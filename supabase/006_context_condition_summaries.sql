-- Market Lab: exploratory pre-event market-context summaries.
-- Applied to the live Supabase project on 6 Oct 2026.

create table if not exists public.context_condition_summaries (
  summary_key text primary key,
  policy_theme text not null,
  direction_guess text not null,
  symbol text not null,
  horizon text not null,
  condition_name text not null,
  condition_value text not null,
  condition_label text not null,
  event_count integer not null,
  average_return numeric,
  hit_rate numeric,
  average_abnormal_return numeric,
  beat_market_rate numeric,
  worst_return numeric,
  best_return numeric,
  base_event_count integer not null,
  base_average_return numeric,
  base_hit_rate numeric,
  return_lift numeric,
  hit_rate_lift numeric,
  source_dataset text not null default 'federal_register_context_v1',
  status text not null default 'exploratory_context',
  calculated_at timestamptz not null default now()
);

alter table public.context_condition_summaries enable row level security;
grant select on public.context_condition_summaries to anon, authenticated;
grant all on public.context_condition_summaries to service_role;
do $$ begin
  create policy "public read context condition summaries"
  on public.context_condition_summaries for select to anon, authenticated using (true);
exception when duplicate_object then null;
end $$;

create index if not exists context_condition_lookup_idx
  on public.context_condition_summaries(policy_theme,direction_guess,symbol,horizon,condition_name);
