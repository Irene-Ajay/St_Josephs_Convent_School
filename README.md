# St. Joseph's Convent School — Service Learning Project

Technical support delivered to St. Joseph's Convent School: a digital
attendance and student-records system, built after visiting the school and
identifying the problems staff actually face.

---

## Start here

**If you want to run the system:** go to
[`school-system/`](school-system/) and read its
[`README.md`](school-system/README.md).

**If you are school staff setting this up:** read
[`school-system/SETUP.md`](school-system/SETUP.md). It assumes no technical
knowledge.

**If you are marking or reviewing this project:** read this file, then
[`docs/`](docs/).

---

## What is in this folder

| Folder | What it is | Status |
|---|---|---|
| **`school-system/`** | **The real deliverable.** The system the school uses. | ✅ Working, 19 end-to-end checks pass |
| `docs/` | Design documentation for a full-scale architecture | ✅ Complete (6 documents) |
| `ml-reference/` | ML and optimisation code, standalone | ✅ 11 tests pass — not yet wired into the system |

57 files in total. An earlier partial build of the full-scale architecture
(`backend/`, `frontend/`, Docker and CI configuration — 157 files) was
deleted once the simpler system replaced it. The design reasoning survives in
`docs/`; the machine-learning code survives in `ml-reference/`.

---

## Why there are two systems

This is the central engineering decision of the project, and it belongs in
the report.

We first designed a full production architecture: PostgreSQL, Redis, Celery,
Docker, MinIO, cloud deployment, CI/CD, eight modules, machine learning
throughout. That design is documented in `docs/`, and roughly 40% of it was
built before we stopped.

We then abandoned it. Not because it was wrong, but because it was wrong
**for this school**:

| Question | Full architecture | What we built |
|---|---|---|
| Who restarts it when it fails? | Needs someone who understands Docker and Celery | Close the window, run one command |
| What does it cost per month? | ₹1,500–3,500, forever | ₹0 |
| How do you back it up? | Managed database snapshots | Copy one file to a pen drive |
| How many dependencies? | 66 | 9 |
| Who maintains it after we graduate? | Unanswered | A written manual and one file |

A school left with a system nobody can maintain is worse off than before the
project arrived. Recognising that, and deliberately building **less**, is the
main finding of this project.

The design documents are kept because the comparison *is* the argument. Being
able to show what was considered and rejected — and why — is stronger evidence
of engineering judgement than the complex system would have been.

---

## What the working system does

Built around what school staff told us they struggle with.

| Problem observed at the school | What the system does |
|---|---|
| Paper attendance registers, slow to total | One-tap marking on a phone; percentages calculated automatically |
| Nobody notices a child missing repeatedly until it is serious | Flags consecutive absences and students below the requirement |
| Parents not informed the same day | Absence list with phone numbers; one-click WhatsApp; optional automatic email |
| Student details scattered across registers | One searchable record per student, imported from the school's existing Excel |
| Attendance reports compiled by hand | Excel register generated on demand |

Verified by testing: Excel import handles messy real-world spreadsheets;
re-importing does not duplicate; a teacher cannot open another class's data
even by editing the address bar.

---

## Deliberately not built

Each was excluded for a stated reason, not overlooked.

- **Automatic SMS** — Indian law (TRAI) requires DLT registration by the
  school: about ₹5,900 + GST, 3–7 working days, and the school's own legal
  documents. WhatsApp achieves the same result today at no cost.
- **Fee management** — handling money needs audit and reconciliation the
  school did not ask for.
- **Detailed medical records** — sensitive health data about minors cannot be
  adequately protected in a system with no full-time administrator. Only
  allergy and emergency information is collected.
- **Cloud hosting** — creates a permanent bill and an account someone must own
  after the project team leaves.

---

## Documentation

| File | Contents |
|---|---|
| [`school-system/README.md`](school-system/README.md) | The working system: features, design, limitations |
| [`school-system/SETUP.md`](school-system/SETUP.md) | Installation guide written for school staff |
| [`docs/00-ARCHITECTURE.md`](docs/00-ARCHITECTURE.md) | Full-scale design: stack comparison, 8 modules, permissions |
| [`docs/01-DATABASE-SCHEMA.md`](docs/01-DATABASE-SCHEMA.md) | Complete relational schema (~45 tables) |
| [`docs/02-API-CONTRACT.md`](docs/02-API-CONTRACT.md) | REST API specification |
| [`docs/03-ML-MODELS.md`](docs/03-ML-MODELS.md) | ML problem framing, features, metrics, ethics |
| [`docs/04-SECURITY.md`](docs/04-SECURITY.md) | Access control, DPDP Act 2023, privacy |
| [`docs/05-DEPLOYMENT.md`](docs/05-DEPLOYMENT.md) | Testing, deployment, phased roadmap |

---

## Open items

Honest status, to be resolved before handover.

1. **Nobody is yet named as responsible for the system after the project team
   leaves.** This is the largest risk to the project — larger than any missing
   feature. It needs a decision from the school.
2. **The working system contains no machine learning yet.** The subject is
   AI & Data Science, so an analytical component still has to be added. The
   groundwork is in [`ml-reference/`](ml-reference/) — tested and runnable,
   but not yet connected. The obstacle is data, not code: a new system starts
   empty, so either the pilot must run long enough to accumulate attendance
   history, or the school's existing paper registers must be digitised to
   provide it.
3. **Backups are manual.** A weekly file copy, documented in `SETUP.md`.
   Someone at the school must own this habit.
