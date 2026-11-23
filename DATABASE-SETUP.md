# Connecting the portal to Supabase

The portal website (`index.html`) now stores everything in a Supabase
(Postgres) database instead of hardcoded sample data.

## 1. Fill in `.env`

Copy `.env.example` to `.env` (one is already created locally) and paste in
the values from **Supabase dashboard → Project Settings → API**:

```
SUPABASE_URL=https://<your-project-ref>.supabase.co
SUPABASE_ANON_KEY=<anon / publishable key>
```

Only use the **anon / publishable** key. Never put the `service_role` /
secret key in this file: it bypasses all security and would be sent to the
browser.

`.env` is git-ignored and must never be committed.

## 2. Create the tables

Run `supabase/migrations/20261123000000_initial_schema.sql` once, either:

- in **Supabase dashboard → SQL Editor** (paste the file and click Run), or
- with the Supabase CLI: `supabase db push`.

It creates:

| Table | What the website stores there |
|---|---|
| `staff` | Teachers/admins who can sign in (linked to Supabase Auth users) |
| `academic_years` | 2026-27 etc. (seeded with 2026-27) |
| `sections` | 10A, 10B, 9A (seeded); class teacher and room |
| `students` | Add Student form + Excel import: roll no, full name, section, parent, phone, gender, DOB, admission no |
| `attendance` | One row per student per day: PRESENT / ABSENT / LATE / HALF_DAY / LEAVE |
| `whatsapp_log` | Every "WhatsApp Parent" message opened from the portal |
| `student_attendance_summary` (view) | Attendance % and consecutive absences shown across the site |

Row Level Security is on for every table. The anon key on its own can read
**nothing**; a user must sign in **and** be listed in `staff`.

## 3. Create the first staff login

1. Dashboard → **Authentication → Users → Add user** (email + password,
   tick "Auto confirm").
2. Dashboard → **SQL Editor**, run (change the name/email):

   ```sql
   insert into public.staff (id, full_name, role)
   select id, 'Sr. Teresa', 'ADMIN'
   from auth.users where email = 'teacher@example.com';

   -- optional: make her class teacher of 10A
   update public.sections set class_teacher_id =
     (select id from auth.users where email = 'teacher@example.com')
   where code = '10A';
   ```

   Roles: `ADMIN`, `PRINCIPAL` (can manage sections/years, delete records),
   `TEACHER` (can add students, mark attendance, send WhatsApp).

3. Optional: Dashboard → Authentication → Providers → Email → turn off
   "Allow new users to sign up" so only staff you create can log in.

## 4. Run the site

```
python serve.py
```

Open http://localhost:8000 and sign in. `serve.py` uses only the Python
standard library; it serves the site and generates `config.js` from `.env`
(only the URL and anon key reach the browser).

For static hosting (Netlify, GitHub Pages, etc.) run
`python serve.py --write-config` and deploy `config.js` alongside
`index.html`.

If `.env` is empty the site still opens, in **demo mode** with sample data.

## Note on `school-system/`

The FastAPI app in `school-system/` is unchanged and still uses its own local
SQLite file. Only the `index.html` portal talks to Supabase.
