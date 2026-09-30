import pandas as pd
import numpy as np

REQUIRED_META = {
    "source_type": "unknown",
    "direction": "unknown",
    "surprise_proxy": "unknown",
    "surprise_basis": "",
    "market_session": "unknown",
    "event_time_et": "",
    "timing_confidence": "low",
}

def load_trump_events(path="trump_events.csv"):
    events = pd.read_csv(path, parse_dates=["date"])
    for col, default in REQUIRED_META.items():
        if col not in events.columns:
            events[col] = default
        events[col] = events[col].fillna(default)
    events["etf_list"] = events["etfs"].fillna("").map(
        lambda s: [x.strip() for x in s.split(";") if x.strip()]
    )
    return events

def _event_position(index, event_date):
    pos = index.searchsorted(pd.Timestamp(event_date), side="left")
    return pos if pos < len(index) else None

def _alignment(index, event_date, session):
    pos = _event_position(index, event_date)
    if pos is None:
        return None
    # Daily-close approximation:
    # pre-market/during-market events use the previous close as baseline;
    # after-hours events use that day's close as baseline.
    session = str(session or "unknown").lower()
    if session == "after_hours":
        base = pos
        first_reaction = pos + 1
    else:
        base = max(0, pos - 1)
        first_reaction = pos
    return base, first_reaction

def _relative_return(prices, ticker, benchmark, start_pos, end_pos):
    if start_pos < 0 or end_pos >= len(prices) or end_pos <= start_pos:
        return np.nan, np.nan
    asset = float(prices[ticker].iloc[end_pos] / prices[ticker].iloc[start_pos] - 1)
    bench = float(prices[benchmark].iloc[end_pos] / prices[benchmark].iloc[start_pos] - 1)
    return asset, asset - bench

def trump_event_study(prices, benchmark="SPY", events_path="trump_events.csv", horizons=(1, 3, 5)):
    """Build a point-in-time event ledger and measure reactions without rewriting event labels after outcomes are known."""
    """Build a point-in-time event ledger and measure market reactions without rewriting event labels after outcomes are known."""
    events = load_trump_events(events_path)
    rows = []
    for _, ev in events.iterrows():
        alignment = _alignment(prices.index, ev["date"], ev["market_session"])
        if alignment is None:
            continue
        base, first = alignment
        for ticker in ev["etf_list"]:
            if ticker not in prices.columns or benchmark not in prices.columns:
                continue
            record = {
                "date": ev["date"],
                "event_type": ev["event_type"],
                "source_type": ev["source_type"],
                "theme": ev["theme"],
                "direction": ev["direction"],
                "surprise_proxy": ev["surprise_proxy"],
                "surprise_basis": ev["surprise_basis"],
                "market_session": ev["market_session"],
                "event_time_et": ev["event_time_et"],
                "timing_confidence": ev["timing_confidence"],
                "summary": ev["summary"],
                "ticker": ticker,
                "source": ev["source"],
                # Frozen event ledger fields: these describe what was known/classified at the event, not its later outcome.
                "ledger_id": f'{pd.Timestamp(ev["date"]).date()}|{ev["event_type"]}|{ticker}',
                "benchmark": benchmark,
                "baseline_date": prices.index[base],
                "first_reaction_date": prices.index[first] if first < len(prices) else pd.NaT,
                "baseline_price": float(prices[ticker].iloc[base]),
                "benchmark_baseline_price": float(prices[benchmark].iloc[base]),
            }

            # Pre-event/control movement. This helps distinguish an event reaction from a move already underway.
            for h in (1, 3, 5):
                pre_start = base - h
                pre_asset, abnormal = _relative_return(prices, ticker, benchmark, pre_start, base)
                record[f"pre_ret_{h}d"] = pre_asset
                record[f"pre_abn_{h}d"] = abnormal

            # Reaction horizons begin with the first session capable of reflecting the event.
            for h in horizons:
                end = first + h - 1
                asset, abnormal = _relative_return(prices, ticker, benchmark, base, end)
                record[f"ret_{h}d"] = asset
                record[f"abn_{h}d"] = abnormal
                pre_control = record.get(f"pre_abn_{h}d", np.nan)
                record[f"reaction_vs_pre_{h}d"] = abnormal - pre_control if pd.notna(pre_control) else np.nan
                # Incremental reaction versus the same-length pre-event abnormal move.
                pre_control = record.get(f"pre_abn_{h}d", np.nan)
                record[f"reaction_vs_pre_{h}d"] = abnormal - pre_control if pd.notna(pre_control) else np.nan
            rows.append(record)
    return pd.DataFrame(rows)

def grouped_event_summary(study, group_cols, horizon=1):
    if study.empty:
        return pd.DataFrame()
    col = f"abn_{horizon}d"
    valid = study.dropna(subset=[col]).copy()
    if valid.empty:
        return pd.DataFrame()
    grouped = valid.groupby(group_cols).agg(
        events=("date", "nunique"),
        observations=(col, "count"),
        avg_abnormal=(col, "mean"),
        median_abnormal=(col, "median"),
        positive_rate=(col, lambda x: float((x > 0).mean())),
        avg_pre_1d=("pre_abn_1d", "mean"),
        avg_pre_3d=("pre_abn_3d", "mean"),
        avg_pre_5d=("pre_abn_5d", "mean"),
        avg_reaction_vs_pre=(f"reaction_vs_pre_{horizon}d", "mean"),
        avg_pre_5d=("pre_abn_5d", "mean"),
        avg_reaction_vs_pre=(f"reaction_vs_pre_{horizon}d", "mean"),
    ).reset_index()
    return grouped.sort_values(["avg_abnormal", "events"], ascending=[False, False])

def trump_theme_summary(study, horizon=1):
    return grouped_event_summary(study, ["theme", "ticker"], horizon)

def source_direction_summary(study, horizon=1):
    return grouped_event_summary(study, ["source_type", "direction"], horizon)

def surprise_summary(study, horizon=1):
    return grouped_event_summary(study, ["surprise_proxy"], horizon)

def timing_summary(study, horizon=1):
    return grouped_event_summary(study, ["market_session"], horizon)
