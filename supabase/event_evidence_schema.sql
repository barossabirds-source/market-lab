-- Read-only derived research evidence. Private provider observations stay private.
create table public.event_hypotheses (
  hypothesis_key text primary key,
  registered_at timestamptz not null default now(),
  title text not null,
  event_category text not null,
  mechanism text not null,
  config jsonb not null check (octet_length(config::text) <= 8192)
);
create table public.event_predictions (
  hypothesis_key text not null references public.event_hypotheses,
  event_key text not null,
  session_date date not null,
  captured_at timestamptz not null default now(),
  source_url text not null,
  published_at timestamptz not null,
  prediction jsonb not null check (octet_length(prediction::text) <= 8192),
  primary key (hypothesis_key, event_key)
);
create table public.event_outcomes (
  hypothesis_key text not null references public.event_hypotheses,
  event_key text not null,
  session_date date not null,
  symbol text not null,
  source text not null,
  source_captured_at timestamptz not null,
  signal boolean,
  us_return_pct double precision,
  entry_at timestamptz,
  exit_at timestamptz,
  result jsonb not null check (octet_length(result::text) <= 8192),
  updated_at timestamptz not null default now(),
  primary key (hypothesis_key, event_key)
);
alter table public.event_hypotheses enable row level security;
alter table public.event_predictions enable row level security;
alter table public.event_outcomes enable row level security;
revoke all on public.event_hypotheses, public.event_predictions, public.event_outcomes from anon, authenticated;
grant select on public.event_hypotheses, public.event_predictions, public.event_outcomes to anon, authenticated;
revoke all on public.event_hypotheses, public.event_predictions, public.event_outcomes from service_role;
grant select, insert on public.event_hypotheses, public.event_predictions to service_role;
revoke update, delete on public.event_hypotheses, public.event_predictions from service_role;
grant select, insert, update on public.event_outcomes to service_role;
create policy "Read frozen hypotheses" on public.event_hypotheses for select to anon, authenticated using (true);
create policy "Read frozen predictions" on public.event_predictions for select to anon, authenticated using (true);
create policy "Read derived outcomes" on public.event_outcomes for select to anon, authenticated using (true);
create or replace function public.asx_collection_storage()
returns jsonb language sql security invoker set search_path = '' as $$
 select jsonb_build_object(
   'database_bytes', pg_database_size(current_database()),
   'study_bytes', pg_total_relation_size('public.asx_session_observations'::regclass)
       + pg_total_relation_size('public.asx_feed_status'::regclass)
       + pg_total_relation_size('public.event_hypotheses'::regclass)
       + pg_total_relation_size('public.event_predictions'::regclass)
       + pg_total_relation_size('public.event_outcomes'::regclass),
   'sessions', (select count(*) from public.asx_session_observations),
   'latest_session', (select max(session_date) from public.asx_session_observations)
 );
$$;
revoke execute on function public.asx_collection_storage() from public, anon, authenticated;
grant execute on function public.asx_collection_storage() to service_role;
