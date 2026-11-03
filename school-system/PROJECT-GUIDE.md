# Project Guide — everything in one place

One reference covering: what exists, how to run it, and how student data gets in.

---

# PART 1 — What is implemented

## Status

| | |
|---|---|
| Works end to end | Yes |
| Pages | 16 |
| Database tables | 9 |
| Dependencies | 9 |
| Files | 42 |
| Tests passing | 19 system + 10 handover + 11 ML |
| Monthly cost | ₹0 |

## Feature list

### Accounts and access
- Office creates teacher accounts through the interface — no programmer needed
- Password generated automatically, shown **once**, forced change at first login
- Password reset by the office
- Deactivate staff who leave (never delete — their name stays on the attendance they marked)
- **Only two roles exist: Teacher and Office/Admin.** No student or parent login at all
- Activity log recording who did what

### Classes
- Create classes, or let the Excel import create them automatically
- Assign a class teacher from a dropdown
- **Assigning the class teacher IS the access control** — a teacher can only see and mark the classes assigned to them

### Student records
- Bulk import from Excel (see Part 3)
- Add students one at a time
- Search by name, admission number or phone
- Student detail page: contact details, attendance percentage, recent history

### Attendance
- One-tap marking; everyone defaults to Present so only exceptions are marked
- Five statuses: Present, Absent, Late, Half-day, Leave
- Re-marking a day corrects it instead of duplicating
- Running attendance percentage shown next to each name while marking
- Sundays and holidays excluded from percentages
- Half-day counts as 0.5; Late and approved Leave count as present

### Parent contact
- Absent-today list with guardian phone numbers, tap to call
- Absence message written automatically; wording escalates after 3 consecutive absences
- One-click WhatsApp (free, works immediately)
- Automatic email once a Gmail App Password is configured
- Every message logged so no parent is contacted twice for the same day

### Academic years and permanent batch records
- Every student and attendance record is tagged with an academic year
- `enrollments` keeps one row per student **per year** — the historical record
- **Past records** page: open any year's classes and students, forever
- **Promotion** page at year end: move a class up, hold individuals back, or
  mark them graduated. Last year's rows are never touched — new rows are created
- Students are never deleted; those who leave stay in the year they studied
- Each student's page shows their full school career, year by year

### Backups
- Automatic: once at startup, once daily; 30 daily + 12 monthly copies kept
- Uses SQLite's online backup API, so backups are never corrupt half-copies
- Optional second copy to a pen drive or the school's own cloud folder
- "Back up now" button and last-run status on the Settings page

### Reports
- Students below the attendance requirement
- Excel attendance register with colour-coded percentages
- Per-student attendance history

### Security (verified by test)
- A teacher gets **403** on another class's attendance, even typing the URL directly
- A teacher gets **403** on Staff, Classes, Import and Settings
- Identical error message for wrong password and unknown username (no account discovery)
- Passwords hashed with bcrypt, never stored or recoverable

## Not implemented — and why

| Not built | Reason |
|---|---|
| Automatic SMS | India's TRAI rules require DLT registration **by the school**: ~₹5,900 + GST, 3–7 working days, and the school's own legal documents. WhatsApp does the same job today at no cost. |
| Marks / report cards | Not yet built. Would be the next module. |
| Fee management | Handling money needs audit trails the school did not ask for. |
| Detailed medical records | Sensitive health data about minors cannot be adequately protected in a system with no full-time administrator. Only allergies and emergency contact are collected. |
| Timetable generation | Solved in `../ml-reference/`, but not the daily problem the school described. |
| Machine learning | Code is ready in `../ml-reference/` but not connected — a new system has no history to learn from. |
| Cloud hosting | Creates a permanent bill and an account someone must own after the project team leaves. Supabase's free tier pauses projects after 7 days idle — the system would be dead after every school holiday — and has no backups. Pro is ~₹26,000/year. |

## Known gaps to fix

1. **No "edit student" screen.** Correct the spreadsheet and import again.
2. **Holidays cannot be added through the interface.** Only Sundays are auto-excluded.
3. **No admin password recovery.** If the office admin forgets their password, only a programmer can fix it. **Create a second admin account as insurance.**

---

## How devices connect

The database is **not** on each device. It lives on the one computer running
`START.bat`; every other device talks to it over the school WiFi. Everyone
sees the same live data instantly.

```
   Teacher's phone  ┐
   Office laptop    ├── school WiFi ──▶  PC running START.bat
   Principal's iPad ┘                     └── data/school.db
```

Nothing leaves the school. No internet is needed for the system itself.

## How long the data lasts

Indefinitely. 1,000 students × 200 school days × 10 years ≈ 2 million rows ≈
**200 MB** — trivial for SQLite. The constraint was never storage size; it was
having a year dimension, which the `academic_years` and `enrollments` tables
now provide.

---

# PART 2 — How to run it

## First time only

**1. Check Python is installed.** Press Windows key, type `cmd`, Enter, then:

```
python --version
```

If it says `'python' is not recognized`, install from **python.org/downloads** and
**tick "Add python.exe to PATH"** on the first screen. Restart the computer.

**2. Double-click `START.bat`** in the `school-system` folder.

The first run installs components — 2–3 minutes, once only.

## Every time after

Double-click **`START.bat`**. Starts in about 3 seconds.

## What you should see

```
========================================================
  SCHOOL MANAGEMENT SYSTEM
========================================================
  On this computer:      http://localhost:8000
  On the school WiFi:    http://192.168.1.14:8000

  Keep this window open while the system is in use.
  Press Ctrl+C to stop.
========================================================
```

The very first time it also prints your login:

```
====================================================
  FIRST-TIME SETUP COMPLETE
  Username: admin
  Password: a2Wy1QyQexKE
====================================================
```

**Write that down.** It is random, different every time, and shown once.
Also saved to `data\FIRST_LOGIN.txt`.

## Then open the browser

| Where | Address |
|---|---|
| This computer | `http://localhost:8000` |
| Teachers' phones (same WiFi) | the second address, e.g. `http://192.168.1.14:8000` |

**Leave the black window open.** Closing it stops the system and the browser
will say "This site can't be reached". Minimise it instead.

## To stop

Click the black window, press **Ctrl+C**.

## When it will not start

| What you see | Cause and fix |
|---|---|
| Window flashes and closes | Python not on PATH — reinstall, tick the box |
| "This site can't be reached" | The black window is not open |
| "Port 8000 is already in use" | Already running in another window |
| "password cannot be longer than 72 bytes" | Old library. Run `pip uninstall -y passlib` then `pip install -r requirements.txt` |
| Module not found after installing | Wrong Python interpreter. Use `python -m pip install -r requirements.txt` |

## Running from an IDE (VS Code, Antigravity)

Same thing, different window. Open the folder, open a terminal
(**Ctrl + `**), then:

```
cd school-system
python -m pip install -r requirements.txt
python run.py
```

Use `python -m pip` rather than plain `pip` so packages install into the same
interpreter that runs the app.

---

# PART 3 — Importing student details

## Where the data lives

Everything is in **one file**:

```
school-system\data\school.db
```

Created automatically on first run. Nothing goes to the internet. Backing up
means copying that one file.

## How importing works

```
your_students.xlsx  ──read once──▶  school.db
     (can delete)                   (the real record)
```

The import is a **one-time copy**, not a link. After importing you can delete
the spreadsheet — the data lives in the database. Editing the spreadsheet
later changes nothing unless you import it again.

## Step by step

1. Sign in as Office/Admin
2. Click **Import** in the menu
3. Click **Download blank template**
4. Open it in Excel. Paste in the school's existing student list, or type it
5. Save the file
6. Back in the browser, choose the file and click **Import**
7. You will see how many were added, updated and skipped

## The columns

Only **two** are compulsory.

| # | Column | Required? | Example |
|---|---|---|---|
| 1 | **Admission Number** | ✅ required | `2026001` |
| 2 | Roll Number | optional | `1` |
| 3 | **Name** | ✅ required | `Ananya Maria Jose` |
| 4 | Class | optional | `Class 8` |
| 5 | Division | optional | `A` |
| 6 | Date of Birth | optional | `15-04-2012` |
| 7 | Gender | optional | `Female` |
| 8 | Blood Group | optional | `O+` |
| 9 | Father Name | optional | `Jose Mathew` |
| 10 | Mother Name | optional | `Maria Jose` |
| 11 | Phone | optional | `9876543210` |
| 12 | Alternate Phone | optional | `9876500011` |
| 13 | Email | optional | `jose@gmail.com` |
| 14 | Address | optional | `Kalathipady, Kottayam` |
| 15 | Admission Date | optional | `01-06-2019` |
| 16 | Allergies / Medical | optional | `Peanut allergy` |
| 17 | Emergency Contact | optional | `Uncle - 9876511111` |

> **Fill in Phone even though it is optional.** It is what makes the whole
> absence-notification feature work. No number means no WhatsApp link and no
> call button. If you import only three things, make them Admission Number,
> Name and Phone.

## You do not have to use the template

The school's existing list probably works as-is. These headings are also
recognised:

| Standard | Also accepted |
|---|---|
| Admission Number | `Adm No`, `Admission No` |
| Name | `Student Name`, `Full Name` |
| Class | `Standard` |
| Division | `Section` |
| Date of Birth | `DOB` |
| Phone | `Mobile`, `Contact Number`, `Guardian Phone` |
| Father Name | `Father` |
| Mother Name | `Mother` |

Matching ignores capitals, spaces and underscores. **Column order does not
matter.** Unrecognised columns are ignored.

## What happens automatically

| Situation | What the system does |
|---|---|
| Class and Division filled in | Creates the class if it does not exist |
| Date written three different ways | Accepts `2012-04-15`, `15-04-2012`, `22/09/2012`, `30.01.2012` |
| Excel turned the phone into `9876543210.0` | Cleans it back to `9876543210` |
| Phone has spaces or dashes | Strips them |
| A row has no admission number or name | Skips it and tells you which row |
| You upload the same file twice | **Updates** existing students — no duplicates |

Students are matched by **Admission Number**. That is their identity.

## Correcting mistakes

Fix the spreadsheet and import it again. There is no edit screen yet, and
re-import is the intended path. It is safe.

## Adding one new student

**Students → Add student.** Use this for admissions during the year, not for
the initial list.

---

# PART 4 — After the students are in

1. **Classes** — assign a class teacher to each class
2. **Staff** — create teacher accounts, note each password
3. Give teachers their username, password and the WiFi address
4. Teachers sign in, set their own password, and mark attendance

---

# PART 5 — Important warnings

**Keep the system out of OneDrive.** Your project folder is currently on the
Desktop inside OneDrive. That is fine for testing, but once real student data
goes in, install it somewhere like `C:\SchoolSystem\`. Cloud sync can corrupt
a live database file, and children's personal data should not sit in a
personal Microsoft account.

**Backups are automatic** — on startup and daily at 3:30 pm, kept in
`data\backups\`. But set a **second copy location** in Settings (a pen drive
or the school's own Drive folder). A backup on the same disk does not survive
that disk failing.

**Create a second admin account.** There is no password recovery. If the only
admin forgets their password, a programmer is needed.

**Nobody is yet responsible for this system after the project team leaves.**
This is the largest risk to the project — larger than any missing feature.
It needs a decision from the school, not more code.
