-- Market Lab research-first schema.
-- Run once in the Supabase SQL editor, then run the GitHub data-sync workflow.

create extension if not exists pgcrypto;

create table if not exists public.events (
  id uuid primary key default gen_random_uuid(),
  event_key text not null unique,
  event_date date not null,
  occurred_at timestamptz,
  available_at timestamptz,
  event_type text not null,
  source_type text not null,
  policy_theme text not null,
  direction text not null default 'unknown',
  surprise_level text not null default 'unknown',
  surprise_basis text,
  market_session text not null default 'unknown',
  timing_confidence text not null default 'low',
  summary text not null,
  source_name text,
  source_url text,
  candidate_symbols text[] not null default '{}',
  theme_occurrence_number integer,
  novelty_proxy numeric,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.market_observations (
  symbol text not null,
  observed_on date not null,
  adjusted_close numeric not null,
  volume bigint,
  source text not null default 'Yahoo Finance via yfinance',
  captured_at timestamptz not null default now(),
  primary key (symbol, observed_on)
);

create table if not exists public.event_impacts (
  event_id uuid not null references public.events(id) on delete cascade,
  event_date date not null,
  symbol text not null,
  asset_name text not null,
  asset_group text not null,
  benchmark_symbol text not null default 'SPY',
  horizon text not null,
  asset_return numeric,
  benchmark_return numeric,
  abnormal_return numeric,
  pre_event_abnormal_return numeric,
  reaction_vs_pre numeric,
  is_candidate boolean not null default false,
  data_quality text not null default 'daily_date_only',
  calculated_at timestamptz not null default now(),
  primary key (event_id, symbol, horizon)
);

create table if not exists public.research_trials (
  id uuid primary key default gen_random_uuid(),
  trial_key text not null unique,
  registered_at timestamptz not null default now(),
  hypothesis text not null,
  policy_theme text,
  horizon text not null,
  test_method text not null,
  status text not null default 'registered',
  event_count integer,
  average_effect numeric,
  hit_rate numeric,
  out_of_sample_effect numeric,
  result_summary text,
  notes text
);

create table if not exists public.sync_runs (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null,
  events_written integer not null default 0,
  observations_written integer not null default 0,
  impacts_written integer not null default 0,
  message text
);

alter table public.events enable row level security;
alter table public.market_observations enable row level security;
alter table public.event_impacts enable row level security;
alter table public.research_trials enable row level security;
alter table public.sync_runs enable row level security;

grant usage on schema public to anon, authenticated;
grant select on public.events, public.event_impacts, public.research_trials, public.sync_runs to anon, authenticated;
grant all on public.events, public.market_observations, public.event_impacts, public.research_trials, public.sync_runs to service_role;

-- Public dashboard reads only research outputs. No public INSERT/UPDATE/DELETE policies are created.
do $$ begin
  create policy "public read events" on public.events for select to anon, authenticated using (true);
exception when duplicate_object then null; end $$;
do $$ begin
  create policy "public read impacts" on public.event_impacts for select to anon, authenticated using (true);
exception when duplicate_object then null; end $$;
do $$ begin
  create policy "public read trials" on public.research_trials for select to anon, authenticated using (true);
exception when duplicate_object then null; end $$;
do $$ begin
  create policy "public read sync runs" on public.sync_runs for select to anon, authenticated using (true);
exception when duplicate_object then null; end $$;

insert into public.research_trials (trial_key,hypothesis,policy_theme,horizon,test_method,status,result_summary)
values
('tariff-industrials-vs-tech-3d','High-surprise tariff escalations are followed by stronger 3-day relative performance in US industrial companies than in large technology companies.','tariffs','3d','Compare XLI and QQQ after pre-registered qualifying events. Report event count, average difference and consistency before any simulated rule is considered.','registered','Awaiting sufficient measured events.'),
('energy-formal-vs-remarks-5d','Formal energy-support actions produce a larger 5-day energy-sector reaction than public remarks about energy.','energy','5d','Compare XLE relative moves for formal actions versus remarks, keeping event labels frozen before outcomes are inspected.','registered','Awaiting sufficient measured events.'),
('formal-action-dispersion-1d','Formal policy actions create greater one-day sector dispersion than routine public remarks.','all','1d','Calculate the strongest-minus-weakest sector response for each event and compare formal actions with remarks.','registered','Awaiting sufficient measured events.')
on conflict (trial_key) do nothing;
