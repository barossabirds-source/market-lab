"""Explore whether simple pre-event market conditions change historically observed policy patterns.

This is an exploratory layer only. It does not create or modify frozen trading rules. The
script uses the same conservative event treatment as the historical discovery engine:
predefined theme-to-fund mappings, obvious routine-document exclusions, same-day collapse,
and non-overlapping holding windows. It then tests only simple, human-readable context
categories such as market direction and volatility level.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date, timedelta
from statistics import mean
from typing import Any, Callable

import requests

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SOURCE_DATASET = "federal_register_context_v1"
MIN_GAP_DAYS = {"1d": 2, "3d": 5, "5d": 8, "20d": 30}
ACTIONABLE_DIRECTIONS = {"escalation", "deescalation", "sector_support", "deregulation"}
SHORT_HORIZONS = {"1d", "3d", "5d"}

THEME_SYMBOLS: dict[str, set[str]] = {
    "china_trade": {"SOXX", "SMH", "QQQ", "XLK", "EEM", "XLI"},
    "trade_tariffs": {"XLI", "XLB", "SOXX", "QQQ", "XLY", "IWM", "EEM"},
    "energy": {"XLE", "XLI", "XLB", "XLU"},
    "defense": {"ITA", "XLI"},
    "financial_regulation": {"XLF", "KRE", "QQQ"},
    "technology_semiconductors": {"SOXX", "SMH", "QQQ", "XLK"},
    "healthcare_pharma": {"XLV", "IBB", "XBI"},
    "infrastructure_manufacturing": {"XLI", "XLB", "IWM"},
    "sanctions_geopolitics": {"EEM", "XLE", "ITA", "QQQ"},
    "tax_fiscal": {"SPY", "XLF", "IWM", "XLI"},
    "labor_immigration": {"IWM", "XLY", "XLI"},
}

ROUTINE_TITLE_PATTERNS = (
    "continuation of the national emergency",
    "sequestration order for fiscal year",
    "presidential determination on refugee admissions",
    "order of succession within",
    "providing an order of succession within",
)


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


def fetch_all(table: str, select: str, extra: str = "") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    offset = 0
    step = 1000
    while True:
        parts = [f"select={select}", f"limit={step}", f"offset={offset}"]
        if extra:
            parts.append(extra)
        batch = rest("GET", table, params="&".join(parts)) or []
        out.extend(batch)
        if len(batch) < step:
            return out
        offset += step


def chunks(items: list[dict[str, Any]], size: int = 200):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def obvious_routine(title: str) -> bool:
    t = title.lower().strip()
    return any(p in t for p in ROUTINE_TITLE_PATTERNS)


def non_overlapping(rows: list[dict[str, Any]], horizon: str) -> list[dict[str, Any]]:
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        d = str(row.get("event_date") or "")[:10]
        if d:
            by_date.setdefault(d, []).append(row)

    collapsed: list[dict[str, Any]] = []
    for d, same_day in sorted(by_date.items()):
        vals = [float(r["asset_return"]) for r in same_day if r.get("asset_return") is not None]
        abn = [float(r["abnormal_return"]) for r in same_day if r.get("abnormal_return") is not None]
        if not vals:
            continue
        sample = dict(same_day[0])
        sample["asset_return"] = mean(vals)
        sample["abnormal_return"] = mean(abn) if abn else None
        sample["event_date"] = d
        collapsed.append(sample)

    gap = MIN_GAP_DAYS.get(horizon, 8)
    kept: list[dict[str, Any]] = []
    last_date: date | None = None
    for row in collapsed:
        d = date.fromisoformat(str(row["event_date"])[:10])
        if last_date is None or d >= last_date + timedelta(days=gap):
            kept.append(row)
            last_date = d
    return kept


def num(row: dict[str, Any], key: str) -> float | None:
    v = row.get(key)
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def market_direction(row: dict[str, Any]) -> str | None:
    v = num(row, "broad_market_pre_5d_return")
    if v is None:
        return None
    if v < -0.01:
        return "falling"
    if v > 0.01:
        return "rising"
    return "flat"


def volatility_level(row: dict[str, Any]) -> str | None:
    v = num(row, "volatility_index_level")
    if v is None:
        return None
    if v < 15:
        return "low"
    if v >= 25:
        return "high"
    return "normal"


def volatility_trend(row: dict[str, Any]) -> str | None:
    v = num(row, "volatility_index_5d_change")
    if v is None:
        return None
    if v < -1:
        return "falling"
    if v > 1:
        return "rising"
    return "stable"


def yield_trend(row: dict[str, Any]) -> str | None:
    v = num(row, "us_10y_yield_5d_change")
    if v is None:
        return None
    if v < -0.05:
        return "falling"
    if v > 0.05:
        return "rising"
    return "stable"


def oil_trend(row: dict[str, Any]) -> str | None:
    v = num(row, "oil_5d_return")
    if v is None:
        return None
    if v < -0.02:
        return "falling"
    if v > 0.02:
        return "rising"
    return "stable"


def dollar_trend(row: dict[str, Any]) -> str | None:
    v = num(row, "us_dollar_5d_return")
    if v is None:
        return None
    if v < -0.005:
        return "falling"
    if v > 0.005:
        return "rising"
    return "stable"


CONDITIONS: list[tuple[str, str, Callable[[dict[str, Any]], str | None]]] = [
    ("market_direction", "Broad market before event", market_direction),
    ("volatility_level", "Market volatility", volatility_level),
    ("volatility_trend", "Volatility before event", volatility_trend),
    ("yield_trend", "US 10-year yield before event", yield_trend),
    ("oil_trend", "Oil before event", oil_trend),
    ("dollar_trend", "US dollar before event", dollar_trend),
]


def stats(rows: list[dict[str, Any]]) -> dict[str, float | int | None]:
    vals = [float(r["asset_return"]) for r in rows if r.get("asset_return") is not None]
    abn = [float(r["abnormal_return"]) for r in rows if r.get("abnormal_return") is not None]
    if not vals:
        return {"n": 0, "avg": None, "hit": None, "worst": None, "best": None, "abn": None, "beat": None}
    return {
        "n": len(vals),
        "avg": mean(vals),
        "hit": sum(v > 0 for v in vals) / len(vals),
        "worst": min(vals),
        "best": max(vals),
        "abn": mean(abn) if abn else None,
        "beat": sum(v > 0 for v in abn) / len(abn) if abn else None,
    }


def main() -> int:
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Supabase credentials missing; skipping context analysis safely.")
        return 0

    candidates = fetch_all(
        "event_candidates",
        "id,event_date,policy_theme,direction_guess,relevance_score,title,classification_basis",
        "auto_collected=eq.true",
    )
    metadata = {str(c["id"]): c for c in candidates}
    impacts = fetch_all(
        "candidate_event_impacts",
        "candidate_id,event_date,symbol,asset_name,asset_group,horizon,asset_return,abnormal_return",
    )
    contexts = fetch_all(
        "candidate_market_context",
        "candidate_id,event_date,broad_market_pre_5d_return,volatility_index_level,volatility_index_5d_change,us_10y_yield_pct,us_10y_yield_5d_change,oil_price,oil_5d_return,us_dollar_index,us_dollar_5d_return,market_regime",
    )
    context_by_id = {str(c["candidate_id"]): c for c in contexts}

    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for impact in impacts:
        cid = str(impact.get("candidate_id") or "")
        meta = metadata.get(cid)
        context = context_by_id.get(cid)
        if not meta or not context:
            continue
        theme = str(meta.get("policy_theme") or "")
        direction = str(meta.get("direction_guess") or "unknown")
        symbol = str(impact.get("symbol") or "")
        horizon = str(impact.get("horizon") or "")
        title = str(meta.get("title") or "")
        if direction not in ACTIONABLE_DIRECTIONS or horizon not in SHORT_HORIZONS:
            continue
        if symbol not in THEME_SYMBOLS.get(theme, set()):
            continue
        if obvious_routine(title):
            continue
        row = dict(impact)
        row.update(context)
        grouped.setdefault((theme, direction, symbol, horizon), []).append(row)

    summaries: list[dict[str, Any]] = []
    for (theme, direction, symbol, horizon), raw_rows in grouped.items():
        rows = non_overlapping(raw_rows, horizon)
        base = stats(rows)
        if int(base["n"] or 0) < 8:
            continue
        for condition_name, condition_label, classifier in CONDITIONS:
            buckets: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                value = classifier(row)
                if value:
                    buckets.setdefault(value, []).append(row)
            for value, subset in buckets.items():
                s = stats(subset)
                # Small groups are visible only when they have at least four independent dates.
                if int(s["n"] or 0) < 4:
                    continue
                key_raw = f"context|{theme}|{direction}|{symbol}|{horizon}|{condition_name}|{value}"
                summaries.append({
                    "summary_key": hashlib.sha1(key_raw.encode("utf-8")).hexdigest()[:24],
                    "policy_theme": theme,
                    "direction_guess": direction,
                    "symbol": symbol,
                    "horizon": horizon,
                    "condition_name": condition_name,
                    "condition_value": value,
                    "condition_label": f"{condition_label}: {value}",
                    "event_count": s["n"],
                    "average_return": s["avg"],
                    "hit_rate": s["hit"],
                    "average_abnormal_return": s["abn"],
                    "beat_market_rate": s["beat"],
                    "worst_return": s["worst"],
                    "best_return": s["best"],
                    "base_event_count": base["n"],
                    "base_average_return": base["avg"],
                    "base_hit_rate": base["hit"],
                    "return_lift": (s["avg"] - base["avg"]) if s["avg"] is not None and base["avg"] is not None else None,
                    "hit_rate_lift": (s["hit"] - base["hit"]) if s["hit"] is not None and base["hit"] is not None else None,
                    "source_dataset": SOURCE_DATASET,
                    "status": "exploratory_context",
                })

    rest("DELETE", "context_condition_summaries", params=f"source_dataset=eq.{SOURCE_DATASET}", prefer="return=minimal")
    for batch in chunks(summaries):
        rest(
            "POST", "context_condition_summaries", params="on_conflict=summary_key", rows=batch,
            prefer="resolution=merge-duplicates,return=minimal",
        )
    print(f"Wrote {len(summaries)} simple market-context summaries. All remain exploratory.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
