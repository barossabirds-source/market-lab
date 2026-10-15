# Market Lab

> **Primary application:** Netlify web dashboard at https://market-lab-trading.netlify.app  
> **Data layer:** Supabase (to be connected for persistent event, market and signal history)  
> **Source control and scheduled research jobs:** GitHub  
> **Legacy prototype:** Streamlit/Python files remain in the repository for research and backup only.

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

The older Streamlit research files remain in the repository for local analysis and backup only. Netlify is now the primary Market Lab interface and serves the dashboard in `/web`.

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

## Overnight Wall Street → ASX study

The dashboard's **Overnight ASX study** tests a fixed rule recorded on 16 October 2026: positive S&P 500 close-to-close return and SPI futures up at least 0.5% at 09:30 Australia/Sydney; enter a single ASX ETF at 10:05 and exit at 15:55. It separates the opening gap from tradable post-entry returns.

No SPI or Australian intraday feed is connected. Import observed sessions using `web/asx-observations-template.csv`; field definitions, sourcing limitations and calculation details are in `web/asx-data-guide.html`. Imports remain in memory in the browser tab and are not uploaded or persisted. Include non-signal sessions for the comparator. Earlier history and the prospective rule period are reported separately; neither an import nor the date split certifies point-in-time integrity.

Run calculation checks with `node --test tests/asx-study.test.cjs`.

### Strategy recording repair

The daily job must run `python -m scripts.sync_strategy_signals` from the repository root. Directly running the script by path excludes the root from Python's module search and failed to import `engine`. Signal persistence now runs even if another research step fails, unless the workflow is cancelled or secrets are missing. Empty downloads or empty generated snapshots fail explicitly. A completed research sync is distinct from successful strategy recording.
