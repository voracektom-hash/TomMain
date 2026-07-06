-- Seed data for local development (supabase db reset applies this automatically).
--
-- Creates:
--   * demo projects
--   * one admin user   admin@example.com  / password123
--   * one employee     zamestnanec@example.com / password123
--
-- The auth.users inserts target the local GoTrue schema used by the Supabase
-- CLI. Do NOT run this against a production project.

-- ---------------------------------------------------------------------------
-- Demo users
-- ---------------------------------------------------------------------------
insert into auth.users (
  instance_id, id, aud, role, email, encrypted_password,
  email_confirmed_at, raw_app_meta_data, raw_user_meta_data,
  created_at, updated_at, confirmation_token, recovery_token,
  email_change_token_new, email_change
)
values
  (
    '00000000-0000-0000-0000-000000000000',
    '11111111-1111-1111-1111-111111111111',
    'authenticated', 'authenticated',
    'admin@example.com',
    crypt('password123', gen_salt('bf')),
    now(),
    '{"provider":"email","providers":["email"]}',
    '{"full_name":"Alena Adminová","role":"admin"}',
    now(), now(), '', '', '', ''
  ),
  (
    '00000000-0000-0000-0000-000000000000',
    '22222222-2222-2222-2222-222222222222',
    'authenticated', 'authenticated',
    'zamestnanec@example.com',
    crypt('password123', gen_salt('bf')),
    now(),
    '{"provider":"email","providers":["email"]}',
    '{"full_name":"Petr Pracovník","role":"employee"}',
    now(), now(), '', '', '', ''
  )
on conflict (id) do nothing;

insert into auth.identities (
  id, user_id, provider_id, identity_data, provider,
  last_sign_in_at, created_at, updated_at
)
values
  (
    gen_random_uuid(),
    '11111111-1111-1111-1111-111111111111',
    '11111111-1111-1111-1111-111111111111',
    '{"sub":"11111111-1111-1111-1111-111111111111","email":"admin@example.com","email_verified":true}',
    'email', now(), now(), now()
  ),
  (
    gen_random_uuid(),
    '22222222-2222-2222-2222-222222222222',
    '22222222-2222-2222-2222-222222222222',
    '{"sub":"22222222-2222-2222-2222-222222222222","email":"zamestnanec@example.com","email_verified":true}',
    'email', now(), now(), now()
  )
on conflict do nothing;

-- Profiles are created by the on_auth_user_created trigger; make sure roles match.
update public.profiles set role = 'admin' where id = '11111111-1111-1111-1111-111111111111';

-- ---------------------------------------------------------------------------
-- Demo projects
-- ---------------------------------------------------------------------------
insert into public.projects (project_code, project_name, client_name, is_active)
values
  ('P-1001', 'Interní vývoj', 'Interní', true),
  ('P-2001', 'E-shop redesign', 'Alfa Retail s.r.o.', true),
  ('P-2002', 'Datový sklad', 'Beta Finance a.s.', true),
  ('P-3001', 'Mobilní aplikace', 'Gama Logistics', true),
  ('P-9001', 'Ukončený projekt', 'Delta Media', false)
on conflict (project_code) do nothing;
