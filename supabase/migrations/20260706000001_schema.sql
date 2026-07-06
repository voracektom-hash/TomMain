-- Timesheet application schema
-- Tables: profiles, projects, timesheet_months, timesheet_days, audit_logs

create extension if not exists pgcrypto;

-- ---------------------------------------------------------------------------
-- profiles
-- ---------------------------------------------------------------------------
create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  full_name text,
  email text,
  role text not null default 'employee' check (role in ('employee', 'admin')),
  created_at timestamptz not null default now()
);

comment on table public.profiles is 'Application user profiles mirroring auth.users';

-- Auto-create a profile whenever a new auth user is created.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, full_name, email, role)
  values (
    new.id,
    coalesce(new.raw_user_meta_data ->> 'full_name', split_part(new.email, '@', 1)),
    new.email,
    coalesce(nullif(new.raw_user_meta_data ->> 'role', ''), 'employee')
  )
  on conflict (id) do nothing;
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- projects
-- ---------------------------------------------------------------------------
create table public.projects (
  id uuid primary key default gen_random_uuid(),
  project_code text unique not null,
  project_name text not null,
  client_name text,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- timesheet_months
-- ---------------------------------------------------------------------------
create table public.timesheet_months (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  year int not null check (year between 2000 and 2100),
  month int not null check (month between 1 and 12),
  status text not null default 'draft'
    check (status in ('draft', 'submitted', 'approved', 'returned')),
  submitted_at timestamptz,
  approved_at timestamptz,
  approved_by uuid references public.profiles (id),
  returned_reason text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (user_id, year, month)
);

create index timesheet_months_user_idx on public.timesheet_months (user_id);
create index timesheet_months_status_idx on public.timesheet_months (status);

-- ---------------------------------------------------------------------------
-- timesheet_days
-- ---------------------------------------------------------------------------
create table public.timesheet_days (
  id uuid primary key default gen_random_uuid(),
  timesheet_month_id uuid not null references public.timesheet_months (id) on delete cascade,
  date date not null,
  day_type text not null
    check (day_type in ('project', 'vacation', 'sick', 'holiday', 'non_working')),
  project_id uuid references public.projects (id),
  note text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (timesheet_month_id, date),
  -- a day of type 'project' must reference a project, other types must not
  constraint timesheet_days_project_consistency check (
    (day_type = 'project' and project_id is not null)
    or (day_type <> 'project' and project_id is null)
  )
);

create index timesheet_days_month_idx on public.timesheet_days (timesheet_month_id);

-- ---------------------------------------------------------------------------
-- audit_logs
-- ---------------------------------------------------------------------------
create table public.audit_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references public.profiles (id) on delete set null,
  action text not null,
  entity_type text not null,
  entity_id uuid,
  metadata jsonb,
  created_at timestamptz not null default now()
);

create index audit_logs_entity_idx on public.audit_logs (entity_type, entity_id);
create index audit_logs_user_idx on public.audit_logs (user_id);

-- ---------------------------------------------------------------------------
-- updated_at maintenance
-- ---------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger projects_set_updated_at
  before update on public.projects
  for each row execute function public.set_updated_at();

create trigger timesheet_months_set_updated_at
  before update on public.timesheet_months
  for each row execute function public.set_updated_at();

create trigger timesheet_days_set_updated_at
  before update on public.timesheet_days
  for each row execute function public.set_updated_at();
