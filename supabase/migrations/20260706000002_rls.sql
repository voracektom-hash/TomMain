-- Row Level Security policies

-- Helper: is the current user an admin?
-- SECURITY DEFINER so it can read profiles without tripping profiles' own RLS.
create or replace function public.is_admin()
returns boolean
language sql
security definer
stable
set search_path = public
as $$
  select exists (
    select 1 from public.profiles
    where id = auth.uid() and role = 'admin'
  );
$$;

-- Helper: does the given timesheet month belong to the current user and is it editable?
create or replace function public.month_editable_by_me(month_id uuid)
returns boolean
language sql
security definer
stable
set search_path = public
as $$
  select exists (
    select 1 from public.timesheet_months m
    where m.id = month_id
      and m.user_id = auth.uid()
      and m.status in ('draft', 'returned')
  );
$$;

-- Helper: does the given timesheet month belong to the current user?
create or replace function public.month_owned_by_me(month_id uuid)
returns boolean
language sql
security definer
stable
set search_path = public
as $$
  select exists (
    select 1 from public.timesheet_months m
    where m.id = month_id and m.user_id = auth.uid()
  );
$$;

alter table public.profiles enable row level security;
alter table public.projects enable row level security;
alter table public.timesheet_months enable row level security;
alter table public.timesheet_days enable row level security;
alter table public.audit_logs enable row level security;

-- ---------------------------------------------------------------------------
-- profiles
-- ---------------------------------------------------------------------------
create policy "profiles: select own or admin"
  on public.profiles for select
  using (id = auth.uid() or public.is_admin());

create policy "profiles: update own name"
  on public.profiles for update
  using (id = auth.uid())
  with check (id = auth.uid());

-- ---------------------------------------------------------------------------
-- projects: readable by all authenticated users, writable by admins only
-- ---------------------------------------------------------------------------
create policy "projects: select authenticated"
  on public.projects for select
  using (auth.uid() is not null);

create policy "projects: insert admin"
  on public.projects for insert
  with check (public.is_admin());

create policy "projects: update admin"
  on public.projects for update
  using (public.is_admin())
  with check (public.is_admin());

-- ---------------------------------------------------------------------------
-- timesheet_months
-- ---------------------------------------------------------------------------
create policy "timesheet_months: select own or admin"
  on public.timesheet_months for select
  using (user_id = auth.uid() or public.is_admin());

-- Employees may create their own months, always as draft.
create policy "timesheet_months: insert own draft"
  on public.timesheet_months for insert
  with check (
    user_id = auth.uid()
    and status = 'draft'
    and approved_by is null
    and approved_at is null
  );

-- Employees may update their own months only while draft/returned,
-- and may move them only to draft/submitted (never approve themselves).
create policy "timesheet_months: employee update draft or returned"
  on public.timesheet_months for update
  using (
    user_id = auth.uid()
    and status in ('draft', 'returned')
  )
  with check (
    user_id = auth.uid()
    and status in ('draft', 'submitted')
    and approved_by is null
  );

-- Admins may update any month (approve / return).
create policy "timesheet_months: admin update"
  on public.timesheet_months for update
  using (public.is_admin())
  with check (public.is_admin());

-- ---------------------------------------------------------------------------
-- timesheet_days
-- ---------------------------------------------------------------------------
create policy "timesheet_days: select own or admin"
  on public.timesheet_days for select
  using (public.month_owned_by_me(timesheet_month_id) or public.is_admin());

create policy "timesheet_days: insert own editable month"
  on public.timesheet_days for insert
  with check (public.month_editable_by_me(timesheet_month_id));

create policy "timesheet_days: update own editable month"
  on public.timesheet_days for update
  using (public.month_editable_by_me(timesheet_month_id))
  with check (public.month_editable_by_me(timesheet_month_id));

create policy "timesheet_days: delete own editable month"
  on public.timesheet_days for delete
  using (public.month_editable_by_me(timesheet_month_id));

-- ---------------------------------------------------------------------------
-- audit_logs: append-only; users write their own entries, admins read all
-- ---------------------------------------------------------------------------
create policy "audit_logs: insert own"
  on public.audit_logs for insert
  with check (user_id = auth.uid());

create policy "audit_logs: select admin"
  on public.audit_logs for select
  using (public.is_admin());
