# Security & Privacy Design

This system holds the personal, medical and financial data of minors. That raises the bar above a typical CRUD application, and it is a strength of the project if handled explicitly.

---

## 1. Authentication

**Password storage.** Argon2id via `passlib`. Parameters: `time_cost=3`, `memory_cost=65536` (64 MB), `parallelism=4`. Argon2id is the current OWASP first recommendation; bcrypt is acceptable but weaker against GPU attack.

**Password policy.** Minimum 10 characters, checked against the top-10k common-password list (`zxcvbn` strength scoring rather than arbitrary composition rules — mandatory symbols demonstrably produce weaker, more predictable passwords). Admin-created accounts set `must_change_password = true`.

**Tokens.**

| Token | Lifetime | Storage | Contents |
|---|---|---|---|
| Access | 15 min | Memory only (never localStorage) | `sub`, `roles`, `permissions`, `scope`, `jti`, `exp` |
| Refresh | 7 days | httpOnly + Secure + SameSite=Strict cookie | opaque; SHA-256 hash stored server-side |

**Why not localStorage for the access token.** Any XSS reads localStorage. Holding the access token in a JS variable and the refresh token in an httpOnly cookie means an XSS can act during the page session but cannot exfiltrate a durable credential.

**Refresh rotation with reuse detection.** Each refresh issues a new token and revokes the old. If a *revoked* token is presented, the entire token family is revoked and the user is forced to re-authenticate — this is how you detect a stolen refresh token.

**Brute-force protection.** `failed_login_attempts` incremented per failure; lock for 15 minutes after 5. Redis rate limit of 5 attempts per 15 minutes per (IP, username). Login responses are constant-time and identical for "user not found" and "wrong password" — no user enumeration.

**MFA.** TOTP, mandatory for `ADMIN`, optional for `PRINCIPAL`. Given admin access to all student medical and financial records, this is proportionate.

---

## 2. Authorisation — Two Layers

Layer 1 alone is insufficient. Both are required on every protected endpoint.

**Layer 1 — Role/permission check.** Does this role hold `attendance:write`?

**Layer 2 — Object scope check.** Is this teacher actually assigned to *this* section and subject? Is this parent actually linked to *this* student?

```python
# app/api/deps.py — illustrative
async def require_section_access(
    section_id: UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UUID:
    if user.has_role("ADMIN", "PRINCIPAL"):
        return section_id
    if user.has_role("TEACHER"):
        if await teacher_repo.is_assigned(db, user.teacher_id, section_id):
            return section_id
    raise ForbiddenError("No access to this section")
```

**Broken Object Level Authorisation (OWASP API #1)** is the most common real-world API vulnerability, and student projects fail it almost universally: a parent changes `student_id` in the URL and reads another child's medical record. Every endpoint that accepts an entity ID must verify the caller's relationship to that entity. Write an explicit test for this per resource.

**Test to include in the suite:**
```python
async def test_parent_cannot_access_other_students_marks(client, parent_token, other_student_id):
    r = await client.get(f"/api/v1/marks?student_id={other_student_id}",
                         headers={"Authorization": f"Bearer {parent_token}"})
    assert r.status_code == 403
```

---

## 3. Field-Level Access Control

Different roles receive different field sets for the same resource. Implemented with distinct Pydantic response models selected in the router — **not** by post-hoc dict filtering, which silently leaks the moment someone adds a field.

| Data | Admin | Principal | Teacher | Parent | Student |
|---|:--:|:--:|:--:|:--:|:--:|
| Name, class, roll | ✅ | ✅ | ✅ | ✅ own | ✅ self |
| Contact details | ✅ | ✅ | ⚠️ primary phone | ✅ own | ✅ self |
| Full medical record | ✅ | ✅ | ❌ | ✅ own | ⚠️ self |
| Emergency summary | ✅ | ✅ | ✅ | ✅ | ✅ |
| Family income band | ✅ | ✅ | ❌ | ✅ own | ❌ |
| Fee details | ✅ | ✅ | ❌ | ✅ own | ⚠️ balance only |
| Counselling notes | ✅ | ✅ | ❌ | ❌ | ❌ |
| Disciplinary notes | ✅ | ✅ | ✅ | ⚠️ if flagged visible | ❌ |
| ML risk predictions | ✅ | ✅ | ✅ | ❌ | ❌ |

Two deliberate decisions worth a paragraph each in the report:

- **Teachers cannot see full medical records.** A teacher needs to know about a peanut allergy and an epilepsy protocol; they do not need a psychiatric history. Emergency summary only.
- **Risk predictions are hidden from students and parents.** Labelling a child "at risk" to their face is likely to be self-fulfilling. Predictions exist to trigger adult intervention, not to inform the child.

---

## 4. Data Protection

**Encryption in transit.** TLS 1.3, HSTS with `max-age=31536000; includeSubDomains; preload`. HTTP redirects to HTTPS. Internal service traffic stays on a private Docker network.

**Encryption at rest.**
- Database-level: encrypted volumes (RDS encryption / LUKS).
- Column-level for the sensitive set — medical records, counselling notes, `aadhaar_hash`, guardian income. AES-256-GCM at the application layer, keys from a secrets manager (AWS KMS / Vault), never from the codebase.

**Aadhaar handling.** Store only `aadhaar_last4` plus a salted SHA-256 hash for duplicate detection. Never store the full number, never display it, never log it. Aadhaar storage in India carries specific legal obligations that a school project should not assume — avoiding storage is the correct engineering answer and worth stating as such.

**File storage.** All uploads to object storage with private ACLs. Access exclusively through short-lived signed URLs (15 min). No public bucket, ever. Validate uploads by magic bytes, not by file extension; enforce a size cap; strip EXIF from photos (student photos carry GPS coordinates).

---

## 5. Application Security

| Threat | Mitigation |
|---|---|
| SQL injection | SQLAlchemy parameterised queries throughout. No f-string SQL, no exceptions. |
| XSS | React escapes by default. `dangerouslySetInnerHTML` is banned; if rich text is ever needed, sanitise with DOMPurify. CSP header with no `unsafe-inline`. |
| CSRF | SameSite=Strict on the refresh cookie; the access token travels in the Authorization header, which cross-site forms cannot set. Double-submit token on any cookie-authenticated mutation. |
| Mass assignment | Pydantic schemas define exactly the writable fields. Never `Model(**request.dict())` over a raw body. |
| IDOR | Object-level checks (§2) plus non-sequential UUIDs. |
| SSRF | No user-supplied URLs are fetched server-side. If ever required, allowlist only. |
| Path traversal | Uploads keyed by generated UUID; the original filename is metadata only and never used as a path. |
| ReDoS | No user-supplied regex; validation patterns bounded. |
| Zip bomb | Import files size- and row-capped, streamed not loaded whole. |
| Dependency risk | `pip-audit` and `npm audit` in CI; Dependabot enabled. |
| Secrets in repo | `gitleaks` pre-commit hook; `.env` gitignored; `.env.example` holds only placeholder values. |

**Security headers (Nginx):**
```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Content-Type-Options    "nosniff" always;
add_header X-Frame-Options           "DENY" always;
add_header Referrer-Policy           "strict-origin-when-cross-origin" always;
add_header Permissions-Policy        "geolocation=(), microphone=(), camera=()" always;
add_header Content-Security-Policy   "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'" always;
```

**CORS.** Explicit origin allowlist from configuration. Never `allow_origins=["*"]` with `allow_credentials=True` — that combination is rejected by browsers and signals a misconfiguration.

---

## 6. Audit Logging

**Always logged (writes):** create, update, delete on every entity; login success and failure; permission denials; role changes; password resets; fee payments and receipt cancellations; attendance edits after lock; mark changes after verification; timetable publication.

**Also logged (sensitive reads):** medical record access, counselling note access, bulk student data export, full-profile views by non-owners.

Logging reads is unusual and is exactly right for medical data on minors. It answers "who looked at this child's file, and when".

**Log record:** actor, action, entity type and ID, old and new values (JSONB), IP, user agent, timestamp, and a reason for override actions.

**Never logged:** passwords, tokens, full Aadhaar, card numbers, or any request body containing them. Apply a redaction filter in the logging middleware with an explicit key denylist.

**Retention.** Audit logs 7 years (financial records requirement), application logs 90 days, monthly partitions on `audit_logs`.

---

## 7. Privacy & Compliance (India — DPDP Act 2023)

The Digital Personal Data Protection Act 2023 treats children's data as a special category. Relevant obligations and how the design meets them:

| Obligation | Implementation |
|---|---|
| Verifiable parental consent for processing a child's data | Consent captured at admission, versioned, stored with timestamp and consenting guardian |
| No behavioural tracking or targeted advertising directed at children | No analytics SDKs, no third-party trackers, no ad tech anywhere in the application |
| Purpose limitation | Each data category is documented with its purpose; medical data is used for safety only, never for academic modelling |
| Data minimisation | Aadhaar reduced to last-4 + hash; no data collected without a stated use |
| Right to access and correction | Parent portal shows the full record held on their child; correction requests routed to admin with an audit trail |
| Breach notification | Documented incident response runbook (§9) |
| Retention limitation | Student records purged or anonymised per policy after the retention window |

**Retention policy.**

| Data | Retention |
|---|---|
| Active student records | Duration of enrolment |
| Alumni academic records | 10 years (transcript requests) |
| Medical records | 3 years post-exit, then deleted |
| Counselling notes | 3 years post-exit, then deleted |
| Financial records | 7 years (statutory) |
| Attendance details | 5 years, then aggregated and detail deleted |
| Audit logs | 7 years |
| ML training data | Anonymised — no names or identifiers in training sets |

**Anonymisation for ML.** Training datasets are built through a view that strips names, admission numbers, contact details and addresses, replacing the student ID with a per-training-run salted hash. Models learn from patterns, not identities. Document this pipeline in the report — it is a strong, concrete privacy-by-design example.

---

## 8. Operational Security

**Environments.** Separate dev / staging / production databases. **Production data is never copied to development.** Development uses the synthetic seed generator — which is one more reason that generator is a genuine deliverable.

**Access control for operators.** Database credentials per environment; the application user holds only DML rights (no DDL — migrations run as a separate role). No shared admin accounts. All production access through named accounts with MFA.

**Backups.** Nightly full plus continuous WAL archiving, 30-day retention, encrypted at rest, stored in a separate region. **Restore tested monthly** — an untested backup is not a backup, and stating that you tested it is worth including in the report.

**Rate limiting and DoS.** Per-endpoint limits (`02-API-CONTRACT.md` §13), Nginx connection limits, Cloudflare or equivalent in front of production.

**Dependency and image hygiene.** Pinned versions, weekly automated scans, Trivy scanning of container images in CI, non-root container user, minimal base images.

---

## 9. Incident Response Runbook

1. **Detect** — alert from Sentry, anomalous audit-log pattern, or a report.
2. **Contain** — revoke affected sessions (`refresh_tokens` family revoke), disable the compromised account, block the source IP.
3. **Assess** — from audit logs, determine exactly which records were accessed and by whom.
4. **Notify** — school management immediately; affected guardians and the Data Protection Board within the statutory window if personal data was exposed.
5. **Remediate** — patch, force password rotation for affected accounts, rotate keys.
6. **Review** — written post-mortem, blameless, with a concrete preventive action.

Including this runbook in the report demonstrates operational thinking that pure-code projects lack.

---

## 10. Security Testing Checklist

- [ ] Authentication bypass attempts on every protected route
- [ ] Object-level authorisation tests per resource per role (the OWASP API #1 suite)
- [ ] SQL injection probes on every text input and filter parameter
- [ ] XSS payloads in every free-text field (notes, remarks, announcements)
- [ ] CSRF on all cookie-authenticated mutations
- [ ] Rate limit verification on login and export endpoints
- [ ] File upload: oversized, wrong magic bytes, double extension, zip bomb
- [ ] JWT tampering: `alg=none`, modified claims, expired token, wrong signature
- [ ] Privilege escalation: student attempting teacher endpoints, teacher attempting admin
- [ ] IDOR sweep: iterate IDs across all `GET /{resource}/{id}` as each role
- [ ] Sensitive data in logs and in error responses
- [ ] Dependency scan clean (`pip-audit`, `npm audit`, Trivy)
- [ ] TLS configuration graded (SSL Labs A or better)
- [ ] Security headers verified (securityheaders.com A or better)

Automate the object-level authorisation suite in CI. It is the test class most likely to catch a real vulnerability during development.

---

*Next: `05-DEPLOYMENT.md`*
