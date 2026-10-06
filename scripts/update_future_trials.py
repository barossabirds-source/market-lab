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
DEFAULT_FREEZE_DATE = "2026-10-05"

RULES = [
    {
        "trial_key": "china-deescalation-semiconductors-5d-future",
        "theme": "china_trade",
        "direction": "deescalation",
        "symbol": "SOXX",
        "horizon": "5d",
        "label": "China trade de-escalation → SOXX",
        "source": "curated",
        "freeze_date": DEFAULT_FREEZE_DATE,
    },
    {
        "trial_key": "metals-escalation-materials-5d-future",
        "theme": "metals_tariffs",
        "direction": "escalation",
        "symbol": "XLB",
        "horizon": "5d",
        "label": "Broad metals tariff escalation → XLB",
        "source": "curated",
        "freeze_date": DEFAULT_FREEZE_DATE,
    },
    {
        "trial_key": "defense-support-defense-5d-future",
        "theme": "defense",
        "direction": "sector_support",
        "symbol": "ITA",
        "horizon": "5d",
        "label": "Defense support action → ITA",
        "source": "curated",
        "freeze_date": DEFAULT_FREEZE_DATE,
    },
    {
        "trial_key": "infrastructure-support-industrials-3d-future",
        "theme": "infrastructure_manufacturing",
        "direction": "sector_support",
        "symbol": "XLI",
        "horizon": "3d",
        "label": "Infrastructure/manufacturing support → XLI",
        "source": "official_candidates",
        "freeze_date": DEFAULT_FREEZE_DATE,
    },
    {
        "trial_key": "tariff-rising-volatility-materials-5d-future",
        "theme": "trade_tariffs",
        "direction": "escalation",
        "symbol": "XLB",
        "horizon": "5d",
        "label": "Adjusting-imports tariff action + rising volatility → XLB",
        "source": "official_conditioned",
        "freeze_date": "2026-10-06",
        "title_phrase": "adjusting imports of",
        "min_vix_5d_change": 1.0,
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


def freeze_date(rule: dict[str, Any]) -> str:
    return str(rule.get("freeze_date") or DEFAULT_FREEZE_DATE)


def curated_values(rule: dict[str, Any]) -> list[float]:
    events = rest(
        "GET",
        "events",
        params=(
            f"select=id,event_date,summary&policy_theme=eq.{rule['theme']}"
            f"&direction=eq.{rule['direction']}&event_date=gt.{freeze_date(rule)}"
            "&order=event_date.asc&limit=100"
        ),
    ) or []
    if not events:
        return []
    ids = ",".join(e["id"] for e in events)
    impacts = rest(
        "GET",
        "event_impacts",
        params=(
            f"select=event_id,event_date,asset_return&event_id=in.({ids})"
            f"&symbol=eq.{rule['symbol']}&horizon=eq.{rule['horizon']}&limit=100"
        ),
    ) or []
    return [float(row["asset_return"]) for row in impacts if row.get("asset_return") is not None]


def official_candidate_rows(rule: dict[str, Any]) -> list[dict[str, Any]]:
    return rest(
        "GET",
        "event_candidates",
        params=(
            f"select=id,event_date,title&policy_theme=eq.{rule['theme']}"
            f"&direction_guess=eq.{rule['direction']}&event_date=gt.{freeze_date(rule)}"
            "&order=event_date.asc&limit=300"
        ),
    ) or []


def values_for_candidate_ids(rule: dict[str, Any], candidates: list[dict[str, Any]]) -> list[float]:
    if not candidates:
        return []
    ids = ",".join(str(c["id"]) for c in candidates)
    impacts = rest(
        "GET",
        "candidate_event_impacts",
        params=(
            f"select=candidate_id,event_date,asset_return&candidate_id=in.({ids})"
            f"&symbol=eq.{rule['symbol']}&horizon=eq.{rule['horizon']}&limit=500"
        ),
    ) or []
    by_date: dict[str, list[float]] = {}
    for row in impacts:
        if row.get("asset_return") is None:
            continue
        d = str(row.get("event_date") or "")[:10]
        by_date.setdefault(d, []).append(float(row["asset_return"]))
    return [mean(values) for _, values in sorted(by_date.items()) if values]


def official_candidate_values(rule: dict[str, Any]) -> list[float]:
    # Multiple official documents can share the same signing date. Count the market outcome
    # once per date so one policy package cannot masquerade as several independent events.
    return values_for_candidate_ids(rule, official_candidate_rows(rule))


def official_conditioned_values(rule: dict[str, Any]) -> list[float]:
    """Future-only official events with an exact title rule and pre-event VIX condition."""
    candidates = official_candidate_rows(rule)
    phrase = str(rule.get("title_phrase") or "").lower()
    candidates = [c for c in candidates if phrase and phrase in str(c.get("title") or "").lower()]
    if not candidates:
        return []

    ids = ",".join(str(c["id"]) for c in candidates)
    contexts = rest(
        "GET",
        "candidate_market_context",
        params=(
            f"select=candidate_id,event_date,volatility_index_5d_change&candidate_id=in.({ids})&limit=500"
        ),
    ) or []
    minimum = float(rule.get("min_vix_5d_change") or 0.0)
    qualifying_ids = {
        str(row["candidate_id"])
        for row in contexts
        if row.get("volatility_index_5d_change") is not None
        and float(row["volatility_index_5d_change"]) > minimum
    }
    filtered = [c for c in candidates if str(c["id"]) in qualifying_ids]
    return values_for_candidate_ids(rule, filtered)


def update_rule(rule: dict[str, Any]) -> None:
    source = rule.get("source")
    if source == "official_candidates":
        values = official_candidate_values(rule)
    elif source == "official_conditioned":
        values = official_conditioned_values(rule)
    else:
        values = curated_values(rule)

    count = len(values)
    avg = mean(values) if values else None
    hit = sum(v > 0 for v in values) / count if count else None
    freeze = freeze_date(rule)

    if count == 0:
        if source == "official_conditioned":
            source_text = "new official actions meeting the frozen title and volatility condition"
        elif source == "official_candidates":
            source_text = "new official formal actions"
        else:
            source_text = "qualifying future events"
        summary = (
            f"Future-only validation is active after {freeze}. No {source_text} have yet completed "
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
