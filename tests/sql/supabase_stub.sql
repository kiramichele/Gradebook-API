-- The pieces of a Supabase project the migration depends on, so RLS can be
-- tested on plain Postgres. Roles are cluster-wide, hence the guards.
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'authenticated') then
        create role authenticated nologin;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'anon') then
        create role anon nologin;
    end if;
    -- Stands in for Supabase's `postgres` role: a non-superuser login that
    -- can SET ROLE authenticated.
    if not exists (select 1 from pg_roles where rolname = 'gradebook_api') then
        create role gradebook_api login password 'gradebook_api' noinherit;
    end if;
end
$$;
grant authenticated to gradebook_api;

create schema auth;
create table auth.users (id uuid primary key, raw_user_meta_data jsonb);
create function auth.uid() returns uuid language sql stable as $$
    select nullif(current_setting('request.jwt.claims', true)::jsonb ->> 'sub', '')::uuid
$$;
grant usage on schema auth to authenticated;
