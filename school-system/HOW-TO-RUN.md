# How to run it — start here

You need to start the system **before** the browser can open it.
`localhost:8000` only works while the system is running.

---

## The easy way

1. Open the `school-system` folder
2. **Double-click `START.bat`**
3. A black window opens. **Leave it open.**
4. Wait until you see:

```
========================================================
  SCHOOL MANAGEMENT SYSTEM
========================================================
  On this computer:      http://localhost:8000
  On the school WiFi:    http://192.168.1.14:8000
========================================================
```

5. **Now** open your browser and go to `http://localhost:8000`

The very first time, it also prints your login:

```
====================================================
  FIRST-TIME SETUP COMPLETE
  Username: admin
  Password: g7ViVr9y7pZh
====================================================
```

Write that down. It is also saved in `data\FIRST_LOGIN.txt`.

> **The black window must stay open.** Closing it stops the system, and the
> browser will show "This site can't be reached" again. Minimise it instead.

---

## The manual way

If you prefer typing commands:

1. Open the `school-system` folder
2. Click the address bar at the top of the window, type `cmd`, press Enter
3. Type these two lines:

```
pip install -r requirements.txt
python run.py
```

The first line is only needed once.

---

## "This site can't be reached" / ERR_CONNECTION_REFUSED

This always means one thing: **the system is not running.**

| Check | What to do |
|---|---|
| Is the black window open? | If not, double-click `START.bat` |
| Did the black window close by itself? | Read the message in it — it will say what went wrong |
| Did you open the browser too early? | Wait for the banner, then refresh |
| Is the address right? | `http://localhost:8000` — not `https`, not port 5173 or 3000 |

---

## Other problems

**"python is not recognised as an internal or external command"**

Python is either not installed, or was installed without ticking *Add Python
to PATH*.

1. Go to https://python.org/downloads
2. Run the installer
3. **Tick "Add Python to PATH"** on the very first screen — this is the step
   almost everyone misses
4. Restart the computer, then double-click `START.bat` again

**"Port 8000 is already in use"**

The system is already running in another window. Either use that one, or
close every black window and start again.

**The first-time install is slow**

The one-time component install takes 2–3 minutes on a normal connection.
This happens only once.

**"ValueError: password cannot be longer than 72 bytes" / "Application startup failed"**

You have an old version installed. Close the window and run:

```
pip uninstall -y passlib
pip install -r requirements.txt
```

Then double-click `START.bat` again.

(The system no longer uses `passlib` — it was unmaintained and broke with
current versions of `bcrypt`. If passlib is still installed from an earlier
attempt, removing it is enough.)

**I forgot the admin password**

Open `data\FIRST_LOGIN.txt` if it is still there. If you already changed the
password and forgot the new one, contact the technical team — it has to be
reset directly in the database. **Create a second admin account now, as
insurance.**

---

## Once it is running

| Where | Address |
|---|---|
| This computer | `http://localhost:8000` |
| Teachers' phones (school WiFi) | the second address in the black window, e.g. `http://192.168.1.14:8000` |

Teachers must be on the **same WiFi**. It will not work from their homes.

Next: read [`SETUP.md`](SETUP.md) to import students and create teacher accounts.
