-- Market Lab: manual review fields for automatically generated market-context leads.
-- Applied to the live Supabase project on 6 Oct 2026.

alter table public.context_condition_summaries
  add column if not exists review_status text not null default 'unreviewed';

alter table public.context_condition_summaries
  add column if not exists review_notes text;

create index if not exists context_condition_review_idx
  on public.context_condition_summaries(review_status);
