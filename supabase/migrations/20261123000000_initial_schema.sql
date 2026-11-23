-- =====================================================================
-- St. Joseph's Convent School portal - initial Supabase schema
--
-- Every table here maps to something the website (index.html) collects
-- or displays:
--
--   staff               -> logged-in teacher shown in the header
--   academic_years      -> "Academic Year 2026-27" on the dashboard
--   sections            -> 10A / 10B / 9A class pickers
--   students            -> Add Student form + Excel import
--                          (roll no, full name, parent, phone, gender, DOB)
--   attendance          -> Mark Attendance tab (P / A / L / H / Lv per day)
--   whatsapp_log        -> WhatsApp Parent buttons + "Parent WhatsApp Log"
--   student_attendance_summary (view) -> attendance %, consecutive absences
--
-- Row Level Security is ON for every table. Only signed-in users who have
-- a row in public.staff can read or write anything. The anon key alone
-- gives no access to student data.
-- =====================================================================

create schema if not exists private;

-- ---------------------------------------------------------------------
-- staff: one row per teacher/admin, linked to a Supabase Auth user
-- ---------------------------------------------------------------------
create table public.staff (
    id          uuid primary key references auth.users (id) on delete cascade,
    full_name   text not null,
    role        text not null default 'TEACHER'
                check (role in ('ADMIN', 'PRINCIPAL', 'TEACHER')),
    phone       text,
    created_at  timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- academic_years
-- ---------------------------------------------------------------------
create table public.academic_years (
    id          bigint generated always as identity primary key,
    name        text not null unique,            -- '2026-27'
    start_date  date not null,
    end_date    date not null,
    is_current  boolean not null default false,
    created_at  timestamptz not null default now(),
    check (end_date > start_date)
);

-- Only one year can be the current one.
create unique index academic_years_one_current
    on public.academic_years (is_current) where is_current;

-- ---------------------------------------------------------------------
-- sections: '10A' = 10th Standard, Section A
-- ---------------------------------------------------------------------
create table public.sections (
    id                bigint generated always as identity primary key,
    code              text not null unique,       -- '10A'
    standard          text not null,              -- '10th Standard'
    division          text not null,              -- 'A'
    room              text,                       -- 'Room 102'
    class_teacher_id  uuid references public.staff (id) on delete set null,
    sort_order        integer not null default 0,
    created_at        timestamptz not null default now(),
    unique (standard, division)
);

-- ---------------------------------------------------------------------
-- students
-- ---------------------------------------------------------------------
create sequence public.admission_number_seq;

create table public.students (
    id                bigint generated always as identity primary key,
    -- Shown as "Adm No" in the directory, e.g. SJ-2026-0042
    admission_number  text not null unique default (
        'SJ-' || extract(year from now())::int || '-' ||
        lpad(nextval('public.admission_number_seq')::text, 4, '0')
    ),
    roll_number       integer not null check (roll_number > 0),
    full_name         text not null check (length(trim(full_name)) > 0),
    section_id        bigint not null references public.sections (id),
    parent_name       text,
    -- 10-digit Indian mobile, used for wa.me/91<phone>
    phone             text check (phone ~ '^[0-9]{10}$'),
    gender            text,
    date_of_birth     date,
    -- Students are never deleted; they change status instead.
    status            text not null default 'ACTIVE'
                      check (status in ('ACTIVE', 'LEFT', 'GRADUATED', 'TRANSFERRED')),
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now(),
    -- Lets the Excel import update a student instead of duplicating them.
    unique (section_id, roll_number)
);

create index students_section_idx on public.students (section_id);
create index students_name_idx    on public.students (lower(full_name));

-- ---------------------------------------------------------------------
-- attendance: one row per student per day
-- ---------------------------------------------------------------------
create table public.attendance (
    id                bigint generated always as identity primary key,
    student_id        bigint not null references public.students (id) on delete cascade,
    section_id        bigint not null references public.sections (id),
    academic_year_id  bigint references public.academic_years (id),
    date              date not null,
    status            text not null
                      check (status in ('PRESENT', 'ABSENT', 'LATE', 'HALF_DAY', 'LEAVE')),
    remarks           text,
    marked_by         uuid default auth.uid() references auth.users (id) on delete set null,
    marked_at         timestamptz not null default now(),
    -- Re-saving the same day updates instead of duplicating.
    unique (student_id, date)
);

create index attendance_section_date_idx on public.attendance (section_id, date);
create index attendance_date_idx         on public.attendance (date);

-- ---------------------------------------------------------------------
-- whatsapp_log: every parent message opened from the portal
-- ---------------------------------------------------------------------
create table public.whatsapp_log (
    id            bigint generated always as identity primary key,
    student_id    bigint not null references public.students (id) on delete cascade,
    phone         text not null,
    message_type  text not null check (message_type in ('ABSENCE', 'LOW_ATTENDANCE')),
    message       text not null,
    for_date      date not null default current_date,
    sent_by       uuid default auth.uid() references auth.users (id) on delete set null,
    sent_at       timestamptz not null default now()
);

create index whatsapp_log_student_idx on public.whatsapp_log (student_id);
create index whatsapp_log_date_idx    on public.whatsapp_log (for_date);

-- ---------------------------------------------------------------------
-- Triggers
-- ---------------------------------------------------------------------
create or replace function private.set_updated_at()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    new.updated_at := now();
    return new;
end;
$$;

create trigger students_set_updated_at
    before update on public.students
    for each row execute function private.set_updated_at();

-- Tag each attendance row with the academic year its date falls in,
-- so a year's register stays queryable after sections are reorganised.
create or replace function private.set_attendance_year()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    if new.academic_year_id is null then
        select y.id into new.academic_year_id
        from public.academic_years y
        where new.date between y.start_date and y.end_date
        order by y.start_date desc
        limit 1;
    end if;
    new.marked_at := now();
    new.marked_by := coalesce(auth.uid(), new.marked_by);
    return new;
end;
$$;

create trigger attendance_set_year
    before insert or update on public.attendance
    for each row execute function private.set_attendance_year();

-- ---------------------------------------------------------------------
-- Attendance summary view (attendance %, consecutive absences)
--
-- Weights match school-system/app/attendance_utils.py:
--   PRESENT / LATE / LEAVE = 1, HALF_DAY = 0.5, ABSENT = 0
-- security_invoker = true means the view obeys the caller's RLS.
-- ---------------------------------------------------------------------
create view public.student_attendance_summary
with (security_invoker = true) as
select
    s.id                                                    as student_id,
    s.section_id,
    count(a.id)                                             as total_days,
    count(a.id) filter (where a.status = 'PRESENT')         as present_days,
    count(a.id) filter (where a.status = 'ABSENT')          as absent_days,
    count(a.id) filter (where a.status = 'LATE')            as late_days,
    count(a.id) filter (where a.status = 'HALF_DAY')        as half_days,
    count(a.id) filter (where a.status = 'LEAVE')           as leave_days,
    coalesce(round(
        100.0 * sum(case
                        when a.status in ('PRESENT', 'LATE', 'LEAVE') then 1
                        when a.status = 'HALF_DAY' then 0.5
                        else 0
                    end) / nullif(count(a.id), 0),
        1), 100.0)                                          as attendance_percent,
    (
        select count(*)
        from public.attendance a2
        where a2.student_id = s.id
          and a2.status = 'ABSENT'
          and a2.date > coalesce(
                (select max(a3.date) from public.attendance a3
                 where a3.student_id = s.id and a3.status <> 'ABSENT'),
                '-infinity'::date)
    )                                                       as consecutive_absences
from public.students s
left join public.attendance a on a.student_id = s.id
group by s.id, s.section_id;

-- ---------------------------------------------------------------------
-- Access helpers (in the private schema so they are not exposed as RPC)
-- ---------------------------------------------------------------------
create or replace function private.is_staff()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (select 1 from public.staff where id = (select auth.uid()));
$$;

create or replace function private.is_admin()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1 from public.staff
        where id = (select auth.uid()) and role in ('ADMIN', 'PRINCIPAL')
    );
$$;

grant usage on schema private to authenticated;
grant execute on function private.is_staff(), private.is_admin() to authenticated;
revoke execute on function private.is_staff(), private.is_admin() from anon, public;

-- ---------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------
alter table public.staff          enable row level security;
alter table public.academic_years enable row level security;
alter table public.sections       enable row level security;
alter table public.students       enable row level security;
alter table public.attendance     enable row level security;
alter table public.whatsapp_log   enable row level security;

-- staff: readable by staff; managed from the Supabase dashboard / SQL editor
create policy "staff can read staff"
    on public.staff for select to authenticated
    using ((select private.is_staff()));

-- academic_years
create policy "staff can read years"
    on public.academic_years for select to authenticated
    using ((select private.is_staff()));
create policy "admins manage years"
    on public.academic_years for all to authenticated
    using ((select private.is_admin())) with check ((select private.is_admin()));

-- sections
create policy "staff can read sections"
    on public.sections for select to authenticated
    using ((select private.is_staff()));
create policy "admins manage sections"
    on public.sections for all to authenticated
    using ((select private.is_admin())) with check ((select private.is_admin()));

-- students: any staff member can add / edit; only admins can delete
create policy "staff can read students"
    on public.students for select to authenticated
    using ((select private.is_staff()));
create policy "staff can add students"
    on public.students for insert to authenticated
    with check ((select private.is_staff()));
create policy "staff can edit students"
    on public.students for update to authenticated
    using ((select private.is_staff())) with check ((select private.is_staff()));
create policy "admins can delete students"
    on public.students for delete to authenticated
    using ((select private.is_admin()));

-- attendance
create policy "staff can read attendance"
    on public.attendance for select to authenticated
    using ((select private.is_staff()));
create policy "staff can mark attendance"
    on public.attendance for insert to authenticated
    with check ((select private.is_staff()));
create policy "staff can correct attendance"
    on public.attendance for update to authenticated
    using ((select private.is_staff())) with check ((select private.is_staff()));
create policy "admins can delete attendance"
    on public.attendance for delete to authenticated
    using ((select private.is_admin()));

-- whatsapp_log: append-only for staff
create policy "staff can read whatsapp log"
    on public.whatsapp_log for select to authenticated
    using ((select private.is_staff()));
create policy "staff can write whatsapp log"
    on public.whatsapp_log for insert to authenticated
    with check ((select private.is_staff()));

-- ---------------------------------------------------------------------
-- Starter data: the year and sections the website already shows
-- ---------------------------------------------------------------------
insert into public.academic_years (name, start_date, end_date, is_current)
values ('2026-27', '2026-06-01', '2027-03-31', true);

insert into public.sections (code, standard, division, room, sort_order) values
    ('10A', '10th Standard', 'A', 'Room 102', 1),
    ('10B', '10th Standard', 'B', 'Room 103', 2),
    ('9A',  '9th Standard',  'A', 'Room 101', 3);
