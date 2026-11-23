-- Self-registration with admin approval.
--
-- Passwords are stored and verified by Supabase Auth (auth.users, bcrypt).
-- When someone registers on the website, a trigger creates their staff row.
--   * The very first account becomes an approved ADMIN (bootstrap).
--   * Everyone after that starts as a TEACHER with approved = false and
--     cannot see any school data until an admin approves them.

alter table public.staff
    add column email    text,
    add column approved boolean not null default false;

-- Anyone already in staff (added by hand) stays approved.
update public.staff set approved = true;

-- ---------------------------------------------------------------------
-- Create a staff row whenever a new auth user signs up
-- ---------------------------------------------------------------------
create or replace function private.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    is_first boolean;
    display_name text;
begin
    -- Serialise concurrent sign-ups so only one can become the first admin.
    perform pg_advisory_xact_lock(hashtext('public.staff.bootstrap'));
    select not exists (select 1 from public.staff) into is_first;

    -- Name comes from the register form; role/approval NEVER come from
    -- user-supplied metadata.
    display_name := left(coalesce(
        nullif(trim(new.raw_user_meta_data ->> 'full_name'), ''),
        split_part(new.email, '@', 1)
    ), 120);

    insert into public.staff (id, full_name, email, role, approved)
    values (
        new.id,
        display_name,
        new.email,
        case when is_first then 'ADMIN' else 'TEACHER' end,
        is_first
    )
    on conflict (id) do nothing;

    return new;
end;
$$;

create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function private.handle_new_user();

-- ---------------------------------------------------------------------
-- Only APPROVED staff count as staff / admins
-- ---------------------------------------------------------------------
create or replace function private.is_staff()
returns boolean
language sql
stable
security definer
set search_path = ''
as $$
    select exists (
        select 1 from public.staff
        where id = (select auth.uid()) and approved
    );
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
        where id = (select auth.uid()) and approved
          and role in ('ADMIN', 'PRINCIPAL')
    );
$$;

-- ---------------------------------------------------------------------
-- staff policies
-- ---------------------------------------------------------------------
drop policy "staff can read staff" on public.staff;

-- Everyone can read their OWN row (so the site can say "pending approval");
-- approved staff can read the whole list.
create policy "read own row or all if staff"
    on public.staff for select to authenticated
    using (id = (select auth.uid()) or (select private.is_staff()));

-- Admins approve people, change roles and fix names.
create policy "admins update staff"
    on public.staff for update to authenticated
    using ((select private.is_admin())) with check ((select private.is_admin()));

-- Admins can remove an account's staff row (revoke completely).
create policy "admins delete staff"
    on public.staff for delete to authenticated
    using ((select private.is_admin()));

-- Column-level guard: only these columns can ever be changed from the site.
revoke update on public.staff from authenticated, anon;
grant update (full_name, role, approved, phone) on public.staff to authenticated;
-- Rows are created only by the trigger above.
revoke insert on public.staff from authenticated, anon;
