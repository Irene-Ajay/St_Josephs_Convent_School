# Setup Guide — for the school

This guide is written for a school staff member, not a programmer.
You do not need to understand any code to follow it.

---

## What this system does

- Keeps all student details in one place
- Lets teachers mark daily attendance from a phone, tablet or computer
- Shows who is absent each day, with the parent's phone number
- Prepares absence messages for parents (WhatsApp, phone call or email)
- Produces attendance reports and Excel downloads for school records

---

## What you need

- One Windows computer that stays switched on during school hours
- The school WiFi (so teachers' phones can connect)
- About 30 minutes for the first setup

You do **not** need internet for the system itself. Internet is only needed
if you want automatic emails to parents.

---

## Part 1 — Installing (done once)

### Step 1: Install Python

1. Go to **python.org/downloads**
2. Download and run the installer
3. **Important:** tick the box that says *"Add Python to PATH"* before clicking Install

### Step 2: Copy the system folder

Copy the `school-system` folder to the computer, for example to:

```
C:\SchoolSystem
```

> **Do not put this folder inside OneDrive, Google Drive or Dropbox.**
> Cloud sync can damage the database file while the system is running.
> Keep it on the computer itself. Backups are explained in Part 4.

### Step 3: Install the required components

1. Open the `school-system` folder
2. Click the address bar at the top, type `cmd`, press Enter
3. Type this and press Enter:

```
pip install -r requirements.txt
```

Wait for it to finish. This is done only once.

---

## Part 2 — Starting the system

Each morning, in that same black window, type:

```
python run.py
```

You will see something like:

```
====================================================
  SCHOOL MANAGEMENT SYSTEM
====================================================
  On this computer:      http://localhost:8000
  On the school WiFi:    http://192.168.1.14:8000
====================================================
```

**Leave this window open.** Closing it stops the system.

- On this computer, open a browser and go to `http://localhost:8000`
- On a teacher's phone connected to school WiFi, go to the second address
  (for example `http://192.168.1.14:8000`)

### The first login

The very first time, a username and password are created automatically and
printed in that window. They are also saved in `data\FIRST_LOGIN.txt`.

- Username: `admin`
- Password: shown on screen

Log in, change the password immediately when asked, then delete
`data\FIRST_LOGIN.txt`.

---

## Part 3 — First-time setup inside the system

### Step 1: Add your students

1. Click **Import** in the menu
2. Click **Download blank template**
3. Open it in Excel. Paste in your existing student list, or type it
4. Only two columns are compulsory: **Admission Number** and **Name**
5. Save the file, then upload it on the same page

Classes are created automatically from the *Class* and *Division* columns.

> If you spot a mistake, correct the spreadsheet and upload it again.
> Students are matched by admission number, so nothing gets duplicated.

### Step 2: Create teacher accounts

You can do this yourself. No technical help is needed.

1. Click **Staff** in the menu, then **Add staff member**
2. Enter their name and choose a username (their first name works well)
3. Choose the role:
   - **Teacher** — can only mark attendance for classes assigned to them
   - **Office / Admin** — full access, including creating other accounts
4. Click **Create account**

A password is generated and shown **once** on the next screen.
**Write it down immediately** — it cannot be viewed again. If it is lost,
click **Reset password** to make a new one.

Give the teacher their username and password. The first time they sign in,
they will be asked to choose their own password.

> Only two kinds of people can log in: teachers and office staff.
> Students and parents have no login at all. This is deliberate — it keeps
> the system small and keeps children's data inside the school.

### Step 3: Assign teachers to their classes

Click **Classes** in the menu. Next to each class, choose the class teacher
from the dropdown. It saves automatically.

**This is the access control.** A teacher can only see and mark attendance for
the classes assigned to them here. They cannot open another class even if they
type its address directly into the browser.

### When a teacher leaves the school

Go to **Staff** and click **Deactivate**. They can no longer sign in, but the
attendance they marked stays in the records with their name on it. Never
delete a staff account.

### Step 4: Fill in school details

Go to **Settings** and enter the school name and office phone number.
These appear in the messages sent to parents.

---

## Part 4 — Backups (automatic)

All your data is in **one single file**: `school-system\data\school.db`

**The system backs itself up automatically.** You do not need to remember
anything:

- once every morning when the system starts
- again every afternoon at 3:30
- 30 daily copies are kept, plus one per month for a year

Backups are saved in `school-system\data\backups\`. You can see when the
last one ran on the **Settings** page.

### One thing you should set up (5 minutes)

A backup on the same computer protects against mistakes, but **not against
that computer failing**. Set a second location:

1. Plug in a pen drive, or find the school's Google Drive / OneDrive folder
2. Go to **Settings → Backups → Second copy location**
3. Type the folder, for example `E:\SchoolBackups`
4. Save

Every backup is now copied there too. If the pen drive is unplugged, the
system carries on normally — it just skips the second copy.

### To restore

1. Stop the system
2. Go to `data\backups\` and find the date you want
3. Copy that file into `data\` and rename it to `school.db`
4. Start the system again

---

## Part 5 — Sending messages to parents

Three options, from easiest to hardest:

### Option A: WhatsApp (works immediately, free)

1. Go to **Parent messages**
2. The message is already written for each absent student
3. Click **Send WhatsApp** — it opens WhatsApp with the message ready
4. Send it, then click **Mark as contacted**

### Option B: Email (free, automatic, needs 10 minutes of setup)

1. Create or use a Gmail account for the school
2. In that Google account, turn on 2-Step Verification, then create an
   **App Password** (Google Account → Security → App passwords)
3. In this system, go to **Settings → Email**, tick *Enable*, and enter the
   Gmail address and the App Password
4. Now the **Send all by email** button works

Use the App Password, not the normal Gmail password.

### Option C: Automatic SMS (costs money, takes 1–2 weeks)

Indian law (TRAI) requires **DLT registration** before any organisation can
send bulk SMS. Telecom companies block unregistered messages.

The school — not the students who built this — must:

1. Register the school as an entity on a DLT portal
2. Register a 6-character sender name, e.g. `STJOSP`
3. Register each message wording in advance

Approximate cost: **₹5,900 + GST** one time, plus a few paise per message
afterwards. It usually takes 3–7 working days.

**Our recommendation:** start with WhatsApp and email. Only pursue SMS if the
school finds that parents are not seeing the WhatsApp messages.

---

## Common problems

| Problem | What to do |
|---|---|
| "python is not recognised" | Python was installed without ticking *Add to PATH*. Reinstall it and tick that box. |
| Teachers' phones cannot connect | They must be on the school WiFi. Check the address shown when starting. |
| "Port already in use" | The system is already running in another window. |
| Forgot the admin password | Ask the technical team — it can be reset directly in the database. |
| System is slow | Restart it: close the window and run `python run.py` again. |
| Database is locked | Two copies are running. Close all black windows and start one. |

---

## Who to contact

Fill this in before the project team leaves:

- **Person responsible at school:** ______________________
- **Technical contact:** ______________________
- **Backup checked on:** ______________________

---

## Part 6 — Training teachers (30 minutes)

The whole system is four things a teacher needs to know. Train them in groups
of five or six, with their own phones in hand.

### What to cover

**1. Signing in (5 min)**
- Connect to school WiFi
- Open the browser, type the address (write it on the board)
- Sign in, choose their own password
- **Tell them to bookmark the page** — this saves the most confusion later

**2. Marking attendance (10 min)**
- Home screen shows their class with a "Mark attendance" button
- Everyone starts as **P** (present)
- Tap **A** only for the students who are absent
- Tap **Save attendance**
- Show them: reopening the same day and correcting a mistake

**3. Seeing who is absent (5 min)**
- **Absent today** shows the list with parent phone numbers
- Tapping a number calls it directly

**4. Messaging parents (10 min)**
- **Parent messages** has the message already written
- Tap **Send WhatsApp**, then **Mark as contacted**
- Explain why marking as contacted matters: it stops a parent being messaged
  twice by two different staff members

### Things worth saying out loud

- "You cannot break it." Marking attendance twice just corrects it.
- "You can only see your own class." This reassures them about privacy.
- "If you forget your password, the office can reset it."
- "It works on your phone. You do not need a computer."

### Before you finish the session

Have every teacher, on their own phone:
1. Sign in successfully
2. Mark attendance for their class
3. Open the Absent today page

If they have each done those three things once, they can use the system.

### Leave behind

- A printed card with the web address and their username
- The name and number of the person at school who can reset passwords
- One page of the steps above, printed
