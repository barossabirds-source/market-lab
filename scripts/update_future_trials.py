"""Update Market Lab trials that were discovered historically but must be tested only on future unseen events.

This keeps exploratory discovery separate from validation. It never places trades.
"""
from __future__ import annotations

import json
import os
from statistics import mean
from typing import Any

import requests

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
FREEZE_DATE = "2026-10-05"
TRIAL_KEY = "china-deescalation-semiconductors-5d-future"


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
    response = requests.request(method, url, headers=h, data=json.dumps(rows) if rows is not None else None, timeout=60)
    if not response.ok:
        raise RuntimeError(f"Supabase {method} {table} failed: {response.status_code} {response.text[:500]}")
    return response.json() if response.text else None


def main() -> int:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return 0

    events = rest(
        "GET",
        "events",
        params=(
            "select=id,event_date,summary&policy_theme=eq.china_trade&direction=eq.deescalation"
            f"&event_date=gt.{FREEZE_DATE}&order=event_date.asc&limit=100"
        ),
    ) or []

    values: list[float] = []
    dates: list[str] = []
    if events:
        ids = ",".join(e["id"] for e in events)
        impacts = rest(
            "GET",
            "event_impacts",
            params=f"select=event_id,event_date,asset_return&event_id=in.({ids})&symbol=eq.SOXX&horizon=eq.5d&limit=100",
        ) or []
        for row in impacts:
            if row.get("asset_return") is None:
                continue
            values.append(float(row["asset_return"]))
            dates.append(str(row.get("event_date") or ""))

    count = len(values)
    avg = mean(values) if values else None
    hit = sum(v > 0 for v in values) / count if count else None

    if count == 0:
        summary = (
            "Future-only validation is active from 5 Oct 2026. No qualifying China-trade de-escalation event "
            "has yet completed a 5-trading-day SOXX measurement. The historical discovery sample remains exploratory."
        )
    else:
        summary = (
            f"Future-only validation has {count} measurable event{'s' if count != 1 else ''}. "
            f"SOXX averaged {avg*100:+.2f}% over 5 trading days and was positive in {hit*100:.0f}% of these future events. "
            "Keep the rule frozen; do not combine this validation result with the historical discovery sample when judging unseen-data performance."
        )

    rest(
        "PATCH",
        "research_trials",
        params=f"trial_key=eq.{TRIAL_KEY}",
        rows={
            "event_count": count,
            "average_effect": avg,
            "hit_rate": hit,
            "result_summary": summary,
            "status": "registered" if count < 5 else "testing",
        },
        prefer="return=minimal",
    )
    print(f"Updated {TRIAL_KEY}: {count} future events")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
