# School Management System — working version

A deliberately simple attendance and student-records system for
St. Joseph's Convent School, built for a service-learning project.

**This is the version the school actually uses.** The `../backend` and
`../frontend` folders contain a larger reference architecture kept for the
project report; they are not the system being handed over.

---

## Status: working, tested, ready to pilot

| | |
|---|---|
| Verified end-to-end checks | 19 passed |
| Lines of code | ~2,200 |
| Things the school must install | Python, then one command |
| Monthly cost | ₹0 |
| Backup procedure | copy one file |

---

## What works today

**Student records**
- Bulk import from the school's existing Excel list — handles unusual column
  headings, phone numbers Excel has mangled into floats, and three date formats
- Re-importing the same file updates records instead of duplicating them
- Add and view students individually; search by name, admission number or phone

**Attendance**
- One-tap daily marking, everyone defaults to Present so teachers mark only
  the exceptions
- Present / Absent / Late / Half-day / Leave
- Correcting a day updates the record rather than creating a second one
- Running attendance percentage shown next to each student while marking
- Sundays and holidays excluded from percentages

**Parent contact**
- Absent-today list with guardian phone numbers, tap to call
- Absence messages written automatically, escalating wording after 3
  consecutive absences
- One-click WhatsApp (free, works immediately)
- Automatic email once a Gmail App Password is configured
- Every message logged, so no parent is contacted twice for the same day

**Reports**
- Students below the attendance requirement
- Excel attendance register with colour-coded percentages
- Per-student attendance history

**Access control**
- Separate office and teacher roles
- A teacher can only open **their own** classes — verified by test, including
  against someone editing the address bar
- Forced password change on first login
- Activity log of who did what

---

## What is deliberately NOT included

Each of these was left out for a reason, not forgotten.

| Not included | Why |
|---|---|
| Automatic SMS | Requires DLT registration by the school: ~₹5,900 + GST, 3–7 days, and the school's own legal documents. WhatsApp achieves the same outcome today at no cost. See `SETUP.md` Part 5. |
| Marks and report cards | Not yet built. Would be the next module. |
| Fee management | Handling money needs audit trails and reconciliation the school did not ask for. |
| Detailed medical records | We cannot adequately protect sensitive health data about minors in a system with no full-time administrator. Only allergy and emergency information is collected. |
| Timetable generation | Solved in the reference architecture; not needed for the daily problem the school described. |
| Cloud hosting | Adds a permanent monthly bill and an account someone must own after we leave. |

---

## Running it

**Windows: double-click `START.bat`**, wait for the banner, then open
`http://localhost:8000`.

Or manually:

```bash
pip install -r requirements.txt
python run.py
```

If the browser says "This site can't be reached", the system is not running —
see [`HOW-TO-RUN.md`](HOW-TO-RUN.md).

| Guide | For |
|---|---|
| [`HOW-TO-RUN.md`](HOW-TO-RUN.md) | Starting it, and fixing it when it will not start |
| [`SETUP.md`](SETUP.md) | School staff: importing students, creating accounts, training teachers |

```bash
python -m pytest tests/ -v      # re-run the verification suite
```

---

## How it is built

| Layer | Choice | Why |
|---|---|---|
| Language | Python | One language, already needed for the project |
| Web framework | FastAPI | Small, fast, well documented |
| Database | SQLite (one file) | No server to install, back up by copying a file |
| Pages | Server-rendered HTML (Jinja2) | No npm, no build step, nothing to compile |
| Styling | Tailwind via CDN | No build tooling |
| Login | Signed httpOnly cookies | Simpler than tokens, safe for one school |

Total external dependencies: **9**. This is the single most important design
decision in the project — every dependency is something a future maintainer
may one day have to reinstall or debug.

### Files

```
run.py                  start here
app/
  config.py             settings, editable without touching code
  database.py           SQLite connection
  models.py             all 7 tables, in one readable file
  auth.py               login, sessions, access checks
  attendance_utils.py   all attendance maths, defined once
  importer.py           Excel import and export
  notify.py             parent messages
  routers/              the pages
  templates/            the HTML
data/                   school.db lives here — this is your data
tests/                  verification suite
SETUP.md                instructions for school staff
```

---

## Known limitations

State these plainly in the report; they are design decisions, not oversights.

1. **One computer.** The system runs on a single machine on the school
   network. Not accessible from teachers' homes.
2. **Backups are manual.** A weekly file copy. Automating it would need
   infrastructure the school cannot maintain.
3. **No HTTPS on the LAN.** Traffic inside the school network is unencrypted.
   Acceptable for a private LAN; not acceptable if ever exposed to the internet.
4. **SQLite concurrency.** Comfortable for tens of simultaneous users, not
   hundreds.
5. **No automatic SMS**, for the reasons above.
6. **Sustainability is unresolved.** Nobody has yet been named as responsible
   for this system after the project team leaves. This is the largest risk to
   the project and needs a decision from the school.
