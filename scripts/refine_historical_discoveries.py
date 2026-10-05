"""Refine automatically collected historical discoveries.

The raw backfill can contain multiple documents signed on the same day and overlapping
holding windows. Counting each as an independent event can greatly exaggerate apparent
sample size. This pass collapses same-day theme clusters and then keeps non-overlapping
observations for each holding period before calculating exploratory summaries.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date, timedelta
from statistics import mean, median
from typing import Any

import requests

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SOURCE_DATASET = "federal_register_clustered_nonoverlap"

# Conservative calendar gaps used to avoid counting substantially overlapping return windows
# as separate observations. They are deliberately longer than the nominal trading-day hold.
MIN_GAP_DAYS = {"1d": 2, "3d": 5, "5d": 8, "20d": 30}


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
            break
        offset += step
    return out


def chunks(items: list[dict[str, Any]], size: int = 200):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def non_overlapping(rows: list[dict[str, Any]], horizon: str) -> list[dict[str, Any]]:
    """Collapse same-day duplicates and then keep spaced observations only."""
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        d = str(row.get("event_date") or "")[:10]
        if d:
            by_date.setdefault(d, []).append(row)

    collapsed: list[dict[str, Any]] = []
    for d, same_day in sorted(by_date.items()):
        # Market returns are identical for same date/symbol/horizon. If a provider ever
        # differs slightly, averaging prevents arbitrary document ordering from deciding.
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


def make_summary(theme: str, direction: str, symbol: str, horizon: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    sample_rows = non_overlapping(rows, horizon)
    vals = [float(r["asset_return"]) for r in sample_rows if r.get("asset_return") is not None]
    if len(vals) < 5:
        return None
    abn = [float(r["abnormal_return"]) for r in sample_rows if r.get("abnormal_return") is not None]
    first = [float(r["asset_return"]) for r in sample_rows if r.get("asset_return") is not None and str(r["event_date"])[:10] <= "2021-01-20"]
    second = [float(r["asset_return"]) for r in sample_rows if r.get("asset_return") is not None and str(r["event_date"])[:10] >= "2025-01-20"]
    sample = sample_rows[0]
    raw_key = f"refined|{theme}|{direction}|{symbol}|{horizon}"
    return {
        "discovery_key": hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:24],
        "policy_theme": theme,
        "direction_guess": direction,
        "symbol": symbol,
        "asset_name": sample.get("asset_name") or symbol,
        "asset_group": sample.get("asset_group") or "",
        "horizon": horizon,
        "event_count": len(vals),
        "average_return": mean(vals),
        "median_return": median(vals),
        "hit_rate": sum(v > 0 for v in vals) / len(vals),
        "worst_return": min(vals),
        "best_return": max(vals),
        "average_abnormal_return": mean(abn) if abn else None,
        "beat_market_rate": sum(v > 0 for v in abn) / len(abn) if abn else None,
        "first_term_count": len(first),
        "first_term_average": mean(first) if first else None,
        "second_term_count": len(second),
        "second_term_average": mean(second) if second else None,
        "source_dataset": SOURCE_DATASET,
        "status": "exploratory_refined",
    }


def main() -> int:
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Supabase credentials missing; skipping refinement safely.")
        return 0

    candidates = fetch_all(
        "event_candidates",
        "id,event_date,policy_theme,direction_guess,relevance_score,title,classification_basis",
        "auto_collected=eq.true",
    )
    cmeta = {str(c["id"]): c for c in candidates}
    impacts = fetch_all(
        "candidate_event_impacts",
        "candidate_id,event_date,symbol,asset_name,asset_group,horizon,asset_return,abnormal_return",
    )

    # Attach classifications and ignore obvious substring artefacts from the first-pass rules.
    enriched: list[dict[str, Any]] = []
    for row in impacts:
        meta = cmeta.get(str(row.get("candidate_id")))
        if not meta:
            continue
        title = str(meta.get("title") or "").lower()
        basis = str(meta.get("classification_basis") or "").lower()
        if "theme energy: mining" in basis and " mining " not in f" {title} ":
            continue
        item = dict(row)
        item["policy_theme"] = meta.get("policy_theme")
        item["direction_guess"] = meta.get("direction_guess") or "unknown"
        enriched.append(item)

    summaries: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    theme_grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in enriched:
        theme = str(row.get("policy_theme") or "unknown")
        direction = str(row.get("direction_guess") or "unknown")
        symbol = str(row.get("symbol") or "")
        horizon = str(row.get("horizon") or "")
        grouped.setdefault((theme, direction, symbol, horizon), []).append(row)
        theme_grouped.setdefault((theme, symbol, horizon), []).append(row)

    for (theme, direction, symbol, horizon), rows in grouped.items():
        s = make_summary(theme, direction, symbol, horizon, rows)
        if s:
            summaries.append(s)
    for (theme, symbol, horizon), rows in theme_grouped.items():
        s = make_summary(theme, "any", symbol, horizon, rows)
        if s:
            summaries.append(s)

    for batch in chunks(summaries):
        rest(
            "POST", "historical_discoveries", params="on_conflict=discovery_key", rows=batch,
            prefer="resolution=merge-duplicates,return=minimal",
        )
    print(f"Refined {len(summaries)} historical summaries using same-day clustering and non-overlapping windows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
