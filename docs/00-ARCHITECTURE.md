# St. Joseph's Convent School — School Management System
## Master Architecture Blueprint

**Project type:** Final-year B.Tech (AI & Data Science) major project
**Document version:** 0.1 (draft)
**Last updated:** 29 July 2026

---

## 1. Executive Summary

A production-grade, role-based School Management System (SMS) delivered as a responsive web application. The system digitises attendance, academic performance, fees, scheduling, and communication, and layers machine-learning capabilities on top of that operational data — attendance forecasting, at-risk student detection, automated timetable generation, and question-paper generation.

**Design reference:** Christ University web presence (public site + KP/ERP portal) and ESPRO ERP for the internal-portal information architecture. The public-facing marketing site and the authenticated portal are treated as two distinct surfaces sharing one design system.

### 1.1 Why this scope is defensible as a major project

The eight modules are not eight independent CRUD apps. They form a single data pipeline:

```
Attendance + Marks + Fees + Profile  →  unified student data model
                                          ↓
                          feature engineering layer
                                          ↓
        ┌─────────────┬──────────────┬─────────────┬──────────────┐
    attendance      at-risk       clustering    timetable      question
    forecasting   classification  (segments)   optimisation    generation
```

The AI contribution is therefore *integrated*, not bolted on. This is the single most important thing to defend in a viva.

### 1.2 Honest scoping note

Eight modules with production quality is a large build. A realistic ordering that still produces a complete-looking demo is given in `05-DEPLOYMENT.md` §11. Modules 1, 2, 5 and 8 form the defensible core; 3, 4, 6, 7 are strong additions. Attempting all eight at equal depth simultaneously is the most common way these projects fail.

---

## 2. Technology Stack

### 2.1 Recommended stack and rationale

| Layer | Choice | Why this over alternatives |
|---|---|---|
| Frontend | **React 18 + TypeScript + Vite** | Vite gives sub-second HMR vs CRA's slow rebuilds. TypeScript catches the class of bug that kills demos (undefined field on an API response). |
| Styling | **Tailwind CSS + shadcn/ui** | shadcn is copy-in, not a dependency — you own the components, so the UI does not look like every other Bootstrap project. Accessible primitives (Radix) come free. |
| State / data | **TanStack Query + Zustand** | TanStack Query handles server cache, retries, and background refetch — removes ~40% of hand-written state code. Zustand for the small amount of true client state (auth user, UI prefs). |
| Charts | **Recharts** (+ Plotly for the analytics dashboard) | Recharts is React-native and fast for standard charts. Plotly only where you need zoom/brush/export on dense analytics. |
| Backend | **FastAPI (Python 3.11+)** | Decisive for this project: the ML models are Python. A Node backend forces a second Python microservice and cross-process serialisation. FastAPI gives async I/O, automatic OpenAPI docs, and Pydantic validation at the boundary. |
| ORM / migrations | **SQLAlchemy 2.0 (async) + Alembic** | Versioned migrations are what makes a schema "production-ready" rather than a `create_all()` toy. |
| Database | **PostgreSQL 16** | Window functions, CTEs, `JSONB`, partial indexes, and `GENERATED` columns do real work here (attendance percentages, rank computation, flexible profile fields). MySQL is workable; MongoDB is a poor fit — this data is deeply relational. |
| Cache / broker | **Redis 7** | Session/refresh-token denylist, rate limiting, Celery broker, and caching expensive dashboard aggregates. |
| Background jobs | **Celery + Celery Beat** | Reminder emails/SMS, nightly model retraining, report generation, fee-due sweeps. These must not run inside a request. |
| ML | **scikit-learn, XGBoost, pandas, statsmodels** | Tabular data at school scale. Deep learning is not justified and you should say so explicitly in your report — that is a mature engineering judgement, not a limitation. |
| Optimisation | **Google OR-Tools (CP-SAT)** | Timetabling is a constraint-satisfaction problem, not a prediction problem. Framing it correctly is a differentiator. |
| Auth | **JWT (access + refresh) + Argon2id** | Argon2id over bcrypt: it is the current OWASP first recommendation. |
| Notifications | **SMTP / SendGrid + Twilio (or MSG91 for India)** | MSG91/Fast2SMS are materially cheaper for Indian DLT-compliant SMS. |
| File storage | **MinIO (dev) → S3-compatible (prod)** | Receipts, question papers, profile photos, exported reports. |
| Testing | **pytest + httpx (API), Vitest + RTL (unit), Playwright (E2E)** | |
| CI/CD | **GitHub Actions → Docker → Render / Railway / AWS ECS** | |
| Observability | **structlog + Sentry + Prometheus/Grafana (optional)** | |

### 2.2 Stack alternatives (for the report's comparison table)

| Option | Verdict |
|---|---|
| MERN (Node/Express) | Rejected — forces a separate Python ML service; adds an inter-service contract with no benefit for this workload. |
| Django + DRF | Viable. Free admin panel and auth are genuinely attractive. Rejected because DRF's async story is weaker and FastAPI's OpenAPI/Pydantic ergonomics accelerate the API-heavy work here. Worth naming in the report as the closest runner-up. |
| Next.js full-stack | Rejected — excellent frontend, but pushes ML to a separate service again. |
| Firebase / Supabase BaaS | Rejected for a major project: it hides exactly the database design and API work that is being assessed. |

---

## 3. System Architecture

### 3.1 High-level view

```
                        ┌────────────────────────────────┐
                        │   Browser (React SPA + PWA)    │
                        │  public site │ role portal     │
                        └───────────────┬────────────────┘
                                        │ HTTPS / JSON
                        ┌───────────────▼────────────────┐
                        │   Nginx  (TLS, gzip, static)   │
                        └───────────────┬────────────────┘
                                        │
                        ┌───────────────▼────────────────┐
                        │       FastAPI application      │
                        │  ┌──────────────────────────┐  │
                        │  │ API layer (routers)      │  │
                        │  ├──────────────────────────┤  │
                        │  │ Service layer (logic)    │  │
                        │  ├──────────────────────────┤  │
                        │  │ Repository layer (ORM)   │  │
                        │  └──────────────────────────┘  │
                        └──┬──────────┬─────────┬────────┘
                           │          │         │
              ┌────────────▼──┐  ┌────▼────┐  ┌─▼──────────────┐
              │ PostgreSQL 16 │  │ Redis 7 │  │ MinIO / S3     │
              └───────────────┘  └────┬────┘  └────────────────┘
                                      │
                          ┌───────────▼───────────┐
                          │ Celery workers + Beat │
                          │ reminders │ retrain   │
                          │ exports   │ fee sweep │
                          └───────────┬───────────┘
                                      │
                          ┌───────────▼───────────┐
                          │ ML registry (joblib)  │
                          │ + OR-Tools solver     │
                          └───────────────────────┘
```

### 3.2 Layering rule (enforce this from day one)

```
router  →  service  →  repository  →  model
```

- **Routers** parse/validate input, check permissions, return response schemas. No business logic, no ORM queries.
- **Services** hold all business rules. Testable without HTTP.
- **Repositories** own every database query. Nothing else imports the ORM session directly.
- **Models** are SQLAlchemy tables only.

The single most common failure in student projects is a 600-line router file. This rule prevents it.

### 3.3 Modular monolith, not microservices

Deploy as one FastAPI process with clean internal module boundaries. Microservices would add network failure modes, distributed transactions, and deployment complexity for a system that will serve a few thousand users. Say this explicitly in the report — choosing *not* to over-engineer is a defensible architectural decision.

The one justified split: **ML training** runs in Celery workers, never in the API process, because training is CPU-bound and would block the event loop. Inference is fast enough (<50ms for a tree model) to run in-process.

---

## 4. Roles and Permission Matrix

Five roles, enforced server-side on every endpoint. Client-side hiding is UX only — never security.

| Capability | Admin | Principal | Teacher | Student | Parent |
|---|:--:|:--:|:--:|:--:|:--:|
| Manage users / roles | ✅ | 👁 | ❌ | ❌ | ❌ |
| Manage academic year, classes, subjects | ✅ | 👁 | ❌ | ❌ | ❌ |
| Mark attendance | ✅ | ❌ | ✅ own classes | ❌ | ❌ |
| View attendance | ✅ all | ✅ all | ✅ own classes | ✅ self | ✅ own child |
| Enter marks | ✅ | ❌ | ✅ own subjects | ❌ | ❌ |
| View performance analytics | ✅ all | ✅ all | ✅ own classes | ✅ self | ✅ own child |
| Fee configuration | ✅ | 👁 | ❌ | ❌ | ❌ |
| Record / view payments | ✅ | 👁 | ❌ | 👁 own | ✅ own child |
| Generate timetable | ✅ | ✅ approve | ❌ | ❌ | ❌ |
| View timetable | ✅ | ✅ | ✅ | ✅ | ✅ |
| School-wide analytics | ✅ | ✅ | ❌ | ❌ | ❌ |
| Generate question paper | ✅ | 👁 | ✅ own subjects | ❌ | ❌ |
| Manage question bank | ✅ | ❌ | ✅ own subjects | ❌ | ❌ |
| Post homework / announcements | ✅ | ✅ | ✅ own classes | ❌ | ❌ |
| Receive reminders | — | — | ✅ | ✅ | ✅ |
| Full student profile (medical, family) | ✅ | ✅ | ⚠️ limited | 👁 self | ✅ own child |
| Audit log | ✅ | 👁 | ❌ | ❌ | ❌ |

Legend: ✅ full · 👁 read-only · ⚠️ restricted subset · ❌ denied

**Two non-obvious rules worth implementing properly:**

1. **Scope, not just role.** A teacher having the `attendance:write` permission is insufficient — they must also be *assigned* to that class-section-subject. Every teacher endpoint checks a `teacher_assignments` row. This is object-level authorisation and is where most RBAC implementations leak.
2. **Medical data is restricted even from teachers** by default, exposed only as an allergy/emergency flag. This is a deliberate privacy decision worth one paragraph in your report.

---

## 5. Module Specifications

Each module below states: purpose → core entities → key logic → AI component → the hard part.

---

### Module 1 — Student Attendance

**Purpose.** Replace paper registers with period-wise or day-wise digital attendance, with export and forecasting.

**Core entities.** `attendance_sessions`, `attendance_records`, `attendance_summary` (materialised).

**Key logic.**
- Teacher opens a session for (class_section, subject, date, period). System pre-loads the roster with default `PRESENT` — marking exceptions is 10× faster than marking everyone.
- Statuses: `PRESENT`, `ABSENT`, `LATE`, `HALF_DAY`, `EXCUSED`, `ON_LEAVE`.
- A session locks after a configurable window (default 24h). Post-lock edits require an admin override and are written to the audit log with a reason. Without this, attendance data is not trustworthy.
- Attendance percentage is computed from `attendance_summary`, refreshed nightly and incrementally on write. Do not compute it with a full-table scan on every dashboard load.

**Exports.** Excel via `openpyxl` (formatted, frozen header, conditional colour for <75%), PDF via WeasyPrint from an HTML template. Generated in Celery, returned as a signed download URL.

**AI component — attendance forecasting.**
- *Per-student risk:* will this student fall below the 75% threshold by term end? Gradient-boosted classifier on features: current %, 7/14/30-day rolling rate, consecutive-absence streak, day-of-week pattern, subject-wise variance, distance-from-school band, prior-term %.
- *Per-class volume:* next-week expected attendance rate. SARIMA or Prophet on the daily series with school-holiday regressors. Useful for the principal's planning view.
- Honest caveat for the report: with one school's data you will have limited rows. Report cross-validated metrics with confidence intervals and do not overstate accuracy.

**The hard part.** Timetable-dependent period attendance means a "day" is not one record. Model sessions properly from the start; retrofitting period-wise attendance onto a day-wise schema is a rewrite.

---

### Module 2 — Student Performance Dashboard

**Purpose.** Unified academic view: marks, assignments, attendance correlation, and predictive flags.

**Core entities.** `exams`, `exam_subjects`, `marks`, `assignments`, `assignment_submissions`, `grade_scales`.

**Key logic.**
- Grade computation driven by a configurable `grade_scales` table, never hard-coded. Schools change grading policy.
- Rank computed with `RANK() OVER (PARTITION BY class_section_id ORDER BY total DESC)` — in SQL, not Python.
- **Topper list**, **most-improved list** (delta vs previous exam, normalised so a 40→60 jump ranks above 88→92), and **needs-attention list**.
- Subject-wise strength/weakness radar per student.

**AI component.**
- *Risk prediction:* multi-class classifier (`SAFE` / `WATCH` / `AT_RISK`) predicting next-exam performance band. Features: rolling marks average, marks trend slope, attendance %, assignment submission rate, subject-difficulty index, previous-term result. XGBoost with SHAP values so the dashboard can say *why* a student is flagged — an unexplained risk score is useless to a teacher and indefensible in a viva.
- *Clustering:* K-Means or Gaussian Mixture over standardised performance+engagement features to surface cohorts such as "high marks / low attendance" or "consistent but plateaued". Choose k by silhouette score and *name the clusters by inspecting centroids* — do not ship "Cluster 3".

**The hard part.** Class imbalance. Few students are genuinely at risk, so a naive model scores 94% accuracy by predicting SAFE for everyone. Use stratified splits, class weights, and report precision/recall/F1 per class plus PR-AUC. Never report accuracy alone.

---

### Module 3 — Fee Management

**Purpose.** Fee structure, invoicing, payment capture, dues tracking, receipts, reminders.

**Core entities.** `fee_categories`, `fee_structures`, `fee_installments`, `student_fee_assignments`, `invoices`, `payments`, `concessions`, `receipts`.

**Key logic.**
- Fee structure is per (academic_year, class, category) with installment plans.
- **Concessions/scholarships** as a first-class entity (percentage or flat, with an approval trail) — real schools always have these, and bolting them on later corrupts every total.
- Payment modes: cash, cheque, UPI, card, online gateway (Razorpay for India).
- **Money is `NUMERIC(12,2)`, never `FLOAT`.** Non-negotiable.
- Receipts are immutable once issued; corrections are credit notes, not edits.
- Idempotency keys on payment creation to survive double-clicks and gateway retries.
- Ledger view per student: charged − concession − paid = outstanding.

**Dashboard.** Collection rate by class, ageing buckets (0–30/31–60/61–90/90+ days), defaulter list, month-on-month collection trend, projected collection.

**AI component (optional, honest framing).** A payment-delay likelihood model is possible (features: past payment latency, installment size, sibling count, prior defaults). Flag it as *decision support for reminder prioritisation only* — it must never gate a student's access to education. State that ethical boundary explicitly in the report; it will earn marks.

**The hard part.** Reconciliation and partial payments across installments. Define allocation order (oldest installment first) and write it down.

---

### Module 4 — AI Timetable Generator

**Purpose.** Generate conflict-free weekly timetables satisfying hard constraints and optimising soft ones.

**Core entities.** `time_slots`, `periods`, `teacher_availability`, `room_resources`, `timetable_versions`, `timetable_entries`.

**Approach — constraint programming with OR-Tools CP-SAT.** Not a neural network. Genetic algorithms are the usual student choice and are demonstrably worse here: slower to converge and with no optimality guarantee. Make this comparison a section in your report.

**Hard constraints (must hold):**
- No teacher in two places in one slot.
- No class-section with two subjects in one slot.
- No room double-booked.
- Each subject meets its required periods per week.
- Teacher availability windows and max daily/weekly load respected.
- Lab subjects occupy contiguous double periods in lab rooms.

**Soft constraints (minimise weighted penalty):**
- Spread each subject across the week rather than clustering.
- Avoid more than two consecutive periods of one subject.
- Place cognitively demanding subjects (Maths, Science) in earlier periods.
- Minimise teacher gap ("free-then-teach-again") periods.
- Balance daily load across the week.
- Respect teacher slot preferences where possible.

**Output.** Multiple candidate versions with a quality score; principal reviews and approves one; approved version publishes to all role views. Versioning matters — mid-term changes must not destroy history.

**The hard part.** Infeasibility. Real inputs are often over-constrained (too few teachers for the required periods). The solver returns INFEASIBLE with no explanation, which is a terrible user experience. Implement a **relaxation pass**: solve with soft constraints only, then report which hard constraint is violated and by how much — "Physics needs 6 periods/week but Mr. Rao is only available for 4". A generator that explains *why* it cannot solve is significantly more impressive than one that only works on clean data.

---

### Module 5 — School Analytics Dashboard

**Purpose.** Institution-level intelligence for the principal and admin.

**Views.**
- Attendance: school/class/section trends, chronic-absentee heatmap (student × week), day-of-week patterns.
- Academics: pass %, mean/median/std by subject and class, grade distribution, year-on-year comparison, subject-difficulty index (mean marks normalised across subjects).
- Demographics: gender ratio by class, age distribution, geographic spread of students.
- Teacher analytics: class-average outcomes by teacher — **presented as a support signal, never a ranking**. Confounded by class composition; say so on the dashboard itself.
- Fees: collection and ageing (mirrors Module 3).
- Drill-down: every chart clicks through school → class → section → student.

**Implementation notes.** Pre-aggregate into summary tables refreshed nightly by Celery. A dashboard that runs seven `GROUP BY`s over the full marks table on every load will be slow by the second year of data. Cache aggregate responses in Redis with a 15-minute TTL and explicit invalidation on write.

---

### Module 6 — AI Question Paper Generator

**Purpose.** Generate balanced question papers from a curated question bank.

**Core entities.** `question_bank`, `question_tags`, `blueprints`, `generated_papers`, `paper_questions`.

**Question metadata.** subject, chapter/unit, topic, **Bloom's taxonomy level** (Remember → Create), difficulty (easy/medium/hard, plus an empirical difficulty score updated from historical student performance), marks, type (MCQ / short / long / numerical / diagram), expected time, usage count, last-used date.

**Generation as constrained selection — two stages:**
1. **Blueprint definition:** total marks, section structure, per-section question count and marks, difficulty mix (e.g. 30/50/20), chapter weightage, Bloom's distribution.
2. **Selection:** integer-programming / weighted random selection satisfying the blueprint while maximising diversity and penalising recently-used questions.

**Where genuine AI helps (be precise about this):**
- Auto-tagging new questions with Bloom's level and topic using a fine-tuned classifier or an LLM call.
- Semantic duplicate detection via sentence embeddings (`sentence-transformers`) + cosine similarity — prevents two near-identical questions in one paper. This is the most valuable AI feature in the module.
- Empirical difficulty calibration from historical marks (Item Response Theory-lite): a question tagged "easy" that 60% of students fail is mis-tagged, and the system should say so.
- Optional LLM-based question *generation* from syllabus text — clearly marked as draft requiring teacher approval. Never auto-publish generated questions.

**Output.** PDF with header, instructions, sections, marks column; plus an answer key. Multiple shuffled sets (A/B/C) from the same blueprint.

**The hard part.** The question bank must exist before anything works. Build a bulk CSV/Excel importer early or you will have an empty demo.

---

### Module 7 — Homework & Exam Reminder System

**Purpose.** Multi-channel, role-aware notifications.

**Core entities.** `notifications`, `notification_templates`, `notification_preferences`, `delivery_log`, `homework`, `announcements`.

**Triggers.**
- Homework posted → students + parents of that section.
- Homework due tomorrow → pending submitters only.
- Exam scheduled / 3 days out / tomorrow.
- **Half-day and holiday alerts** → all parents of affected sections (explicitly required).
- Fee due in 7 days / overdue.
- Attendance below threshold → parent alert.
- Result published.

**Channels.** In-app (always), email (SMTP/SendGrid), SMS (DLT-compliant template IDs for India), optional web push. Per-user, per-category channel preferences with a quiet-hours window.

**Architecture.** Event → `notifications` row → Celery task fan-out → per-channel adapter → `delivery_log` with status, provider message ID, and retry count. Exponential-backoff retry, dead-letter after N failures. Templates in the database with variable substitution so admins edit copy without a deploy.

**The hard part.** Idempotency. A retried Celery task must not send the same SMS twice — SMS costs money and duplicate messages destroy user trust. Use a deterministic key: `hash(notification_id, channel, recipient_id)`.

---

### Module 8 — Student Profile

**Purpose.** The single source of truth every other module joins against.

**Sections.**
- **Identity:** admission number, name, DOB, gender, blood group, photo, Aadhaar reference (store a hash or last-4 only, never the full number — justify this in the report), category, mother tongue, religion (optional, respect it being optional).
- **Academic:** current class/section, roll number, admission date, previous school, transfer certificate details, house/club.
- **Family:** father, mother, guardian — name, occupation, qualification, phone, email, annual income band, primary-contact flag. **Sibling links within the school** (useful for fee concessions and analytics).
- **Contact:** permanent and correspondence address, emergency contacts (ordered).
- **Medical:** blood group, allergies, chronic conditions, medications, physician contact, special-needs accommodations, vaccination record. **Access-restricted** — admin/principal/nurse full, teachers see only an emergency-critical summary.
- **Notes/observations:** timestamped, authored, categorised (academic / behavioural / achievement / disciplinary / counselling). Counselling notes restricted. Notes are append-only and edits are versioned.
- **Documents:** birth certificate, TC, mark sheets, ID proofs, photos in object storage with signed time-limited URLs.

**The hard part.** This module carries the project's genuine privacy weight — minor children's medical and family financial data. Field-level access control, encryption at rest for the sensitive columns (`pgcrypto` or application-level AES-GCM), full audit logging of every read of medical and counselling data, and a documented retention policy. A dedicated "Data Protection & Privacy" chapter in the report, referencing India's DPDP Act 2023, will meaningfully differentiate this project.

---

## 6. Project Structure

```
St.Josephs_SMS/
├── docs/
│   ├── 00-ARCHITECTURE.md          ← this file
│   ├── 01-DATABASE-SCHEMA.md
│   ├── 02-API-CONTRACT.md
│   ├── 03-ML-MODELS.md
│   ├── 04-SECURITY.md
│   └── 05-DEPLOYMENT.md
│
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app factory, middleware, router mounting
│   │   ├── core/
│   │   │   ├── config.py           # Pydantic Settings, env-driven
│   │   │   ├── security.py         # Argon2 hashing, JWT encode/decode
│   │   │   ├── permissions.py      # RBAC matrix + scope checks
│   │   │   ├── exceptions.py       # domain exceptions → HTTP mapping
│   │   │   └── logging.py          # structlog config
│   │   ├── db/
│   │   │   ├── base.py             # DeclarativeBase, naming convention
│   │   │   ├── session.py          # async engine + session factory
│   │   │   └── mixins.py           # TimestampMixin, SoftDeleteMixin, AuditMixin
│   │   ├── models/                 # SQLAlchemy tables, one file per domain
│   │   ├── schemas/                # Pydantic request/response models
│   │   ├── repositories/           # all DB queries live here
│   │   ├── services/               # business logic
│   │   ├── api/
│   │   │   ├── deps.py             # get_db, get_current_user, require_role
│   │   │   └── v1/                 # one router per module
│   │   ├── ml/
│   │   │   ├── features/           # feature engineering (shared train/infer)
│   │   │   ├── training/           # training scripts
│   │   │   ├── inference/          # loaded-model predict wrappers
│   │   │   ├── timetable/          # OR-Tools CP-SAT solver
│   │   │   ├── qpgen/              # blueprint solver + embeddings
│   │   │   └── registry.py         # model versioning, load/save
│   │   ├── tasks/                  # Celery tasks
│   │   ├── notifications/          # channel adapters
│   │   └── utils/                  # exports (excel/pdf), pagination, dates
│   ├── alembic/
│   ├── tests/
│   ├── requirements.txt
│   └── Dockerfile
│
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── routes/                 # route tree + role guards
│   │   ├── layouts/                # PublicLayout, PortalLayout
│   │   ├── pages/
│   │   │   ├── public/             # home, about, academics, admissions, contact
│   │   │   ├── auth/
│   │   │   ├── admin/  principal/  teacher/  student/  parent/
│   │   ├── components/
│   │   │   ├── ui/                 # shadcn primitives
│   │   │   ├── charts/
│   │   │   └── shared/             # DataTable, StatCard, EmptyState
│   │   ├── lib/  api.ts  auth.ts  utils.ts
│   │   ├── hooks/
│   │   └── types/                  # generated from OpenAPI
│   ├── package.json
│   └── Dockerfile
│
├── infra/
│   ├── nginx/
│   └── grafana/
├── ml_notebooks/                   # EDA and experiments — keep out of app code
├── docker-compose.yml
├── docker-compose.prod.yml
├── .env.example
├── .github/workflows/ci.yml
└── README.md
```

---

## 7. UI/UX Direction

### 7.1 Two surfaces

**Public site** (Christ University reference): hero with school imagery, about/vision, academics by stream, admissions with downloadable prospectus, faculty, facilities, news & events, photo gallery, contact with an embedded map, and a prominent **Portal Login**. Server-rendered or statically pre-rendered for SEO.

**Authenticated portal** (ESPRO/Christ KP reference): persistent left sidebar with role-filtered navigation, top bar with search / notification bell / profile menu, breadcrumbs, and a role-specific dashboard landing page.

### 7.2 Role landing pages

| Role | Lands on |
|---|---|
| Admin | System health, user counts, today's attendance %, fee collection, recent audit events |
| Principal | School KPIs, at-risk students, attendance trend, pending approvals |
| Teacher | Today's timetable, one-click "Mark Attendance" for the current period, pending grading, class alerts |
| Student | Attendance %, upcoming homework/exams, latest marks, timetable, fee status |
| Parent | Child's attendance, recent marks, fee dues, notifications, teacher remarks |

### 7.3 Design tokens

- **Palette:** deep navy/maroon primary (convent-school appropriate, distinguishable from generic SaaS blue), warm neutral surfaces, semantic status colours (green ≥85%, amber 75–85%, red <75% for attendance — used consistently everywhere).
- **Typography:** one humanist sans (Inter/Source Sans) at 14–16px base, generous line height. Serif accents on the public site only.
- **Density:** portal tables are dense; dashboards are spacious.
- **Accessibility:** WCAG 2.1 AA — 4.5:1 contrast, full keyboard navigation, ARIA labels on charts, and never colour alone to convey status (pair with an icon or label). Include an accessibility section in your report.
- **Responsive:** mobile-first for parent and student views (they will use phones); teacher attendance marking must be genuinely usable one-handed on a phone. Admin analytics may assume desktop.
- **States:** every list has designed loading (skeleton), empty, and error states. Empty states are where student projects look unfinished.

---

## 8. Cross-Cutting Concerns

| Concern | Decision |
|---|---|
| API versioning | `/api/v1/...` from day one |
| Pagination | Cursor-based for large lists; `limit`/`offset` for admin tables |
| Errors | RFC 7807 problem+json: `{type, title, status, detail, instance, errors[]}` |
| Timezone | Store UTC, render in `Asia/Kolkata` |
| Soft delete | `deleted_at` on all student-facing entities; hard delete only via admin purge |
| Audit | `audit_logs` on every write and on every sensitive read (medical, counselling) |
| Idempotency | `Idempotency-Key` header on payments and notification sends |
| Rate limiting | Per-IP and per-user via Redis; strict on `/auth/login` |
| Config | 12-factor, all via environment; no secrets in the repository, ever |
| Academic year | Every operational table carries `academic_year_id`. Retrofitting multi-year support is painful. |

---

## 9. Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| No real data for ML training | High — models untrainable | Build a realistic synthetic data generator early (seed script with plausible distributions and correlations). Be transparent in the report that models were validated on synthetic + limited real data. |
| Scope overrun across 8 modules | High | Follow the roadmap ordering; ship modules 1/2/5/8 to production quality before starting 3/4/6/7. |
| Timetable solver infeasible on real inputs | Medium | Relaxation pass with explanatory diagnostics (§ Module 4). |
| SMS cost and DLT registration delay | Medium | Ship email + in-app first; SMS behind a feature flag. DLT template approval in India takes 1–2 weeks — start it early. |
| Class imbalance inflating ML metrics | Medium — undermines the project's core claim | Stratified CV, class weights, PR-AUC and per-class F1 reported throughout. |
| Privacy exposure of minors' data | High — ethical and legal | Field-level RBAC, encryption at rest, read auditing, documented retention (§ Module 8). |
| Demo failure on presentation day | High | Seeded demo database, recorded fallback video, no live external API calls in the demo path. |

---

## 10. What Makes This Portfolio-Grade

Four things separate this from a typical college project, and each should get explicit attention:

1. **Explainable ML, not black-box scores.** SHAP-backed reasons on every at-risk flag.
2. **Correct problem framing.** Timetabling solved as constraint programming; question-paper generation as constrained selection; only genuinely predictive problems solved with learned models.
3. **Production hygiene.** Migrations, tests, CI, audit logs, structured errors, RBAC with object-level scope checks.
4. **Stated ethical boundaries.** Documented limits on how predictions may be used, especially around fees and at-risk labelling of children.

---

*Next: `01-DATABASE-SCHEMA.md`*
