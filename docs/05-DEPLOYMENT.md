# Deployment, Testing & Operations

---

## 1. Environments

| Environment | Purpose | Data | Hosting |
|---|---|---|---|
| Local | Development | Synthetic seed | Docker Compose |
| Staging | Integration + demo rehearsal | Synthetic, production-shaped | Render / Railway free tier |
| Production | Live school use | Real | AWS ECS or a managed VPS |

**Production data never flows downstream.** Development and staging use the synthetic generator.

---

## 2. Local Development

```bash
git clone <repo> && cd St.Josephs_SMS
cp .env.example .env          # fill in local values
docker compose up -d          # postgres, redis, minio, mailhog
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
alembic upgrade head
python -m app.scripts.seed --demo          # roles, classes, subjects, slots
python -m app.scripts.generate_synthetic --students 400 --years 2
uvicorn app.main:app --reload --port 8000

cd ../frontend
npm install && npm run dev    # http://localhost:5173
```

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API | http://localhost:8000 |
| API docs | http://localhost:8000/api/docs |
| MinIO console | http://localhost:9001 |
| Mailhog (email catcher) | http://localhost:8025 |

Mailhog matters more than it looks — it lets you develop and demo the entire notification module without sending a single real email.

---

## 3. Container Topology

```
docker-compose.yml
├── postgres     (16-alpine, volume-persisted)
├── redis        (7-alpine)
├── minio        (object storage, S3 API)
├── mailhog      (dev SMTP capture)
├── backend      (FastAPI, uvicorn)
├── celery-worker
├── celery-beat
├── flower        (Celery monitoring, :5555)
└── frontend      (Vite dev server / Nginx-served build in prod)
```

Production adds Nginx as TLS terminator and static file server, and drops mailhog and flower's public exposure.

**Backend image** is multi-stage: a builder stage compiles wheels, the runtime stage copies only the virtualenv and app code, runs as a non-root user, and includes a `HEALTHCHECK`. Final image should land around 250 MB.

---

## 4. CI/CD (GitHub Actions)

```
on: [push, pull_request]

jobs:
  backend:
    - ruff check + ruff format --check
    - mypy app/
    - pytest --cov=app --cov-fail-under=70   (postgres + redis services)
    - pip-audit
  frontend:
    - eslint + prettier --check
    - tsc --noEmit
    - vitest run --coverage
    - npm run build
    - npm audit --audit-level=high
  e2e:
    - docker compose up + playwright test
  security:
    - gitleaks
    - trivy image scan
  deploy:            # main branch only, after all pass
    - build & push images
    - alembic upgrade head
    - rolling deploy
    - smoke test /health/ready
```

Coverage floor of 70% is realistic and enforceable. A higher stated target that you then disable is worse than an honest one you actually meet.

---

## 5. Testing Strategy

| Layer | Tool | Target | What it covers |
|---|---|---|---|
| Unit | pytest | Services, feature builders, solvers | Business rules in isolation |
| Integration | pytest + httpx + test DB | Routers → DB | Real SQL, real constraints |
| Authorisation | pytest matrix | Every endpoint × every role | The OWASP API #1 suite |
| Frontend unit | Vitest + RTL | Components, hooks | Rendering and interaction |
| E2E | Playwright | 5 critical journeys | Full stack |
| Load | Locust | Attendance marking, dashboard | 200 concurrent users |
| ML | pytest | Feature parity, model contracts | Train/serve skew |

**The five E2E journeys** (these are what you demo):
1. Teacher logs in → marks attendance for a period → verifies the section summary updates
2. Teacher enters marks in bulk → admin computes results → student sees the report card
3. Admin generates invoices → parent pays online → receipt PDF downloads
4. Admin generates a timetable → principal approves → teacher sees "today's schedule"
5. Teacher posts homework → parent receives the notification → student submits

**Test data.** Factory Boy factories, a fresh transactional rollback per test, and a session-scoped test database created and dropped by a fixture. Never test against the development database.

**The ML test most projects miss:**
```python
def test_training_and_inference_features_match():
    """Guards against train/serve skew — the invisible ML bug."""
    train_cols = build_attendance_features(train_df, as_of=date(2026, 3, 31)).columns
    infer_cols = build_attendance_features(live_df,  as_of=date.today()).columns
    assert list(train_cols) == list(infer_cols)
```

---

## 6. Performance Targets

| Operation | Target (p95) |
|---|---|
| Login | < 300 ms |
| Attendance roster load | < 400 ms |
| Attendance bulk save (50 students) | < 600 ms |
| Student dashboard | < 500 ms |
| Analytics dashboard (cached) | < 300 ms |
| Analytics dashboard (cold) | < 2 s |
| Marks bulk entry (60 rows) | < 800 ms |
| Excel export (1000 rows) | < 5 s (async job) |
| ML inference (single student) | < 100 ms |
| Timetable generation | < 120 s (async) |
| Question paper generation | < 15 s |

**How the targets are met:** pre-aggregated summary tables, Redis caching of dashboard aggregates with explicit invalidation, indexes from `01-DATABASE-SCHEMA.md` §12, `selectinload` to eliminate N+1 queries, pagination everywhere, and async jobs for anything above two seconds.

**N+1 queries are the single most likely cause of a slow demo.** Enable SQLAlchemy `echo` during development and watch the query count on the dashboard endpoints.

---

## 7. Monitoring

| Concern | Tool |
|---|---|
| Errors | Sentry (backend + frontend), release-tagged |
| Structured logs | structlog → JSON → stdout → aggregator |
| Metrics | prometheus-fastapi-instrumentator → Prometheus → Grafana |
| Uptime | UptimeRobot on `/health/ready` |
| Background jobs | Flower |
| DB | `pg_stat_statements` for slow queries |

**Alerts worth configuring:** error rate > 1% over 5 min, p95 latency > 2 s, Celery queue depth > 100, disk > 80%, failed logins > 50/min (credential stuffing), any 5xx on payment endpoints.

Every log line carries a `trace_id` propagated from the request header, which is also returned in error responses — so a user reporting "it broke" gives you an ID that finds the exact request.

---

## 8. Production Deployment Options

| Option | Cost/month | Best for |
|---|---|---|
| **Render** (web + worker + managed PG + Redis) | ~$25–40 | Simplest path; recommended for the project demo |
| **Railway** | ~$20–35 | Similar, good DX |
| **AWS ECS Fargate + RDS + ElastiCache + S3** | ~$80–150 | Genuine production; strongest to describe in the report |
| **Single VPS (Hetzner/DigitalOcean) + Docker Compose** | ~$12–25 | Cheapest real deployment; you manage backups and TLS |

**Recommendation:** deploy the demo on Render, and *document* the AWS architecture in the report with a diagram. You get a working live URL for the presentation plus a production-grade design to defend, without the AWS bill.

**Deployment order (non-negotiable):**
1. Back up the database
2. Run migrations (backward-compatible only — additive first, destructive in a later release)
3. Deploy backend with a rolling restart
4. Deploy frontend
5. Smoke test `/health/ready` and one authenticated journey
6. Roll back on failure — and have practised the rollback before you need it

---

## 9. Backup & Recovery

| Item | Frequency | Retention | Location |
|---|---|---|---|
| Postgres full dump | Nightly 02:00 | 30 days | Separate region, encrypted |
| WAL archive | Continuous | 7 days | Enables PITR |
| Object storage | Versioning + cross-region replication | 90 days | |
| ML artifacts | On each training | All versions | Object storage |

**Targets:** RPO 1 hour, RTO 4 hours. **Restore drill monthly** — restore to a scratch instance and verify row counts and a sample query. Record the drill date; being able to say "last verified restore: 2026-07-15" is a genuinely professional detail.

---

## 10. Environment Variables

```ini
# ── Application ─────────────────────────────
APP_NAME="St. Joseph's SMS"
ENVIRONMENT=development          # development | staging | production
DEBUG=true
SECRET_KEY=change-me-min-32-chars
API_V1_PREFIX=/api/v1
ALLOWED_ORIGINS=http://localhost:5173
TIMEZONE=Asia/Kolkata

# ── Database ────────────────────────────────
DATABASE_URL=postgresql+asyncpg://sms:sms@localhost:5432/sms_db
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=10

# ── Redis / Celery ──────────────────────────
REDIS_URL=redis://localhost:6379/0
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# ── Auth ────────────────────────────────────
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
JWT_ALGORITHM=HS256
PASSWORD_MIN_LENGTH=10
MAX_LOGIN_ATTEMPTS=5
LOCKOUT_MINUTES=15

# ── Storage ─────────────────────────────────
S3_ENDPOINT_URL=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=sms-files
S3_REGION=ap-south-1
SIGNED_URL_EXPIRE_SECONDS=900

# ── Email ───────────────────────────────────
SMTP_HOST=localhost
SMTP_PORT=1025
SMTP_USER=
SMTP_PASSWORD=
EMAIL_FROM="St. Joseph's School <noreply@stjosephs.edu.in>"

# ── SMS (India — DLT compliant) ─────────────
SMS_PROVIDER=msg91                # msg91 | twilio | disabled
SMS_API_KEY=
SMS_SENDER_ID=STJOSP
SMS_ENABLED=false

# ── Payments ────────────────────────────────
PAYMENT_GATEWAY=razorpay
RAZORPAY_KEY_ID=
RAZORPAY_KEY_SECRET=
RAZORPAY_WEBHOOK_SECRET=

# ── ML ──────────────────────────────────────
ML_MODEL_DIR=./ml_artifacts
ML_ENABLE_TRAINING=true
ATTENDANCE_THRESHOLD=75.0
RISK_THRESHOLD_SAFE=60.0
RISK_THRESHOLD_WATCH=40.0
EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2

# ── Timetable solver ────────────────────────
SOLVER_MAX_SECONDS=120
SOLVER_NUM_WORKERS=4

# ── Observability ───────────────────────────
SENTRY_DSN=
LOG_LEVEL=INFO
LOG_FORMAT=json

# ── Feature flags ───────────────────────────
FEATURE_ONLINE_PAYMENTS=false
FEATURE_SMS_NOTIFICATIONS=false
FEATURE_AI_QUESTION_GENERATION=false
FEATURE_TIMETABLE_GENERATOR=true
```

Feature flags let you ship modules progressively and disable anything unstable minutes before a demo — a small piece of insurance that has saved many presentations.

---

## 11. Build Roadmap

Ordered so that something demonstrable exists at every stage. Weeks are indicative for one person working part-time alongside coursework.

### Phase 0 — Foundation (weeks 1–2)
Repo, Docker Compose, FastAPI skeleton, SQLAlchemy base, Alembic, React+Vite+Tailwind shell, CI pipeline, `users`/`roles`/`permissions` schema, JWT auth end to end, login page, protected route guard.
*Milestone: a user can log in and see a role-appropriate empty dashboard.*

### Phase 1 — Core data (weeks 3–4)
Academic years, classes, sections, subjects, teachers, students, guardians, enrollments. Admin CRUD screens, bulk import, **Module 8 (Student Profile)**. Synthetic data generator.
*Milestone: a populated school exists in the database.*

### Phase 2 — Attendance (weeks 5–6)
**Module 1** without ML: sessions, marking UI, locking, summaries, Excel/PDF export, leave applications, holidays.
*Milestone: a teacher can run a full day of attendance on a phone.*

### Phase 3 — Academics (weeks 7–8)
**Module 2** without ML: exams, marks entry, grade scales, result computation, ranks, report card PDF, homework and submissions.
*Milestone: an exam cycle completes end to end.*

### Phase 4 — Analytics (week 9)
**Module 5**: summary tables, aggregation jobs, dashboards, drill-down, caching.
*Milestone: the principal's dashboard is populated and fast.*

### Phase 5 — ML layer (weeks 10–12)
Feature builders, attendance risk model, academic risk model, clustering, SHAP explanations, model registry, prediction logging, retraining tasks, UI surfaces.
*Milestone: explainable at-risk lists appear in the teacher and principal views.*

### Phase 6 — Fees (weeks 13–14)
**Module 3**: structures, concessions, invoices, payments, receipts, ledger, dues dashboard, gateway integration.
*Milestone: a payment produces a downloadable receipt.*

### Phase 7 — Timetable (weeks 15–16)
**Module 4**: slots, rooms, availability, CP-SAT solver, infeasibility diagnostics, versions, approval, publication, substitutions.
*Milestone: a conflict-free timetable generates and publishes to all roles.*

### Phase 8 — Question papers (weeks 17–18)
**Module 6**: question bank, bulk import, embeddings, duplicate detection, blueprints, selection solver, PDF output, difficulty calibration.
*Milestone: a balanced paper generates from a blueprint with an answer key.*

### Phase 9 — Notifications (week 19)
**Module 7**: templates, preferences, Celery fan-out, email + in-app, half-day alerts, delivery log. SMS behind a flag.
*Milestone: posting homework notifies parents.*

### Phase 10 — Public site & polish (week 20)
Public pages, responsive audit, accessibility audit, empty and error states, loading skeletons.

### Phase 11 — Hardening (weeks 21–22)
Security test suite, load testing, performance tuning, backup drill, documentation, deployment to staging then production.

### Phase 12 — Report & presentation (weeks 23–24)
Project report, ER and UML diagrams, ML results chapter, demo script, fallback recording.

**If you fall behind — and you probably will — cut in this order:** Module 6, then Module 4, then online payments within Module 3. Keep 1, 2, 5 and 8 at full quality. A project with four excellent modules and honest scope documentation scores better than eight shallow ones.

---

## 12. Report Structure

1. Introduction — problem, objectives, scope
2. Literature survey — existing SMS products (Christ KP, ESPRO, Fedena, Teachmint) and academic work on attendance/performance prediction and timetabling
3. System analysis — requirements, feasibility, stakeholder interviews
4. System design — architecture, ER diagram, UML (use case, class, sequence, activity), DFD
5. Technology selection — stack comparison with justification
6. Implementation — module by module, key algorithms
7. Machine learning — problem framing, features, models, results, error analysis (follow `03-ML-MODELS.md` §9)
8. Testing — strategy, cases, coverage, security testing
9. Deployment — architecture, CI/CD, monitoring
10. Security & privacy — RBAC, DPDP compliance, ethical boundaries
11. Results & discussion — screenshots, performance measurements, model metrics
12. Limitations & future work
13. Conclusion
14. References
15. Appendices — API documentation, schema DDL, key code listings

Chapters 7 and 10 carry the AI & Data Science identity of the project. Give them the most attention.

---

*The scaffold in `backend/` and `frontend/` implements these patterns. See the root `README.md` for what is built versus stubbed.*
