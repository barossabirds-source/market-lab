"""Add market backdrop to each automatically collected historical event candidate.

The event itself is only half the story. This script records what the broad market,
volatility, US 10-year yield, oil and US dollar were doing immediately before each event.
That allows later research to distinguish a policy pattern from the market regime in which
it occurred. It never places trades.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd
import requests
import yfinance as yf

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
CONTEXT_SYMBOLS = {
    "SPY": "broad_market",
    "^VIX": "volatility",
    "^TNX": "us_10y_yield",
    "CL=F": "oil",
    "DX-Y.NYB": "us_dollar",
}


def headers() -> dict[str, str]:
    h = {"apikey": SUPABASE_KEY, "Content-Type": "application/json"}
    if SUPABASE_KEY.startswith("eyJ"):
        h["Authorization"] = f"Bearer {SUPABASE_KEY}"
    return h


def rest(method: str, table: str, *, params: str = "", rows: Any | None = None, prefer: str | None = None) -> Any:
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if params:
        url += f"?{params}"
    h = headers()
    if prefer:
        h["Prefer"] = prefer
    response = requests.request(method, url, headers=h, data=json.dumps(rows) if rows is not None else None, timeout=90)
    if not response.ok:
        raise RuntimeError(f"Supabase {method} {table} failed: {response.status_code} {response.text[:500]}")
    return response.json() if response.text else None


def fetch_candidates() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    offset = 0
    while True:
        batch = rest(
            "GET", "event_candidates",
            params=f"select=id,event_date&auto_collected=eq.true&order=event_date.asc&limit=1000&offset={offset}",
        ) or []
        out.extend(batch)
        if len(batch) < 1000:
            return out
        offset += 1000


def chunks(items: list[dict[str, Any]], size: int = 250):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def download_context(start: date) -> pd.DataFrame:
    raw = yf.download(
        list(CONTEXT_SYMBOLS),
        start=start.isoformat(),
        end=(date.today() + timedelta(days=1)).isoformat(),
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="column",
    )
    if raw.empty:
        raise RuntimeError("No market-context data returned by yfinance")
    close = raw["Close"].copy() if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close.sort_index()


def value_at(series: pd.Series, pos: int) -> float | None:
    if pos < 0 or pos >= len(series):
        return None
    value = series.iloc[pos]
    return float(value) if pd.notna(value) else None


def pct_return(series: pd.Series, start_pos: int, end_pos: int) -> float | None:
    a = value_at(series, start_pos)
    b = value_at(series, end_pos)
    if a is None or b is None or a == 0:
        return None
    return b / a - 1.0


def absolute_change(series: pd.Series, start_pos: int, end_pos: int) -> float | None:
    a = value_at(series, start_pos)
    b = value_at(series, end_pos)
    if a is None or b is None:
        return None
    return b - a


def regime(vix: float | None, pre_spy: float | None, yield_change: float | None) -> str:
    labels: list[str] = []
    if vix is not None:
        if vix >= 30:
            labels.append("very_high_volatility")
        elif vix >= 22:
            labels.append("high_volatility")
        elif vix <= 15:
            labels.append("low_volatility")
        else:
            labels.append("normal_volatility")
    if pre_spy is not None:
        if pre_spy <= -0.03:
            labels.append("market_falling")
        elif pre_spy >= 0.03:
            labels.append("market_rising")
        else:
            labels.append("market_flat")
    if yield_change is not None:
        if yield_change >= 0.20:
            labels.append("yields_rising")
        elif yield_change <= -0.20:
            labels.append("yields_falling")
        else:
            labels.append("yields_stable")
    return "+".join(labels) if labels else "unknown"


def main() -> int:
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Supabase credentials missing; skipping context enrichment safely.")
        return 0
    candidates = fetch_candidates()
    if not candidates:
        print("No event candidates available for context enrichment.")
        return 0

    earliest = min(date.fromisoformat(str(c["event_date"])[:10]) for c in candidates) - timedelta(days=30)
    close = download_context(earliest)
    rows: list[dict[str, Any]] = []

    for c in candidates:
        event_date = pd.Timestamp(str(c["event_date"])[:10])
        pos = int(close.index.searchsorted(event_date, side="left")) - 1
        if pos < 0:
            continue

        def s(symbol: str) -> pd.Series:
            return close[symbol].dropna()

        # Because series can have different missing dates, align each to its own last date before event.
        def prior_pos(symbol: str) -> tuple[pd.Series, int] | tuple[None, None]:
            series = s(symbol)
            p = int(series.index.searchsorted(event_date, side="left")) - 1
            return (series, p) if p >= 0 else (None, None)

        spy, sp = prior_pos("SPY")
        vix, vp = prior_pos("^VIX")
        tnx, tp = prior_pos("^TNX")
        oil, op = prior_pos("CL=F")
        usd, dp = prior_pos("DX-Y.NYB")

        pre_spy = pct_return(spy, max(0, sp - 5), sp) if spy is not None else None
        vix_level = value_at(vix, vp) if vix is not None else None
        vix_change = absolute_change(vix, max(0, vp - 5), vp) if vix is not None else None
        yield_level = value_at(tnx, tp) if tnx is not None else None
        yield_change = absolute_change(tnx, max(0, tp - 5), tp) if tnx is not None else None
        oil_level = value_at(oil, op) if oil is not None else None
        oil_ret = pct_return(oil, max(0, op - 5), op) if oil is not None else None
        usd_level = value_at(usd, dp) if usd is not None else None
        usd_ret = pct_return(usd, max(0, dp - 5), dp) if usd is not None else None

        rows.append({
            "candidate_id": c["id"],
            "event_date": str(c["event_date"])[:10],
            "broad_market_pre_5d_return": pre_spy,
            "volatility_index_level": vix_level,
            "volatility_index_5d_change": vix_change,
            "us_10y_yield_pct": yield_level,
            "us_10y_yield_5d_change": yield_change,
            "oil_price": oil_level,
            "oil_5d_return": oil_ret,
            "us_dollar_index": usd_level,
            "us_dollar_5d_return": usd_ret,
            "market_regime": regime(vix_level, pre_spy, yield_change),
            "captured_at": datetime.now(timezone.utc).isoformat(),
        })

    for batch in chunks(rows):
        rest(
            "POST", "candidate_market_context", params="on_conflict=candidate_id", rows=batch,
            prefer="resolution=merge-duplicates,return=minimal",
        )
    print(f"Added market backdrop to {len(rows)} historical event candidates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
