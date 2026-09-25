-- FantaCoach v0.8 - database multi-utente
-- Esegui tutto questo file nel SQL Editor del tuo progetto Supabase.

create extension if not exists pgcrypto;

create table if not exists public.teams (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  owner_name text not null,
  team_name text not null,
  league_name text not null,
  mode text not null default 'Classic' check (mode in ('Classic','Mantra')),
  created_at timestamptz not null default now()
);

create index if not exists teams_user_id_idx on public.teams(user_id);

create table if not exists public.roster_entries (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  team_id uuid not null references public.teams(id) on delete cascade,
  player_key text not null,
  name text not null,
  full_name text not null,
  club text not null,
  role text not null check (role in ('POR','DIF','CEN','ATT')),
  provider_id text,
  created_at timestamptz not null default now(),
  unique(team_id, player_key)
);

create index if not exists roster_entries_user_id_idx on public.roster_entries(user_id);
create index if not exists roster_entries_team_id_idx on public.roster_entries(team_id);

alter table public.teams enable row level security;
alter table public.roster_entries enable row level security;

revoke all on table public.teams from anon, authenticated;
revoke all on table public.roster_entries from anon, authenticated;
grant select, insert, update, delete on table public.teams to authenticated;
grant select, insert, update, delete on table public.roster_entries to authenticated;

drop policy if exists "teams_select_own" on public.teams;
create policy "teams_select_own" on public.teams
for select to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists "teams_insert_own" on public.teams;
create policy "teams_insert_own" on public.teams
for insert to authenticated
with check ((select auth.uid()) = user_id);

drop policy if exists "teams_update_own" on public.teams;
create policy "teams_update_own" on public.teams
for update to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);

drop policy if exists "teams_delete_own" on public.teams;
create policy "teams_delete_own" on public.teams
for delete to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists "roster_select_own" on public.roster_entries;
create policy "roster_select_own" on public.roster_entries
for select to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists "roster_insert_own" on public.roster_entries;
create policy "roster_insert_own" on public.roster_entries
for insert to authenticated
with check (
  (select auth.uid()) = user_id
  and exists (
    select 1 from public.teams t
    where t.id = team_id and t.user_id = (select auth.uid())
  )
);

drop policy if exists "roster_update_own" on public.roster_entries;
create policy "roster_update_own" on public.roster_entries
for update to authenticated
using ((select auth.uid()) = user_id)
with check (
  (select auth.uid()) = user_id
  and exists (
    select 1 from public.teams t
    where t.id = team_id and t.user_id = (select auth.uid())
  )
);

drop policy if exists "roster_delete_own" on public.roster_entries;
create policy "roster_delete_own" on public.roster_entries
for delete to authenticated
using ((select auth.uid()) = user_id);
