# REST API Contract — v1

Base URL: `/api/v1`
Auth: `Authorization: Bearer <access_token>` on everything except `/auth/login`, `/auth/refresh`, `/public/*`, `/health`.

FastAPI auto-generates OpenAPI at `/api/docs` (Swagger) and `/api/redoc`. The frontend generates its TypeScript types from `/api/openapi.json` — types are never hand-written twice.

---

## 0. Conventions

**Success envelope (lists):**
```json
{
  "items": [...],
  "meta": { "total": 248, "limit": 25, "offset": 0, "has_more": true }
}
```
Single resources are returned bare, not wrapped.

**Error (RFC 7807):**
```json
{
  "type": "https://sms.stjosephs.edu/errors/validation-error",
  "title": "Validation failed",
  "status": 422,
  "detail": "marks_obtained cannot exceed max_marks",
  "instance": "/api/v1/marks/bulk",
  "errors": [
    { "field": "items[3].marks_obtained", "message": "must be <= 100", "code": "value_too_high" }
  ],
  "trace_id": "01J8X4..."
}
```

**Status codes.** 200 OK · 201 Created · 204 No Content · 400 malformed · 401 unauthenticated · 403 authenticated but not permitted · 404 · 409 conflict (duplicate, already-locked) · 422 validation · 429 rate-limited · 500.

**Common query params.** `limit` (default 25, max 100), `offset` or `cursor`, `sort` (`-created_at`), `search`, `academic_year_id` (defaults to current), plus resource-specific filters.

**Idempotency.** `POST /payments` and `POST /notifications/send` require an `Idempotency-Key` header. Replaying the same key returns the original response.

---

## 1. Authentication

| Method | Endpoint | Roles | Purpose |
|---|---|---|---|
| POST | `/auth/login` | public | Returns access (15 min) + refresh (7 d, httpOnly cookie) |
| POST | `/auth/refresh` | public | Rotates refresh token |
| POST | `/auth/logout` | any | Revokes refresh token family |
| GET | `/auth/me` | any | Current user, roles, permissions, active scope |
| POST | `/auth/change-password` | any | Requires current password |
| POST | `/auth/forgot-password` | public | Rate-limited; always returns 200 (no user enumeration) |
| POST | `/auth/reset-password` | public | Single-use token |
| POST | `/auth/mfa/enable` · `/verify` | admin | TOTP |

`POST /auth/login`
```json
// request
{ "username": "STJ2026001", "password": "••••••••" }

// 200
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 900,
  "must_change_password": false,
  "user": {
    "id": "uuid", "full_name": "Ananya Nair",
    "roles": ["STUDENT"],
    "permissions": ["attendance:read:self", "marks:read:self"],
    "context": { "student_id": "uuid", "class_section": "10-A", "academic_year_id": "uuid" }
  }
}
```

---

## 2. Users & Academic Structure

| Method | Endpoint | Roles |
|---|---|---|
| GET/POST | `/users` | Admin |
| GET/PATCH/DELETE | `/users/{id}` | Admin |
| POST | `/users/bulk-import` | Admin — CSV/Excel, returns per-row result |
| POST | `/users/{id}/reset-password` | Admin |
| GET/POST | `/academic-years` | Admin |
| POST | `/academic-years/{id}/activate` | Admin |
| GET/POST | `/classes` · `/classes/{id}/sections` | Admin |
| GET/POST | `/subjects` | Admin |
| GET/POST | `/class-subjects` | Admin |
| GET/POST | `/teachers` | Admin |
| GET | `/teachers/{id}/assignments` | Admin, Principal, self |
| POST | `/teachers/{id}/assignments` | Admin |
| GET | `/teachers/me/classes` | Teacher — drives the "my classes" view |

---

## 3. Students & Profiles

| Method | Endpoint | Roles | Notes |
|---|---|---|---|
| GET | `/students` | Admin, Principal, Teacher* | *Teacher sees only assigned sections |
| POST | `/students` | Admin | Creates student + user + guardians in one transaction |
| GET | `/students/{id}` | scoped | Field set varies by role |
| PATCH | `/students/{id}` | Admin |
| GET | `/students/{id}/full-profile` | Admin, Principal | Everything except restricted medical |
| GET | `/students/{id}/medical` | Admin, Principal, Nurse | **Audited read** |
| PUT | `/students/{id}/medical` | Admin, Nurse |
| GET | `/students/{id}/emergency-summary` | Teacher | Blood group + allergies only |
| GET/POST | `/students/{id}/guardians` | Admin |
| GET/POST | `/students/{id}/notes` | staff, filtered by `visibility` |
| GET/POST | `/students/{id}/documents` | Admin — signed upload URL |
| GET | `/students/{id}/timeline` | Admin, Principal | Merged feed: attendance flags, results, notes, fees |
| POST | `/students/bulk-import` | Admin |
| GET | `/students/me` | Student |
| GET | `/parents/me/children` | Parent |

**Role-shaped responses.** `GET /students/{id}` returns different field sets per role. Implement with distinct Pydantic response models (`StudentTeacherView`, `StudentAdminView`, `StudentSelfView`) selected in the router — never by filtering a dict at the end, which leaks on refactor.

---

## 4. Attendance (Module 1)

| Method | Endpoint | Roles |
|---|---|---|
| POST | `/attendance/sessions` | Teacher, Admin — open a session |
| GET | `/attendance/sessions` | scoped — filter by date/section/subject |
| GET | `/attendance/sessions/{id}/roster` | Teacher — students pre-filled PRESENT |
| PUT | `/attendance/sessions/{id}/records` | Teacher — bulk upsert |
| POST | `/attendance/sessions/{id}/lock` | Teacher, Admin |
| PATCH | `/attendance/records/{id}` | Admin — post-lock override, `reason` required |
| GET | `/attendance/students/{id}` | scoped — daily history |
| GET | `/attendance/students/{id}/summary` | scoped — %, subject-wise, monthly trend |
| GET | `/attendance/sections/{id}/summary` | Teacher, Admin, Principal |
| GET | `/attendance/defaulters` | Admin, Principal — below threshold |
| GET | `/attendance/heatmap` | Admin, Principal — student × week |
| POST | `/attendance/export` | staff — `{format: xlsx\|pdf, scope, filters}` → job id |
| GET | `/attendance/exports/{job_id}` | poll → signed URL |
| GET/POST | `/leave-applications` | Parent creates, staff approves |
| POST | `/leave-applications/{id}/approve` · `/reject` | Teacher, Admin |
| GET/POST | `/holidays` | Admin |

`PUT /attendance/sessions/{id}/records`
```json
{
  "records": [
    { "student_id": "uuid", "status": "PRESENT" },
    { "student_id": "uuid", "status": "LATE", "minutes_late": 12 },
    { "student_id": "uuid", "status": "ABSENT", "remarks": "Informed by parent" }
  ]
}
// 200
{ "session_id": "uuid", "updated": 42, "summary": { "present": 38, "absent": 3, "late": 1 } }
```

**Prediction endpoints**

| Method | Endpoint | Returns |
|---|---|---|
| GET | `/attendance/predictions/at-risk` | Students predicted to fall below threshold, with SHAP reasons |
| GET | `/attendance/predictions/forecast` | Next-N-day class attendance forecast with confidence band |

```json
// GET /attendance/predictions/at-risk?class_section_id=...
{
  "items": [{
    "student_id": "uuid", "student_name": "Rohan Das", "roll_number": "10A-17",
    "current_percentage": 71.4,
    "predicted_end_term_percentage": 68.2,
    "risk_level": "HIGH", "confidence": 0.83,
    "top_factors": [
      { "feature": "consecutive_absence_streak", "value": 4, "impact": 0.31 },
      { "feature": "monday_absence_rate",        "value": 0.42, "impact": 0.19 }
    ],
    "model_version": "attendance_risk_v3"
  }],
  "meta": { "model_trained_at": "2026-07-20T02:00:00Z", "total": 7 }
}
```

---

## 5. Performance (Module 2)

| Method | Endpoint | Roles |
|---|---|---|
| GET/POST | `/exams` | Admin |
| POST | `/exams/{id}/schedule` | Admin |
| POST | `/exams/{id}/publish` | Principal — triggers result notifications |
| GET | `/marks` | scoped |
| POST | `/marks/bulk` | Teacher — enter a whole section at once |
| PATCH | `/marks/{id}` | Teacher (before verification), Admin (after) |
| POST | `/marks/{exam_id}/verify` | Admin, Principal |
| POST | `/marks/import` | Teacher — Excel template |
| GET | `/results/students/{id}` | scoped — all exams, trend |
| GET | `/results/exams/{exam_id}/section/{id}` | Teacher, Admin — ranked list |
| POST | `/results/exams/{exam_id}/compute` | Admin — totals, grades, ranks |
| GET | `/results/toppers` | staff |
| GET | `/results/most-improved` | staff — normalised delta |
| GET | `/results/needs-attention` | staff |
| GET | `/results/students/{id}/report-card` | scoped → PDF |
| GET/POST | `/homework` | Teacher creates, all read scoped |
| POST | `/homework/{id}/submit` | Student |
| GET | `/homework/{id}/submissions` | Teacher |
| POST | `/homework/submissions/{id}/grade` | Teacher |
| GET | `/homework/me/pending` | Student |

**Analytics / ML**

| Method | Endpoint | Returns |
|---|---|---|
| GET | `/performance/students/{id}/analytics` | Subject radar, trend line, percentile, attendance correlation |
| GET | `/performance/predictions/risk` | SAFE/WATCH/AT_RISK with SHAP explanation |
| GET | `/performance/clusters` | Named cohorts with centroids and members |
| GET | `/performance/subjects/{id}/difficulty` | Empirical difficulty index vs school mean |

---

## 6. Fees (Module 3)

| Method | Endpoint | Roles |
|---|---|---|
| GET/POST | `/fees/categories` · `/fees/structures` · `/fees/installments` | Admin |
| GET/POST | `/fees/concessions` | Admin creates, Principal approves |
| POST | `/fees/invoices/generate` | Admin — bulk generate for a class/year |
| GET | `/fees/invoices` | Admin; Parent/Student see own |
| GET | `/fees/invoices/{id}` | scoped |
| POST | `/fees/payments` | Admin (counter) — **`Idempotency-Key` required** |
| POST | `/fees/payments/online/initiate` | Parent — creates gateway order |
| POST | `/fees/payments/online/webhook` | gateway — **signature-verified, unauthenticated** |
| GET | `/fees/receipts/{id}` | scoped → PDF |
| POST | `/fees/receipts/{id}/cancel` | Admin — credit note |
| GET | `/fees/students/{id}/ledger` | scoped |
| GET | `/fees/dues` | Admin — ageing buckets |
| GET | `/fees/dashboard` | Admin, Principal |
| POST | `/fees/reminders/send` | Admin — batch |

`POST /fees/payments`
```json
// headers: Idempotency-Key: 9f2c-...
{
  "invoice_id": "uuid", "amount": 12500.00,
  "payment_mode": "UPI", "transaction_id": "UPI2607291234",
  "payment_date": "2026-07-29", "remarks": "Term 1"
}
// 201
{
  "payment_id": "uuid", "payment_reference": "PAY-2627-000412",
  "status": "SUCCESS",
  "invoice": { "id": "uuid", "net_amount": 25000.00, "paid_amount": 12500.00,
               "balance_amount": 12500.00, "status": "PARTIALLY_PAID" },
  "receipt": { "receipt_number": "RCP-2627-000412", "pdf_url": "https://.../signed" }
}
```

---

## 7. Timetable (Module 4)

| Method | Endpoint | Roles |
|---|---|---|
| GET/POST | `/timetable/time-slots` · `/rooms` | Admin |
| GET/PUT | `/timetable/teacher-availability/{teacher_id}` | Admin, self |
| POST | `/timetable/generate` | Admin — async, returns job id |
| GET | `/timetable/jobs/{job_id}` | Admin — progress + solver status |
| GET | `/timetable/versions` | Admin, Principal |
| GET | `/timetable/versions/{id}` | Admin, Principal — full grid + quality metrics |
| POST | `/timetable/versions/{id}/approve` | Principal |
| POST | `/timetable/versions/{id}/publish` | Admin |
| PATCH | `/timetable/entries/{id}` | Admin — manual override, re-validates clashes |
| GET | `/timetable/sections/{id}` | all |
| GET | `/timetable/teachers/{id}` | Teacher self, Admin |
| GET | `/timetable/me/today` | Teacher, Student |
| POST | `/timetable/substitutions` | Admin |
| GET | `/timetable/substitutions/suggest` | Admin — free teachers for a slot |

`POST /timetable/generate`
```json
{
  "academic_year_id": "uuid",
  "class_section_ids": ["uuid", "..."],
  "constraints": {
    "max_periods_per_teacher_per_day": 6,
    "avoid_consecutive_same_subject": true,
    "prefer_core_subjects_morning": true,
    "lab_requires_double_period": true
  },
  "soft_weights": { "subject_spread": 5, "teacher_gaps": 3, "morning_core": 2, "daily_balance": 2 },
  "max_solve_seconds": 120,
  "num_candidates": 3
}
// 202
{ "job_id": "uuid", "status": "QUEUED", "poll_url": "/api/v1/timetable/jobs/uuid" }
```

Infeasible result (the important case):
```json
{
  "status": "INFEASIBLE",
  "diagnostics": {
    "message": "No conflict-free schedule exists with the given inputs.",
    "conflicts": [
      { "type": "INSUFFICIENT_TEACHER_CAPACITY",
        "detail": "Physics requires 18 periods/week across sections 10-A,10-B,10-C but assigned teachers are available for 14.",
        "suggestion": "Add a Physics teacher, extend Mr. Rao's availability by 4 periods, or reduce periods_per_week to 5." },
      { "type": "ROOM_SHORTAGE",
        "detail": "3 lab sessions collide on Wednesday P5-P6; only 2 labs exist.",
        "suggestion": "Move one section's lab to Thursday." }
    ]
  }
}
```

---

## 8. School Analytics (Module 5)

All Admin/Principal only. Responses cached in Redis (15 min TTL), invalidated on relevant writes.

| Method | Endpoint | Returns |
|---|---|---|
| GET | `/analytics/overview` | Headline KPI cards |
| GET | `/analytics/attendance` | Trends by class/section/month, day-of-week pattern |
| GET | `/analytics/attendance/chronic-absentees` | Heatmap data |
| GET | `/analytics/academics` | Pass %, mean/median/σ by subject and class |
| GET | `/analytics/academics/grade-distribution` | Histogram |
| GET | `/analytics/academics/subject-difficulty` | Normalised difficulty index |
| GET | `/analytics/academics/year-over-year` | Multi-year comparison |
| GET | `/analytics/demographics` | Gender ratio, age, geography |
| GET | `/analytics/teachers` | Class-outcome signals (explicitly non-ranking) |
| GET | `/analytics/fees` | Collection, ageing, projection |
| POST | `/analytics/export` | Full report → PDF/Excel job |

```json
// GET /analytics/overview
{
  "academic_year": "2026-27",
  "as_of": "2026-07-29T09:00:00Z",
  "students": { "total": 1284, "active": 1271, "new_admissions": 142 },
  "attendance": { "today_percentage": 93.7, "month_average": 91.2, "trend": "+1.4",
                  "below_threshold_count": 38 },
  "academics": { "last_exam": "Mid-Term I", "pass_percentage": 89.4,
                 "average_percentage": 72.8, "at_risk_count": 61 },
  "fees": { "expected": 18420000.00, "collected": 15106400.00,
            "collection_rate": 82.0, "overdue_count": 97 },
  "staff": { "teachers": 68, "student_teacher_ratio": 18.7 }
}
```

---

## 9. Question Papers (Module 6)

| Method | Endpoint | Roles |
|---|---|---|
| GET/POST | `/questions` | Teacher (own subjects), Admin |
| PATCH/DELETE | `/questions/{id}` | Teacher (own), Admin |
| POST | `/questions/bulk-import` | Teacher — Excel/CSV |
| POST | `/questions/{id}/check-duplicates` | Teacher — embedding similarity |
| POST | `/questions/auto-tag` | Teacher — suggest Bloom's + topic |
| POST | `/questions/generate-draft` | Teacher — LLM draft, `is_approved=false` |
| POST | `/questions/{id}/approve` | Teacher |
| GET | `/questions/stats` | Teacher — coverage gaps by chapter/difficulty |
| GET/POST | `/papers/blueprints` | Teacher, Admin |
| POST | `/papers/generate` | Teacher |
| GET | `/papers/{id}` | Teacher, Admin |
| POST | `/papers/{id}/regenerate-section` | Teacher — swap one section |
| POST | `/papers/{id}/swap-question` | Teacher — replace one question |
| POST | `/papers/{id}/approve` | Admin, Principal |
| GET | `/papers/{id}/pdf` · `/answer-key` | Teacher, Admin |
| POST | `/papers/{id}/generate-sets` | Teacher — shuffled A/B/C |

`POST /papers/generate`
```json
{
  "blueprint_id": "uuid", "title": "Mid-Term I — Physics — Grade 10",
  "exclude_used_within_days": 365,
  "chapter_weightage": { "Light": 0.3, "Electricity": 0.4, "Magnetism": 0.3 },
  "avoid_question_ids": ["uuid"]
}
// 201
{
  "paper_id": "uuid", "total_marks": 80, "question_count": 27,
  "achieved_distribution": {
    "difficulty": { "EASY": 0.30, "MEDIUM": 0.48, "HARD": 0.22 },
    "blooms":     { "REMEMBER": 0.22, "UNDERSTAND": 0.30, "APPLY": 0.30, "ANALYZE": 0.18 }
  },
  "blueprint_deviation": 0.04,
  "warnings": ["Chapter 'Magnetism' has only 11 approved hard questions; consider expanding the bank."],
  "pdf_url": "https://.../signed"
}
```

`blueprint_deviation` — L1 distance between requested and achieved distributions. Surfacing it is honest engineering: the generator says how close it got rather than silently missing the target.

---

## 10. Notifications (Module 7)

| Method | Endpoint | Roles |
|---|---|---|
| GET | `/notifications` | any — own inbox |
| GET | `/notifications/unread-count` | any |
| POST | `/notifications/{id}/read` · `/read-all` | any |
| GET/PUT | `/notifications/preferences` | any |
| POST | `/notifications/send` | Admin, Principal, Teacher (scoped) — `Idempotency-Key` |
| GET/POST | `/notifications/templates` | Admin |
| GET | `/notifications/delivery-log` | Admin — status, failures, cost |
| GET/POST | `/announcements` | Admin, Principal, Teacher |
| POST | `/announcements/half-day` | Admin, Principal — urgent broadcast to affected parents |

`POST /announcements/half-day`
```json
{
  "date": "2026-07-30",
  "dismissal_time": "11:30",
  "reason": "Heavy rainfall advisory",
  "affected_class_ids": null,
  "channels": ["IN_APP", "SMS", "EMAIL"],
  "priority": "URGENT"
}
// 202
{ "notification_id": "uuid", "estimated_recipients": 2418,
  "channels_queued": { "IN_APP": 2418, "SMS": 1289, "EMAIL": 1976 },
  "estimated_sms_cost": 322.25 }
```

Showing estimated cost before a bulk SMS send is the kind of operational detail that distinguishes a real system from a demo.

---

## 11. System

| Method | Endpoint | Roles |
|---|---|---|
| GET | `/health` | public — liveness |
| GET | `/health/ready` | public — DB + Redis check |
| GET | `/admin/audit-logs` | Admin |
| GET | `/admin/ml-models` | Admin — versions, metrics, active flag |
| POST | `/admin/ml-models/{name}/retrain` | Admin — queues training |
| POST | `/admin/ml-models/{id}/activate` | Admin |
| GET | `/admin/jobs` | Admin — Celery queue state |
| GET/PUT | `/admin/settings` | Admin — thresholds, school details, feature flags |

---

## 12. Public Site

| Method | Endpoint |
|---|---|
| GET | `/public/school-info` |
| GET | `/public/news` · `/events` · `/gallery` · `/faculty` |
| GET | `/public/admissions/info` |
| POST | `/public/enquiry` — rate-limited + CAPTCHA |
| POST | `/public/admissions/apply` |

---

## 13. Rate Limits

| Endpoint group | Limit |
|---|---|
| `/auth/login` | 5 / 15 min per IP+username |
| `/auth/forgot-password` | 3 / hour per email |
| `/public/enquiry` | 5 / hour per IP |
| Authenticated reads | 300 / min per user |
| Writes | 60 / min per user |
| Export & generate jobs | 10 / hour per user |

Exceeding returns 429 with a `Retry-After` header.

---

*Next: `03-ML-MODELS.md`*
