# Database Schema — PostgreSQL 16

**Conventions used throughout**

- `snake_case` table and column names; tables plural.
- Primary keys: `UUID` (`gen_random_uuid()`) for externally-exposed entities, `BIGSERIAL` for high-volume internal rows (attendance records, audit logs, delivery logs).
- Every table: `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`.
- Student-facing entities also carry `deleted_at TIMESTAMPTZ` (soft delete) and `created_by`/`updated_by` UUID references.
- Money: `NUMERIC(12,2)`. Never float.
- All timestamps stored UTC.
- Enums as PostgreSQL `ENUM` types where the value set is stable; lookup tables where admins must edit them.

---

## 1. Entity Relationship Overview

```
                    ┌──────────────┐
                    │ academic_    │
                    │   years      │
                    └──────┬───────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
   ┌────▼─────┐      ┌─────▼──────┐     ┌─────▼──────┐
   │ classes  │      │  subjects  │     │ fee_       │
   └────┬─────┘      └─────┬──────┘     │ structures │
        │                  │            └─────┬──────┘
   ┌────▼──────────┐       │                  │
   │ class_        │       │                  │
   │ sections      │◄──────┼──────────┐       │
   └────┬──────────┘       │          │       │
        │                  │          │       │
        │            ┌─────▼──────────▼──┐    │
        │            │ teacher_          │    │
        │            │ assignments       │    │
        │            └─────┬─────────────┘    │
        │                  │                  │
   ┌────▼──────┐     ┌─────▼──────┐           │
   │ students  │────►│ teachers   │           │
   └────┬──────┘     └─────┬──────┘           │
        │                  │                  │
        │            ┌─────▼──────┐           │
        │            │   users    │           │
        │            └────────────┘           │
        │                                     │
   ┌────┼─────────────┬──────────┬────────────┼──────────┐
   │    │             │          │            │          │
┌──▼────▼───┐  ┌──────▼────┐  ┌──▼────────┐ ┌▼────────┐ ┌▼──────────┐
│ attendance│  │  marks    │  │ student_  │ │invoices │ │ homework_ │
│ _records  │  │           │  │ guardians │ │payments │ │ submissions│
└───────────┘  └───────────┘  └───────────┘ └─────────┘ └───────────┘
```

---

## 2. Identity & Access

### `users`
The authentication identity. A person has exactly one `users` row regardless of how many roles they hold.

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| email | CITEXT UNIQUE | nullable — some parents have no email |
| phone | VARCHAR(15) UNIQUE | nullable; E.164 |
| username | VARCHAR(50) UNIQUE | admission no. / employee code for login |
| password_hash | TEXT | Argon2id |
| full_name | VARCHAR(150) NOT NULL | |
| avatar_url | TEXT | |
| is_active | BOOLEAN DEFAULT true | |
| is_verified | BOOLEAN DEFAULT false | |
| must_change_password | BOOLEAN DEFAULT true | true on admin-created accounts |
| failed_login_attempts | SMALLINT DEFAULT 0 | |
| locked_until | TIMESTAMPTZ | |
| last_login_at | TIMESTAMPTZ | |
| password_changed_at | TIMESTAMPTZ | |
| mfa_secret | TEXT | nullable; enforced for ADMIN |

Constraint: `CHECK (email IS NOT NULL OR phone IS NOT NULL)`.
Indexes: `email`, `phone`, `username`, partial `WHERE is_active`.

### `roles`, `permissions`, `role_permissions`, `user_roles`

Standard RBAC. `roles.code` ∈ `ADMIN, PRINCIPAL, TEACHER, STUDENT, PARENT`. `permissions.code` uses `resource:action` (`attendance:write`, `marks:read`, `fees:manage`, `profile:read_medical`).

`user_roles` carries `academic_year_id` (nullable) so a role can be scoped to a year — a teacher who becomes a coordinator for one year only.

### `refresh_tokens`
| Column | Type |
|---|---|
| id | UUID PK |
| user_id | UUID FK → users |
| token_hash | TEXT (SHA-256 of the token; never store raw) |
| expires_at | TIMESTAMPTZ |
| revoked_at | TIMESTAMPTZ |
| user_agent, ip_address | TEXT, INET |

Rotation: each refresh issues a new token and revokes the old. Reuse of a revoked token revokes the entire family (theft detection).

### `audit_logs`
`id BIGSERIAL`, `user_id`, `action`, `entity_type`, `entity_id`, `old_values JSONB`, `new_values JSONB`, `ip_address INET`, `user_agent`, `reason TEXT`, `created_at`.
Partition by month once volume grows. Index on `(entity_type, entity_id)` and `(user_id, created_at DESC)`.

---

## 3. Academic Structure

### `academic_years`
`id`, `name` ('2026-27'), `start_date`, `end_date`, `is_current BOOLEAN`.
Partial unique index: `CREATE UNIQUE INDEX ON academic_years (is_current) WHERE is_current` — guarantees exactly one current year.

### `classes`
`id`, `name` ('Grade 10'), `numeric_level SMALLINT` (10 — sortable), `stream` (nullable: Science/Commerce/Arts), `display_order`.

### `class_sections`
`id`, `class_id`, `academic_year_id`, `section_name` ('A'), `class_teacher_id` FK → teachers, `room_id`, `max_strength`, `current_strength`.
Unique: `(class_id, academic_year_id, section_name)`.

### `subjects`
`id`, `code` UNIQUE, `name`, `subject_type ENUM(CORE, ELECTIVE, LANGUAGE, ACTIVITY)`, `is_lab BOOLEAN`, `credit_hours`.

### `class_subjects`
Which subjects a class studies in a year, and how often.
`id`, `class_id`, `academic_year_id`, `subject_id`, `periods_per_week SMALLINT`, `max_marks`, `pass_marks`, `is_graded BOOLEAN`.

### `teachers`
`id`, `user_id` FK UNIQUE, `employee_code` UNIQUE, `designation`, `department`, `qualification`, `date_of_joining`, `specialization_subject_ids UUID[]`, `max_periods_per_day SMALLINT DEFAULT 6`, `max_periods_per_week SMALLINT DEFAULT 30`, `is_class_teacher BOOLEAN`.

### `teacher_assignments`
**The object-level authorisation table.** Every teacher permission check joins here.
`id`, `teacher_id`, `class_section_id`, `subject_id`, `academic_year_id`, `is_primary BOOLEAN`.
Unique: `(class_section_id, subject_id, academic_year_id)` — one primary teacher per subject per section.

---

## 4. Students & Profiles (Module 8)

### `students`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| user_id | UUID FK UNIQUE | nullable until portal access is granted |
| admission_number | VARCHAR(30) UNIQUE NOT NULL | |
| roll_number | VARCHAR(20) | unique within section-year |
| first_name, middle_name, last_name | VARCHAR | |
| date_of_birth | DATE NOT NULL | |
| gender | ENUM(MALE, FEMALE, OTHER, PREFER_NOT_TO_SAY) | |
| blood_group | VARCHAR(5) | |
| nationality, mother_tongue, religion, category | VARCHAR | all nullable — religion and category must be optional |
| aadhaar_last4 | CHAR(4) | **never store the full number** |
| aadhaar_hash | TEXT | SHA-256 + per-record salt, for duplicate detection only |
| photo_url | TEXT | |
| admission_date | DATE NOT NULL | |
| admission_class_id | UUID FK | |
| previous_school, tc_number | TEXT | |
| house | VARCHAR(30) | Red/Blue/Green/Yellow |
| status | ENUM(ACTIVE, TRANSFERRED, GRADUATED, DROPPED, SUSPENDED) | |
| transport_required | BOOLEAN | |
| distance_from_school_km | NUMERIC(5,2) | a real feature in the attendance model |
| sibling_group_id | UUID | links siblings for concessions and analytics |

### `student_enrollments`
Students change section every year — this is the historical record and the join key for all year-scoped queries.
`id`, `student_id`, `class_section_id`, `academic_year_id`, `roll_number`, `enrolled_on`, `status`.
Unique: `(student_id, academic_year_id)`.

> **Design note.** Do not put `class_section_id` on `students`. Doing so makes last year's marks and attendance unqueryable by class. This single decision is the most common irreversible schema mistake in school projects.

### `guardians`
`id`, `user_id` (nullable), `full_name`, `relationship ENUM(FATHER, MOTHER, GUARDIAN, OTHER)`, `occupation`, `qualification`, `organization`, `annual_income_band ENUM(...)`, `phone`, `alternate_phone`, `email`, `is_primary_contact`, `is_emergency_contact`, `photo_url`.

### `student_guardians`
Junction: `student_id`, `guardian_id`, `relationship`, `is_primary`, `can_pickup BOOLEAN`, `priority SMALLINT`.
Many-to-many is required — one guardian can have three children in the school.

### `student_addresses`
`student_id`, `address_type ENUM(PERMANENT, CORRESPONDENCE)`, `line1`, `line2`, `city`, `district`, `state`, `pincode`, `country`, `latitude`, `longitude`.

### `student_medical_records` — **restricted access**
`student_id`, `blood_group`, `height_cm`, `weight_kg`, `allergies TEXT[]`, `chronic_conditions TEXT[]`, `current_medications TEXT[]`, `physician_name`, `physician_phone`, `special_needs TEXT`, `emergency_instructions TEXT`, `vaccination_record JSONB`, `last_updated_by`.

Teachers do **not** select from this table. They read a view:
```sql
CREATE VIEW v_student_emergency_summary AS
SELECT student_id, blood_group, allergies, emergency_instructions
FROM student_medical_records;
```
Every direct read of `student_medical_records` writes an `audit_logs` row.

### `student_notes`
`id`, `student_id`, `author_id`, `category ENUM(ACADEMIC, BEHAVIOURAL, ACHIEVEMENT, DISCIPLINARY, COUNSELLING, GENERAL)`, `title`, `content TEXT`, `visibility ENUM(ALL_STAFF, ADMIN_ONLY, COUNSELLOR_ONLY)`, `is_parent_visible BOOLEAN`, `occurred_on DATE`.
Append-only; edits create a new version row rather than mutating.

### `student_documents`
`student_id`, `document_type`, `file_key` (object-storage key, not a public URL), `file_name`, `mime_type`, `size_bytes`, `uploaded_by`, `verified_by`, `verified_at`.

---

## 5. Attendance (Module 1)

### `attendance_sessions`
One row per (section, subject, date, period) that a teacher opens.

| Column | Type |
|---|---|
| id | UUID PK |
| class_section_id | UUID FK |
| subject_id | UUID FK (nullable for day-wise attendance) |
| academic_year_id | UUID FK |
| session_date | DATE NOT NULL |
| period_number | SMALLINT |
| session_type | ENUM(DAILY, PERIOD, EVENT) |
| marked_by | UUID FK → teachers |
| marked_at | TIMESTAMPTZ |
| locked_at | TIMESTAMPTZ |
| is_holiday | BOOLEAN |
| total_present, total_absent, total_strength | SMALLINT (denormalised counts) |

Unique: `(class_section_id, session_date, period_number, subject_id)`.
Index: `(session_date DESC, class_section_id)`.

### `attendance_records`
`id BIGSERIAL`, `session_id`, `student_id`, `status ENUM(PRESENT, ABSENT, LATE, HALF_DAY, EXCUSED, ON_LEAVE)`, `remarks`, `minutes_late SMALLINT`, `marked_by`, `modified_by`, `modification_reason`.
Unique: `(session_id, student_id)`. Index: `(student_id, session_id)`.

### `attendance_summary` — pre-aggregated
Refreshed nightly by Celery and incrementally on write. The dashboard reads only this table.
`student_id`, `academic_year_id`, `subject_id` (NULL = overall), `month DATE`, `total_sessions`, `present_count`, `absent_count`, `late_count`, `half_day_count`, `attendance_percentage NUMERIC(5,2)`, `last_computed_at`.
Unique: `(student_id, academic_year_id, subject_id, month)`.

### `leave_applications`
`student_id`, `from_date`, `to_date`, `reason`, `leave_type ENUM(SICK, CASUAL, EMERGENCY, OTHER)`, `applied_by` (guardian), `status ENUM(PENDING, APPROVED, REJECTED)`, `approved_by`, `attachment_key`.

### `holidays`
`academic_year_id`, `date`, `name`, `holiday_type ENUM(NATIONAL, RELIGIOUS, SCHOOL, VACATION, HALF_DAY)`, `applies_to_class_ids UUID[]` (NULL = all).
Feeds both the attendance denominator and the half-day alert in Module 7.

---

## 6. Academics & Performance (Module 2)

### `exams`
`id`, `name` ('Mid-Term I'), `exam_type ENUM(UNIT_TEST, MID_TERM, FINAL, PRACTICAL, ASSIGNMENT, PROJECT)`, `academic_year_id`, `term SMALLINT`, `start_date`, `end_date`, `weightage NUMERIC(5,2)`, `is_published BOOLEAN`, `published_at`.

### `exam_schedules`
`exam_id`, `class_section_id`, `subject_id`, `exam_date`, `start_time`, `duration_minutes`, `max_marks`, `pass_marks`, `room_id`.

### `marks`
`id BIGSERIAL`, `exam_id`, `student_id`, `subject_id`, `class_section_id`, `marks_obtained NUMERIC(6,2)`, `max_marks NUMERIC(6,2)`, `is_absent BOOLEAN`, `grade VARCHAR(3)`, `grade_point NUMERIC(3,1)`, `remarks`, `entered_by`, `verified_by`, `verified_at`.
Unique: `(exam_id, student_id, subject_id)`.
`CHECK (marks_obtained >= 0 AND marks_obtained <= max_marks)`.
Index: `(student_id, exam_id)`, `(class_section_id, exam_id, subject_id)`.

### `grade_scales`
`academic_year_id`, `name`, `min_percentage`, `max_percentage`, `grade`, `grade_point`, `description`, `is_pass BOOLEAN`.
Grading is data, not code.

### `exam_results` — computed per student per exam
`exam_id`, `student_id`, `total_marks`, `total_max_marks`, `percentage`, `grade`, `gpa`, `rank_in_section`, `rank_in_class`, `subjects_passed`, `subjects_failed`, `result_status ENUM(PASS, FAIL, PENDING, WITHHELD)`.

Rank computation:
```sql
UPDATE exam_results er SET rank_in_section = r.rnk
FROM (
  SELECT id, RANK() OVER (
    PARTITION BY exam_id, class_section_id ORDER BY percentage DESC
  ) AS rnk
  FROM exam_results WHERE exam_id = :exam_id
) r WHERE er.id = r.id;
```

### `homework` / `assignments`
`id`, `class_section_id`, `subject_id`, `teacher_id`, `title`, `description`, `attachment_keys TEXT[]`, `assigned_date`, `due_date`, `max_marks`, `submission_type ENUM(ONLINE, OFFLINE, NONE)`, `is_published`.

### `homework_submissions`
`homework_id`, `student_id`, `submitted_at`, `file_keys TEXT[]`, `text_response`, `status ENUM(PENDING, SUBMITTED, LATE, GRADED, MISSING)`, `marks_obtained`, `feedback`, `graded_by`, `graded_at`.
Unique: `(homework_id, student_id)`.

---

## 7. Fees (Module 3)

### `fee_categories`
`id`, `name` ('Tuition', 'Transport', 'Lab'), `code` UNIQUE, `is_recurring`, `is_optional`, `display_order`.

### `fee_structures`
`id`, `academic_year_id`, `class_id`, `fee_category_id`, `amount NUMERIC(12,2)`, `frequency ENUM(ANNUAL, TERM, MONTHLY, ONE_TIME)`, `is_active`.
Unique: `(academic_year_id, class_id, fee_category_id)`.

### `fee_installments`
`fee_structure_id`, `installment_number`, `label` ('Term 1'), `amount`, `due_date`, `late_fee_per_day NUMERIC(8,2)`, `grace_days SMALLINT`.

### `student_fee_assignments`
Which fee items apply to which student (handles optional transport, electives).
`student_id`, `academic_year_id`, `fee_structure_id`, `is_applicable BOOLEAN`, `custom_amount` (nullable override), `remarks`.

### `concessions`
`student_id`, `academic_year_id`, `fee_category_id` (NULL = all), `concession_type ENUM(PERCENTAGE, FLAT)`, `value NUMERIC(10,2)`, `reason ENUM(SIBLING, MERIT, STAFF_WARD, FINANCIAL_NEED, MANAGEMENT, OTHER)`, `approved_by`, `approved_at`, `valid_from`, `valid_to`.

### `invoices`
`id`, `invoice_number` UNIQUE (sequence-generated), `student_id`, `academic_year_id`, `installment_id`, `gross_amount`, `concession_amount`, `late_fee`, `net_amount`, `paid_amount`, `balance_amount`, `due_date`, `status ENUM(DRAFT, ISSUED, PARTIALLY_PAID, PAID, OVERDUE, CANCELLED, WAIVED)`, `issued_at`.

### `payments`
`id`, `payment_reference` UNIQUE, `invoice_id`, `student_id`, `amount NUMERIC(12,2)`, `payment_date`, `payment_mode ENUM(CASH, CHEQUE, DD, UPI, CARD, NETBANKING, ONLINE_GATEWAY)`, `transaction_id`, `gateway_name`, `gateway_response JSONB`, `cheque_number`, `cheque_date`, `bank_name`, `status ENUM(PENDING, SUCCESS, FAILED, REFUNDED, BOUNCED)`, `idempotency_key VARCHAR(64) UNIQUE`, `collected_by`, `remarks`.

`idempotency_key UNIQUE` is what prevents a double-clicked payment button from charging twice.

### `receipts`
`payment_id`, `receipt_number` UNIQUE, `issued_at`, `issued_by`, `pdf_key`, `is_cancelled`, `cancellation_reason`.
Immutable — corrections issue a credit note, never an edit.

### `fee_ledger` (view)
```sql
CREATE VIEW v_student_fee_ledger AS
SELECT s.id AS student_id, i.academic_year_id,
       SUM(i.gross_amount)      AS total_charged,
       SUM(i.concession_amount) AS total_concession,
       SUM(i.paid_amount)       AS total_paid,
       SUM(i.balance_amount)    AS outstanding
FROM students s
JOIN invoices i ON i.student_id = s.id AND i.status <> 'CANCELLED'
GROUP BY s.id, i.academic_year_id;
```

---

## 8. Timetable (Module 4)

### `time_slots`
`academic_year_id`, `day_of_week SMALLINT` (1=Mon), `period_number`, `start_time`, `end_time`, `slot_type ENUM(TEACHING, BREAK, LUNCH, ASSEMBLY)`.

### `rooms`
`id`, `name`, `room_type ENUM(CLASSROOM, LAB, HALL, LIBRARY, SPORTS)`, `capacity`, `building`, `floor`, `has_projector`.

### `teacher_availability`
`teacher_id`, `academic_year_id`, `day_of_week`, `period_number`, `is_available BOOLEAN`, `preference_score SMALLINT` (-2 dislike … +2 prefer), `reason`.

### `timetable_versions`
`id`, `academic_year_id`, `name`, `generated_at`, `generated_by`, `algorithm` ('CP-SAT'), `solver_status` ('OPTIMAL' / 'FEASIBLE' / 'INFEASIBLE'), `solve_time_seconds`, `hard_constraint_violations SMALLINT`, `soft_penalty_score NUMERIC`, `quality_metrics JSONB`, `status ENUM(DRAFT, UNDER_REVIEW, APPROVED, PUBLISHED, ARCHIVED)`, `approved_by`, `effective_from`, `effective_to`.

### `timetable_entries`
`version_id`, `class_section_id`, `subject_id`, `teacher_id`, `room_id`, `day_of_week`, `period_number`, `is_double_period`.
Unique constraints that mirror the solver's hard constraints (defence in depth — the database refuses a clash even if the solver is buggy):
```sql
UNIQUE (version_id, teacher_id,        day_of_week, period_number)
UNIQUE (version_id, class_section_id,  day_of_week, period_number)
UNIQUE (version_id, room_id,           day_of_week, period_number)
```

### `substitutions`
`timetable_entry_id`, `date`, `original_teacher_id`, `substitute_teacher_id`, `reason`, `arranged_by`.

---

## 9. Question Bank (Module 6)

### `question_bank`
| Column | Type |
|---|---|
| id | UUID PK |
| subject_id | UUID FK |
| class_id | UUID FK |
| chapter, topic | VARCHAR |
| question_text | TEXT NOT NULL |
| question_type | ENUM(MCQ, TRUE_FALSE, FILL_BLANK, SHORT_ANSWER, LONG_ANSWER, NUMERICAL, DIAGRAM, MATCH) |
| options | JSONB (MCQ choices) |
| correct_answer | TEXT |
| answer_explanation | TEXT |
| marks | SMALLINT |
| difficulty | ENUM(EASY, MEDIUM, HARD) |
| empirical_difficulty | NUMERIC(4,3) — observed failure rate, updated from `marks` |
| blooms_level | ENUM(REMEMBER, UNDERSTAND, APPLY, ANALYZE, EVALUATE, CREATE) |
| expected_time_minutes | SMALLINT |
| embedding | VECTOR(384) — pgvector, for duplicate detection |
| image_keys | TEXT[] |
| source | VARCHAR (textbook / previous year / custom / AI-generated) |
| is_ai_generated | BOOLEAN |
| is_approved | BOOLEAN — AI-generated questions require teacher approval |
| usage_count | INT DEFAULT 0 |
| last_used_at | TIMESTAMPTZ |
| created_by | UUID |

Enable `pgvector`: `CREATE EXTENSION vector;` then an HNSW index on `embedding` for fast similarity search.

### `paper_blueprints`
`id`, `name`, `subject_id`, `class_id`, `exam_type`, `total_marks`, `duration_minutes`, `section_config JSONB`, `difficulty_distribution JSONB` (`{"EASY":0.3,"MEDIUM":0.5,"HARD":0.2}`), `blooms_distribution JSONB`, `chapter_weightage JSONB`, `created_by`.

### `generated_papers`
`id`, `blueprint_id`, `title`, `exam_id`, `set_code` ('A'), `generation_params JSONB`, `pdf_key`, `answer_key_pdf_key`, `status ENUM(DRAFT, REVIEWED, APPROVED, USED, ARCHIVED)`, `generated_by`, `approved_by`.

### `paper_questions`
`paper_id`, `question_id`, `section_label`, `question_number`, `marks_allotted`, `is_optional`, `option_group` (for "attempt any 5 of 7").

---

## 10. Notifications (Module 7)

### `notification_templates`
`id`, `code` UNIQUE ('HOMEWORK_ASSIGNED'), `name`, `category`, `channel ENUM(IN_APP, EMAIL, SMS, PUSH)`, `subject_template`, `body_template` (Jinja2), `variables JSONB` (documented placeholders), `dlt_template_id` (India SMS compliance), `is_active`.

### `notifications`
`id`, `template_code`, `category ENUM(HOMEWORK, EXAM, ATTENDANCE, FEE, ANNOUNCEMENT, RESULT, EMERGENCY, GENERAL)`, `title`, `body`, `data JSONB` (deep-link payload), `priority ENUM(LOW, NORMAL, HIGH, URGENT)`, `created_by`, `scheduled_for`, `expires_at`.

### `notification_recipients`
`notification_id`, `user_id`, `is_read`, `read_at`, `is_archived`.
Index: `(user_id, is_read, created_at DESC)` — powers the bell badge.

### `notification_preferences`
`user_id`, `category`, `in_app BOOLEAN`, `email BOOLEAN`, `sms BOOLEAN`, `push BOOLEAN`, `quiet_hours_start TIME`, `quiet_hours_end TIME`.

### `delivery_log`
`id BIGSERIAL`, `notification_id`, `user_id`, `channel`, `recipient_address`, `provider`, `provider_message_id`, `status ENUM(QUEUED, SENT, DELIVERED, FAILED, BOUNCED)`, `attempt_count`, `error_message`, `cost NUMERIC(8,4)`, `idempotency_key VARCHAR(64) UNIQUE`, `sent_at`, `delivered_at`.

### `announcements`
`title`, `content`, `audience_roles TEXT[]`, `audience_class_ids UUID[]`, `attachment_keys`, `publish_at`, `expires_at`, `is_pinned`, `created_by`.

---

## 11. ML Support Tables

### `ml_models`
`id`, `name` ('attendance_risk'), `version` ('v3'), `algorithm`, `hyperparameters JSONB`, `metrics JSONB` (precision/recall/F1/PR-AUC per class), `feature_names TEXT[]`, `training_rows INT`, `trained_at`, `artifact_key`, `is_active BOOLEAN`, `notes`.
Partial unique index: one active model per name.

### `predictions`
`id BIGSERIAL`, `model_id`, `student_id`, `prediction_type`, `predicted_value JSONB`, `confidence NUMERIC(4,3)`, `explanation JSONB` (SHAP top-k features), `predicted_at`, `actual_value JSONB` (backfilled later), `was_correct BOOLEAN`.

> Storing `actual_value` and backfilling it is what lets you show *measured production accuracy* rather than only a validation-set number. This is a strong point in a viva and almost no student project does it.

---

## 12. Critical Indexes

```sql
-- Attendance dashboards
CREATE INDEX idx_att_records_student   ON attendance_records (student_id, session_id);
CREATE INDEX idx_att_sessions_date_sec ON attendance_sessions (session_date DESC, class_section_id);
CREATE INDEX idx_att_summary_lookup    ON attendance_summary (student_id, academic_year_id, month DESC);

-- Marks and results
CREATE INDEX idx_marks_student_exam    ON marks (student_id, exam_id);
CREATE INDEX idx_marks_section_exam    ON marks (class_section_id, exam_id, subject_id);
CREATE INDEX idx_results_rank          ON exam_results (exam_id, class_section_id, percentage DESC);

-- Fees
CREATE INDEX idx_invoices_outstanding  ON invoices (student_id, status)
  WHERE status IN ('ISSUED','PARTIALLY_PAID','OVERDUE');
CREATE INDEX idx_invoices_due          ON invoices (due_date) WHERE status <> 'PAID';

-- Enrollment joins (used by nearly every query)
CREATE INDEX idx_enroll_year_section   ON student_enrollments (academic_year_id, class_section_id);

-- Notifications
CREATE INDEX idx_notif_unread          ON notification_recipients (user_id, is_read, created_at DESC);

-- Question bank similarity
CREATE INDEX idx_qb_embedding ON question_bank USING hnsw (embedding vector_cosine_ops);

-- Audit
CREATE INDEX idx_audit_entity          ON audit_logs (entity_type, entity_id, created_at DESC);
```

---

## 13. Seed Data Required for a Working Demo

1. One `academic_years` row with `is_current = true`
2. `roles` + `permissions` + `role_permissions`
3. `grade_scales` for the current year
4. `classes` (Grade 1–12) and `class_sections` (A/B/C)
5. `subjects` and `class_subjects` with `periods_per_week`
6. `time_slots` (Mon–Sat, 8 periods, break and lunch)
7. `fee_categories` and `fee_structures`
8. `notification_templates`
9. Realistic synthetic students, guardians, enrollments, attendance and marks — **with correlations built in** (attendance should genuinely correlate with marks, or the ML models will learn nothing and the demo will be hollow)

The synthetic data generator is a deliverable, not a throwaway script. Document its distributional assumptions in the report.

---

*Next: `02-API-CONTRACT.md`*
