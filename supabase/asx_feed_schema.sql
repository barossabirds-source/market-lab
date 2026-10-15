-- Compact, private source observations; public dashboard reads operational health only.
create table if not exists public.asx_session_observations (
  session_date date not null,
  symbol text not null,
  source text not null,
  captured_at timestamptz not null default now(),
  quality text not null check (quality in ('research_proxy_missing_spi','missing_intraday','missing_us_close')),
  observations jsonb not null check (octet_length(observations::text) <= 8192),
  primary key (session_date, symbol, source)
);
create table if not exists public.asx_feed_status (
  feed_key text primary key,
  checked_at timestamptz not null,
  status text not null,
  message text not null check (length(message)<=500),
  details jsonb not null default '{}'::jsonb check (octet_length(details::text)<=4096)
);
alter table public.asx_session_observations enable row level security;
alter table public.asx_feed_status enable row level security;
revoke all on public.asx_session_observations from anon, authenticated;
grant select, insert on public.asx_session_observations to service_role;
grant all on public.asx_feed_status to service_role;
grant select on public.asx_feed_status to anon, authenticated;
create policy "Read ASX collection health" on public.asx_feed_status for select to anon, authenticated using (true);
create or replace function public.asx_collection_storage()
returns jsonb language sql security invoker set search_path = '' as $$
 select jsonb_build_object(
   'database_bytes', pg_database_size(current_database()),
   'study_bytes', pg_total_relation_size('public.asx_session_observations'::regclass) + pg_total_relation_size('public.asx_feed_status'::regclass),
   'sessions', (select count(*) from public.asx_session_observations),
   'latest_session', (select max(session_date) from public.asx_session_observations)
 );
$$;
revoke execute on function public.asx_collection_storage() from public, anon, authenticated;
grant execute on function public.asx_collection_storage() to service_role;
