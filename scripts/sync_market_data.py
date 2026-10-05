"""Daily Market Lab data sync.

Reads the frozen event ledger from repository CSV files, downloads daily market
prices, stores both in Supabase, and calculates transparent event reactions.
This script deliberately does not create or send brokerage orders.
"""
from __future__ import annotations

import csv
import glob
import hashlib
import json
import math
import os
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pandas as pd
import requests
import yfinance as yf

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

BENCHMARK = "SPY"
HORIZONS = (1, 3, 5, 20)
CORE_UNIVERSE = {
    "SPY": ("Broad US Market", "Broad market"),
    "QQQ": ("Large US Technology", "Technology / growth"),
    "IWM": ("Smaller US Companies", "Company size"),
    "DIA": ("Large Established US Companies", "Large companies"),
    "XLK": ("US Technology", "Technology"),
    "XLF": ("US Financials", "Financials"),
    "KRE": ("US Regional Banks", "Financials"),
    "XLE": ("US Energy", "Energy"),
    "XLI": ("US Industrials", "Industrials"),
    "XLB": ("US Materials", "Materials"),
    "XLV": ("US Health Care", "Health care"),
    "XLY": ("US Consumer Discretionary", "Consumer"),
    "XLP": ("US Consumer Staples", "Consumer"),
    "XLU": ("US Utilities", "Utilities"),
    "SMH": ("Semiconductor Companies", "Semiconductors"),
    "SOXX": ("Semiconductor Companies", "Semiconductors"),
    "ITA": ("US Aerospace & Defence", "Defence"),
    "IBB": ("Biotechnology", "Biotechnology"),
    "XBI": ("Biotechnology", "Biotechnology"),
    "EEM": ("Emerging Markets", "International"),
}


def headers() -> dict[str, str]:
    h = {"apikey": SUPABASE_KEY, "Content-Type": "application/json"}
    # Legacy service_role keys are JWTs. New sb_secret keys must not be sent as Bearer JWTs.
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
    response = requests.request(method, url, headers=h, data=json.dumps(rows) if rows is not None else None, timeout=60)
    if not response.ok:
        raise RuntimeError(f"Supabase {method} {table} failed: {response.status_code} {response.text[:500]}")
    if not response.text:
        return None
    return response.json()


def chunks(items: list[dict[str, Any]], size: int = 500):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def clean(value: Any, default: str = "") -> str:
    if value is None:
        return default
    value = str(value).strip()
    return value if value else default


def event_key(row: dict[str, str]) -> str:
    raw = "|".join([clean(row.get("date")), clean(row.get("event_type")), clean(row.get("theme")), clean(row.get("summary"))])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def load_events() -> list[dict[str, Any]]:
    records: list[dict[str, str]] = []
    for path in sorted(glob.glob("trump_events*.csv")):
        with open(path, newline="", encoding="utf-8") as f:
            records.extend(csv.DictReader(f))
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    theme_counts: dict[str, int] = {}
    for row in sorted(records, key=lambda r: (clean(r.get("date")), clean(r.get("theme")), clean(r.get("summary")))):
        key = event_key(row)
        if key in seen:
            continue
        seen.add(key)
        theme = clean(row.get("theme"), "unknown")
        theme_counts[theme] = theme_counts.get(theme, 0) + 1
        occurrence = theme_counts[theme]
        symbols = [x.strip() for x in clean(row.get("etfs")).split(";") if x.strip()]
        source_url = clean(row.get("source"))
        out.append({
            "event_key": key,
            "event_date": clean(row.get("date")),
            "occurred_at": None,
            "available_at": None,
            "event_type": clean(row.get("event_type"), "unknown"),
            "source_type": clean(row.get("source_type"), "unknown"),
            "policy_theme": theme,
            "direction": clean(row.get("direction"), "unknown"),
            "surprise_level": clean(row.get("surprise_proxy"), "unknown"),
            "surprise_basis": clean(row.get("surprise_basis")),
            "market_session": clean(row.get("market_session"), "unknown"),
            "timing_confidence": clean(row.get("timing_confidence"), "low"),
            "summary": clean(row.get("summary")),
            "source_name": "White House" if "whitehouse.gov" in source_url else "Public source",
            "source_url": source_url or None,
            "candidate_symbols": symbols,
            "theme_occurrence_number": occurrence,
            "novelty_proxy": round(1.0 / math.sqrt(occurrence), 6),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
    return out


def download_prices(start: date) -> tuple[pd.DataFrame, pd.DataFrame]:
    symbols = list(CORE_UNIVERSE)
    raw = yf.download(
        symbols,
        start=start.isoformat(),
        end=(date.today() + timedelta(days=1)).isoformat(),
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="column",
    )
    if raw.empty:
        raise RuntimeError("No market data returned by yfinance")
    close = raw["Close"].copy() if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]].rename(columns={"Close": symbols[0]})
    volume = raw["Volume"].copy() if isinstance(raw.columns, pd.MultiIndex) else pd.DataFrame(index=close.index)
    close.index = pd.to_datetime(close.index).tz_localize(None)
    if not volume.empty:
        volume.index = pd.to_datetime(volume.index).tz_localize(None)
    return close.sort_index(), volume.sort_index()


def price_rows(close: pd.DataFrame, volume: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for symbol in close.columns:
        series = close[symbol].dropna()
        for ts, value in series.items():
            vol = None
            if symbol in volume.columns and ts in volume.index and pd.notna(volume.at[ts, symbol]):
                vol = int(volume.at[ts, symbol])
            rows.append({"symbol": symbol, "observed_on": ts.date().isoformat(), "adjusted_close": float(value), "volume": vol})
    return rows


def alignment(index: pd.DatetimeIndex, event_date: str, session: str) -> tuple[int, int] | None:
    d = pd.Timestamp(event_date)
    pos = int(index.searchsorted(d, side="left"))
    if pos >= len(index):
        return None
    session = clean(session, "unknown").lower()
    if session == "after_hours":
        base, first = pos, pos + 1
    else:
        base, first = max(0, pos - 1), pos
    return (base, first) if first < len(index) else None


def period_return(close: pd.DataFrame, symbol: str, start_pos: int, end_pos: int) -> float | None:
    if symbol not in close.columns or start_pos < 0 or end_pos >= len(close) or end_pos <= start_pos:
        return None
    a, b = close[symbol].iloc[start_pos], close[symbol].iloc[end_pos]
    if pd.isna(a) or pd.isna(b) or float(a) == 0:
        return None
    return float(b / a - 1.0)


def impact_rows(events: list[dict[str, Any]], event_ids: dict[str, str], close: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in events:
        align = alignment(close.index, event["event_date"], event["market_session"])
        if align is None or event["event_key"] not in event_ids:
            continue
        base, first = align
        quality = "daily_session_aligned" if event["market_session"] != "unknown" and event["timing_confidence"] in {"medium", "high"} else "daily_date_only"
        candidates = set(event["candidate_symbols"])
        for symbol, (asset_name, asset_group) in CORE_UNIVERSE.items():
            if symbol not in close.columns:
                continue
            for h in HORIZONS:
                end = first + h - 1
                asset = period_return(close, symbol, base, end)
                bench = period_return(close, BENCHMARK, base, end)
                pre_asset = period_return(close, symbol, base - h, base)
                pre_bench = period_return(close, BENCHMARK, base - h, base)
                abnormal = asset - bench if asset is not None and bench is not None else None
                pre_abnormal = pre_asset - pre_bench if pre_asset is not None and pre_bench is not None else None
                reaction = abnormal - pre_abnormal if abnormal is not None and pre_abnormal is not None else None
                rows.append({
                    "event_id": event_ids[event["event_key"]],
                    "event_date": event["event_date"],
                    "symbol": symbol,
                    "asset_name": asset_name,
                    "asset_group": asset_group,
                    "benchmark_symbol": BENCHMARK,
                    "horizon": f"{h}d",
                    "asset_return": asset,
                    "benchmark_return": bench,
                    "abnormal_return": abnormal,
                    "pre_event_abnormal_return": pre_abnormal,
                    "reaction_vs_pre": reaction,
                    "is_candidate": symbol in candidates,
                    "data_quality": quality,
                    "calculated_at": datetime.now(timezone.utc).isoformat(),
                })
    return rows


def main() -> int:
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("SUPABASE_URL and SUPABASE_SECRET_KEY (or legacy SUPABASE_SERVICE_ROLE_KEY) are required.", file=sys.stderr)
        return 2

    run = rest("POST", "sync_runs", rows=[{"status": "running"}], prefer="return=representation")
    run_id = run[0]["id"]
    try:
        events = load_events()
        if not events:
            raise RuntimeError("No event CSV records found")
        for batch in chunks(events):
            rest("POST", "events", params="on_conflict=event_key", rows=batch, prefer="resolution=merge-duplicates,return=minimal")

        stored = rest("GET", "events", params="select=id,event_key&limit=1000")
        event_ids = {x["event_key"]: x["id"] for x in stored}

        first_date = min(date.fromisoformat(e["event_date"]) for e in events) - timedelta(days=40)
        close, volume = download_prices(first_date)
        observations = price_rows(close, volume)
        for batch in chunks(observations):
            rest("POST", "market_observations", params="on_conflict=symbol,observed_on", rows=batch, prefer="resolution=merge-duplicates,return=minimal")

        impacts = impact_rows(events, event_ids, close)
        for batch in chunks(impacts):
            rest("POST", "event_impacts", params="on_conflict=event_id,symbol,horizon", rows=batch, prefer="resolution=merge-duplicates,return=minimal")

        finished = datetime.now(timezone.utc).isoformat()
        rest("PATCH", "sync_runs", params=f"id=eq.{run_id}", rows={
            "status": "completed", "finished_at": finished,
            "events_written": len(events), "observations_written": len(observations), "impacts_written": len(impacts),
            "message": "Daily research data sync completed; no trading orders were created.",
        }, prefer="return=minimal")
        print(f"Synced {len(events)} events, {len(observations)} prices and {len(impacts)} event-impact rows.")
        return 0
    except Exception as exc:
        rest("PATCH", "sync_runs", params=f"id=eq.{run_id}", rows={
            "status": "failed", "finished_at": datetime.now(timezone.utc).isoformat(), "message": str(exc)[:1000]
        }, prefer="return=minimal")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
