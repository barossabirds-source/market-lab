import pandas as pd

def load_trump_events(path="trump_events.csv"):
    events = pd.read_csv(path, parse_dates=["date"])
    events["etf_list"] = events["etfs"].fillna("").map(
        lambda s: [x.strip() for x in s.split(";") if x.strip()]
    )
    return events

def _next_trading_index(index, event_date):
    pos = index.searchsorted(pd.Timestamp(event_date), side="left")
    return pos if pos < len(index) else None

def trump_event_study(prices, benchmark="SPY", events_path="trump_events.csv", horizons=(1, 3, 5)):
    events = load_trump_events(events_path)
    rows = []
    for _, ev in events.iterrows():
        for ticker in ev["etf_list"]:
            if ticker not in prices.columns or benchmark not in prices.columns:
                continue
            pos = _next_trading_index(prices.index, ev["date"])
            if pos is None or pos >= len(prices) - 1:
                continue
            start = float(prices[ticker].iloc[pos])
            bstart = float(prices[benchmark].iloc[pos])
            record = {
                "date": ev["date"],
                "event_type": ev["event_type"],
                "theme": ev["theme"],
                "summary": ev["summary"],
                "ticker": ticker,
                "source": ev["source"],
            }
            for h in horizons:
                end = min(pos + h, len(prices) - 1)
                asset = float(prices[ticker].iloc[end] / start - 1)
                bench = float(prices[benchmark].iloc[end] / bstart - 1)
                record[f"ret_{h}d"] = asset
                record[f"abn_{h}d"] = asset - bench
            rows.append(record)
    return pd.DataFrame(rows)

def trump_theme_summary(study, horizon=1):
    if study.empty:
        return pd.DataFrame()
    col = f"abn_{horizon}d"
    grouped = study.groupby(["theme", "ticker"]).agg(
        events=(col, "count"),
        avg_abnormal=(col, "mean"),
        median_abnormal=(col, "median"),
        positive_rate=(col, lambda x: float((x > 0).mean())),
    ).reset_index()
    return grouped.sort_values(["avg_abnormal", "events"], ascending=[False, False])
