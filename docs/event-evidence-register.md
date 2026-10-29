# Event evidence register

The dashboard's **Event evidence register** follows the frozen `wall-street-up-asx-v1` hypothesis. This is association research, with no brokerage orders and no paid feeds.

## Frozen rule

- S&P 500 previous completed session return above zero is the event. Zero and negative sessions are the comparison group.
- A200.AX at exactly 10:05 and 15:55 Australia/Sydney, using observed minute-bar opens as research proxies.
- A$2,000 fixed exposure, A$10 round-trip brokerage, 10 basis points round-trip spread/slippage: A$12 total estimated cost. Tax and whole units excluded.
- Pause at A$200 cumulative fixed-exposure signal drawdown. Review after 60 usable forward signal observations; reject support if mean is nonpositive or does not exceed comparison mean. At least 30 per group is only a preliminary review threshold.
- Config is insert-only and compared on each run. Changing the rule requires a new key and validation period. The registration timestamp comes from the database's first insertion, not a historical date chosen later.

## Capture and update

The existing GitHub Actions job gains UTC morning schedules at 22:35 and 23:35 Sunday–Thursday. These cover daylight-saving and standard Sydney time; only a run arriving between 09:30 and 10:00 Sydney on an ASX session can freeze a prediction. Delayed jobs outside that window do not backdate. GitHub schedules are best-effort, not guaranteed executions.

The existing after-close job stores raw observations privately as before, then derives one outcome per hypothesis/session from the first acquired provider observations. It reads all pages, keeps missing and comparison sessions, and never treats an absent bar as a zero or a losing return. Repeated runs do not duplicate events or change frozen predictions. Revision mismatches between morning US observations and evening observations are excluded.

Tables:

- `event_hypotheses`: immutable version, mechanism, rule, costs and review thresholds.
- `event_predictions`: immutable source link, publication time, actual capture time and directional expectation, including comparison-day predictions.
- `event_outcomes`: recalculable derived result, quality, exclusions, whether prediction was frozen before entry, and explicit unreviewed confounder/surprise fields. No raw provider quote payload is published.
- `asx_feed_status`: compact summary and operational status. The summary fits the existing 4 KB details limit.

Public dashboard roles can read derived evidence but cannot insert/update/delete it. The service role can insert hypotheses/predictions and update derived outcomes; application grants prohibit editing/deleting frozen records. The database owner remains an administrator, so this is not a tamper-proof external audit log. No secret key belongs in browser code.

## Reading the results

1. **All collected prices** is exploratory and includes observations acquired before this rule was registered.
2. **Prediction saved before entry** includes matching morning captures after registration, but prices remain proxies.
3. **Verified execution** remains zero: the current Yahoo feed supplies no independently verified executable quotes. No date split alone establishes validation.

The table compares group means, medians, win rates, average win/loss and fixed-size cumulative drawdown. Wilson win-rate intervals and normal-approximation mean intervals describe sampling uncertainty under independent sessions. They do not adjust for serial dependence or multiple testing; shared-news explanations, overlapping events, market regimes and tax are not controlled. A high hit rate or an arbitrary sample threshold never certifies causation or a tradable edge.

The latest 60 derived sessions appear on screen; **Download evidence** exports all fetched pages, frozen rule, predictions and current summary. Missing morning captures remain visible. Surprise, confounder review and intraday adverse/favourable excursions are explicitly unmeasured; no AI invents them.

## Setup and checks

Apply `supabase/event_evidence_schema.sql` once to the existing project, deploy the updated dashboard and collector from the same commit, then run the existing ASX collection workflow. Existing GitHub secrets are reused. Do not run duplicate collector schedules elsewhere.

Run `python -m unittest discover -s tests -p 'test_event_evidence.py'`, the existing ASX Python tests, `node --test tests/asx-study.test.cjs`, and `node --check web/event-evidence.js`.
