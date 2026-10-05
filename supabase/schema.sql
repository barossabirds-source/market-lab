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

-- Automatically collected official documents are kept separate from the curated event ledger.
-- This prevents an automated classification from silently becoming a trading rule.
create table if not exists public.event_candidates (
  id uuid primary key default gen_random_uuid(),
  candidate_key text not null unique,
  event_date date not null,
  signing_date date,
  publication_date date,
  document_number text,
  title text not null,
  abstract text,
  source_url text,
  source_name text not null default 'Federal Register',
  source_kind text not null default 'presidential_document',
  document_subtype text,
  executive_order_number text,
  proclamation_number text,
  policy_theme text not null,
  direction_guess text not null default 'unknown',
  relevance_score integer not null default 0,
  affected_symbols text[] not null default '{}',
  classification_basis text,
  review_status text not null default 'candidate',
  auto_collected boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.candidate_event_impacts (
  candidate_id uuid not null references public.event_candidates(id) on delete cascade,
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
  data_quality text not null default 'daily_date_only',
  calculated_at timestamptz not null default now(),
  primary key (candidate_id, symbol, horizon)
);

-- Market conditions immediately before an automatically collected event candidate.
-- These fields let later research distinguish an apparent event effect from the market backdrop.
create table if not exists public.candidate_market_context (
  candidate_id uuid primary key references public.event_candidates(id) on delete cascade,
  event_date date not null,
  broad_market_pre_5d_return numeric,
  volatility_index_level numeric,
  volatility_index_5d_change numeric,
  us_10y_yield_pct numeric,
  us_10y_yield_5d_change numeric,
  oil_price numeric,
  oil_5d_return numeric,
  us_dollar_index numeric,
  us_dollar_5d_return numeric,
  market_regime text,
  captured_at timestamptz not null default now()
);

create table if not exists public.historical_discoveries (
  discovery_key text primary key,
  policy_theme text not null,
  direction_guess text not null,
  symbol text not null,
  asset_name text not null,
  asset_group text not null,
  horizon text not null,
  event_count integer not null,
  average_return numeric,
  median_return numeric,
  hit_rate numeric,
  worst_return numeric,
  best_return numeric,
  average_abnormal_return numeric,
  beat_market_rate numeric,
  first_term_count integer not null default 0,
  first_term_average numeric,
  second_term_count integer not null default 0,
  second_term_average numeric,
  source_dataset text not null default 'auto_federal_register_candidates',
  status text not null default 'exploratory_auto',
  calculated_at timestamptz not null default now()
);

create table if not exists public.backfill_runs (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null,
  documents_fetched integer not null default 0,
  candidates_written integer not null default 0,
  impacts_written integer not null default 0,
  discoveries_written integer not null default 0,
  message text
);

alter table public.events enable row level security;
alter table public.market_observations enable row level security;
alter table public.event_impacts enable row level security;
alter table public.research_trials enable row level security;
alter table public.sync_runs enable row level security;
alter table public.event_candidates enable row level security;
alter table public.candidate_event_impacts enable row level security;
alter table public.candidate_market_context enable row level security;
alter table public.historical_discoveries enable row level security;
alter table public.backfill_runs enable row level security;

grant usage on schema public to anon, authenticated;
grant select on public.events, public.event_impacts, public.research_trials, public.sync_runs,
  public.event_candidates, public.candidate_event_impacts, public.candidate_market_context,
  public.historical_discoveries, public.backfill_runs to anon, authenticated;
grant all on public.events, public.market_observations, public.event_impacts, public.research_trials, public.sync_runs,
  public.event_candidates, public.candidate_event_impacts, public.candidate_market_context,
  public.historical_discoveries, public.backfill_runs to service_role;

-- Public dashboard reads only research outputs. No public INSERT/UPDATE/DELETE policies are created.
do $$ begin create policy "public read events" on public.events for select to anon, authenticated using (true); exception when duplicate_object then null; end $$;
do $$ begin create policy "public read impacts" on public.event_impacts for select to anon, authenticated using (true); exception when duplicate_object then null; end $$;
do $$ begin create policy "public read trials" on public.research_trials for select to anon, authenticated using (true); exception when duplicate_object then null; end $$;
do $$ begin create policy "public read sync runs" on public.sync_runs for select to anon, authenticated using (true); exception when duplicate_object then null; end $$;
do $$ begin create policy "public read event candidates" on public.event_candidates for select to anon, authenticated using (true); exception when duplicate_object then null; end $$;
do $$ begin create policy "public read candidate impacts" on public.candidate_event_impacts for select to anon, authenticated using (true); exception when duplicate_object then null; end $$;
do $$ begin create policy "public read candidate market context" on public.candidate_market_context for select to anon, authenticated using (true); exception when duplicate_object then null; end $$;
do $$ begin create policy "public read historical discoveries" on public.historical_discoveries for select to anon, authenticated using (true); exception when duplicate_object then null; end $$;
do $$ begin create policy "public read backfill runs" on public.backfill_runs for select to anon, authenticated using (true); exception when duplicate_object then null; end $$;

create index if not exists event_candidates_theme_idx on public.event_candidates(policy_theme, direction_guess, event_date);
create index if not exists candidate_impacts_lookup_idx on public.candidate_event_impacts(symbol, horizon, event_date);
create index if not exists candidate_market_context_date_idx on public.candidate_market_context(event_date);

insert into public.research_trials (trial_key,hypothesis,policy_theme,horizon,test_method,status,result_summary)
values
('tariff-industrials-vs-tech-3d','High-surprise tariff escalations are followed by stronger 3-day relative performance in US industrial companies than in large technology companies.','tariffs','3d','Compare XLI and QQQ after pre-registered qualifying events. Report event count, average difference and consistency before any simulated rule is considered.','registered','Awaiting sufficient measured events.'),
('energy-formal-vs-remarks-5d','Formal energy-support actions produce a larger 5-day energy-sector reaction than public remarks about energy.','energy','5d','Compare XLE relative moves for formal actions versus remarks, keeping event labels frozen before outcomes are inspected.','registered','Awaiting sufficient measured events.'),
('formal-action-dispersion-1d','Formal policy actions create greater one-day sector dispersion than routine public remarks.','all','1d','Calculate the strongest-minus-weakest sector response for each event and compare formal actions with remarks.','registered','Awaiting sufficient measured events.'),
('infrastructure-support-industrials-3d-future','Formal US infrastructure or domestic-manufacturing support actions are followed by a positive 3-trading-day return in the US industrials fund XLI.','infrastructure_manufacturing','3d','From 5 Oct 2026 onward, use newly collected official Presidential Documents classified before outcomes as infrastructure/manufacturing sector-support actions. Measure XLI over 3 trading days and keep the trigger, fund and holding period frozen.','registered','Future-only validation is active from 5 Oct 2026.')
on conflict (trial_key) do nothing;
