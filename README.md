# Market Lab

Market Lab is a research-first application for studying how public policy events are followed by different market reactions. It keeps event facts, proposed explanations, measured outcomes and simulated strategies separate.

## What changed in this version

The Netlify dashboard adds a **Policy Impact Map** that compares market areas after each recorded event. Market Lab measures the same core set of funds for every event instead of hard-coding a trade. Funds thought to be relevant before the event are stored only as *candidates* so the data can disagree with the original idea.

The event ledger records formal actions versus remarks, escalation/de-escalation, surprise level, market-session timing and source evidence. It also records a simple novelty proxy based on how often the same theme has already appeared. Unknown timing remains unknown rather than being invented.

Research ideas are registered before their outcomes are inspected. Live brokerage execution is deliberately absent. The final gate is simulated trading on genuinely new data.

## Free-tier architecture

- **GitHub**: source code, event CSVs and a scheduled Python data-sync workflow.
- **Netlify**: static web dashboard. No always-on server is required.
- **Supabase Free**: PostgreSQL storage for the event ledger, daily market observations, measured event reactions, trial register and sync history.
- **Market prices**: downloaded by the GitHub workflow with `yfinance`; the source is recorded in the database.

The older Streamlit research files remain in the repository for local analysis. Netlify serves the lightweight dashboard in `/web`.

## 1. Create the Supabase database

Create a Supabase Free project, open the SQL editor, and run:

`supabase/schema.sql`

The schema enables Row Level Security on every exposed table. The public dashboard gets read-only access to events, measured impacts, trial records and sync status. It gets no public write policy. Keep the secret key out of the browser.

## 2. Configure Netlify

Import this GitHub repository into Netlify. `netlify.toml` already defines the build and publish settings.

Add these Netlify environment variables:

- `SUPABASE_URL`
- `SUPABASE_PUBLISHABLE_KEY`

The build script writes those public values into `web/runtime-config.js`. The publishable key is intended for browser use; Row Level Security controls what it can read.

Do **not** add the Supabase secret key to browser code.

## 3. Configure the GitHub daily sync

In GitHub repository secrets, add:

- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY`

If the Supabase project still uses a legacy service-role key, `SUPABASE_SERVICE_ROLE_KEY` is temporarily supported instead.

Then run **Actions → Market Lab daily research sync → Run workflow** once manually. The workflow also runs after US market hours on weekdays. If the secrets have not been configured, it exits safely without failing the repository.

## 4. What the daily sync does

1. Reads `trump_events.csv` plus any `trump_events*.csv` additions.
2. Freezes the event classification and source record.
3. Downloads daily prices for the common market universe.
4. Stores daily observations in Supabase.
5. Measures 1, 3, 5 and 20 trading-day reactions against the broad US market.
6. Compares the post-event relative move with the same-length pre-event move.
7. Marks whether a fund had been nominated as an affected candidate before the result was known.

The dashboard does not claim the event caused the market move. It displays association, data quality and pre-event movement so causal stories remain testable rather than assumed.

## Intraday data

The interface intentionally does not fabricate 30-minute or two-hour reactions. Those fields should be added only after a reliable intraday feed is captured consistently. Daily periods are the current evidence base.

## Run the legacy Python lab locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Safety

Market Lab is research software. It does not place live orders. Historical performance and event associations do not establish future profitability.
