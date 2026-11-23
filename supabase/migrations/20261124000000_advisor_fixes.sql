-- Fixes from the Supabase performance advisor after the initial schema.

-- 1. Split the admin "for all" policies so SELECT has a single policy
--    (multiple permissive policies are evaluated for every row).
drop policy "admins manage years" on public.academic_years;
create policy "admins add years"
    on public.academic_years for insert to authenticated
    with check ((select private.is_admin()));
create policy "admins edit years"
    on public.academic_years for update to authenticated
    using ((select private.is_admin())) with check ((select private.is_admin()));
create policy "admins delete years"
    on public.academic_years for delete to authenticated
    using ((select private.is_admin()));

drop policy "admins manage sections" on public.sections;
create policy "admins add sections"
    on public.sections for insert to authenticated
    with check ((select private.is_admin()));
create policy "admins edit sections"
    on public.sections for update to authenticated
    using ((select private.is_admin())) with check ((select private.is_admin()));
create policy "admins delete sections"
    on public.sections for delete to authenticated
    using ((select private.is_admin()));

-- 2. Index foreign keys that had no covering index.
create index attendance_academic_year_idx on public.attendance (academic_year_id);
create index attendance_marked_by_idx     on public.attendance (marked_by);
create index sections_class_teacher_idx   on public.sections (class_teacher_id);
create index whatsapp_log_sent_by_idx     on public.whatsapp_log (sent_by);
