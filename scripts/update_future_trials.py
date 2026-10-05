"""Update Market Lab rules that were discovered historically but must prove themselves on unseen future events.

The rules in this file are frozen. Historical discovery results are not mixed into future validation.
This script never places trades.
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

RULES = [
    {
        "trial_key": "china-deescalation-semiconductors-5d-future",
        "theme": "china_trade",
        "direction": "deescalation",
        "symbol": "SOXX",
        "horizon": "5d",
        "label": "China trade de-escalation → SOXX",
    },
    {
        "trial_key": "metals-escalation-materials-5d-future",
        "theme": "metals_tariffs",
        "direction": "escalation",
        "symbol": "XLB",
        "horizon": "5d",
        "label": "Metals tariff escalation → XLB",
    },
    {
        "trial_key": "defense-support-defense-5d-future",
        "theme": "defense",
        "direction": "sector_support",
        "symbol": "ITA",
        "horizon": "5d",
        "label": "Defense support action → ITA",
    },
]


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


def update_rule(rule: dict[str, str]) -> None:
    events = rest(
        "GET",
        "events",
        params=(
            f"select=id,event_date,summary&policy_theme=eq.{rule['theme']}"
            f"&direction=eq.{rule['direction']}&event_date=gt.{FREEZE_DATE}"
            "&order=event_date.asc&limit=100"
        ),
    ) or []

    values: list[float] = []
    if events:
        ids = ",".join(e["id"] for e in events)
        impacts = rest(
            "GET",
            "event_impacts",
            params=(
                f"select=event_id,event_date,asset_return&event_id=in.({ids})"
                f"&symbol=eq.{rule['symbol']}&horizon=eq.{rule['horizon']}&limit=100"
            ),
        ) or []
        for row in impacts:
            if row.get("asset_return") is not None:
                values.append(float(row["asset_return"]))

    count = len(values)
    avg = mean(values) if values else None
    hit = sum(v > 0 for v in values) / count if count else None

    if count == 0:
        summary = (
            f"Future-only validation is active from 5 Oct 2026. No qualifying future event has yet completed "
            f"a {rule['horizon']} {rule['symbol']} measurement. Historical discovery remains exploratory."
        )
    else:
        summary = (
            f"Future-only validation has {count} measurable event{'s' if count != 1 else ''}. "
            f"{rule['symbol']} averaged {avg*100:+.2f}% over {rule['horizon'].replace('d', ' trading days')} "
            f"and was positive in {hit*100:.0f}% of these unseen events. Keep the rule frozen."
        )

    if count < 5:
        status = "registered"
    elif avg is not None and hit is not None and avg > 0 and hit >= 0.60:
        status = "some_support"
    else:
        status = "mixed_not_supported"

    rest(
        "PATCH",
        "research_trials",
        params=f"trial_key=eq.{rule['trial_key']}",
        rows={
            "event_count": count,
            "average_effect": avg,
            "hit_rate": hit,
            "result_summary": summary,
            "status": status,
        },
        prefer="return=minimal",
    )
    print(f"Updated {rule['trial_key']}: {count} future events")


def main() -> int:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return 0
    for rule in RULES:
        update_rule(rule)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
