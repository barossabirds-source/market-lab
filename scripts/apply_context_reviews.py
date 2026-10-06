"""Apply version-controlled manual review decisions to Market Lab context leads.

The market-context analysis is deliberately automatic. These review labels are a separate
human-quality-control layer so that a statistically attractive subgroup is not shown as a
credible research lead until the underlying event set has been inspected.

This script never creates trades or changes the frozen trigger of an existing trial.
"""
from __future__ import annotations

import json
import os
from typing import Any

import requests

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")

REVIEWS: dict[str, dict[str, str]] = {
    # Broad supporting context for the narrower frozen tariff + rising-volatility XLB trial.
    "b06aa8b717c5f4071782d901": {
        "review_status": "promising_reviewed",
        "review_notes": (
            "Reviewed 6 Oct 2026. The broader tariff-escalation sample is stronger when volatility "
            "was rising before the event: 10 independent dates, about +1.93% average over five "
            "trading days, 80% positive, and 60% beating the broad market. This supports, but does "
            "not replace, the narrower frozen rule requiring an official 'Adjusting Imports of' "
            "action and a VIX rise greater than 1 point."
        ),
    },
    # Interesting, but the economic link is not clean enough to freeze.
    "c3ccc666e208070e3f27463d": {
        "review_status": "watch",
        "review_notes": (
            "Reviewed 6 Oct 2026. Tariff escalations with a rising US dollar show a strong historical "
            "SOXX result, but the qualifying events mix metals, autos and wider trade actions. Several "
            "large later-term technology gains drive the average. Keep as a watch item only; do not "
            "freeze a rule without a cleaner event definition."
        ),
    },
    # High-looking sanctions/geopolitics results below are too small and too heterogeneous.
    "5f5d871253e353406a7300f8": {
        "review_status": "rejected",
        "review_notes": (
            "Rejected after review on 6 Oct 2026. Only four independent high-volatility events and a "
            "broad sanctions/geopolitics label. The sample is too small and heterogeneous to justify "
            "a defence-fund rule."
        ),
    },
    "c04948f78091665d308776ab": {
        "review_status": "rejected",
        "review_notes": (
            "Rejected after review on 6 Oct 2026. Four-event high-volatility subgroup with mixed "
            "sanctions/geopolitical actions. The apparent energy return is not robust enough to turn "
            "into a frozen rule."
        ),
    },
    "a054ad9304011cf4156ad053": {
        "review_status": "rejected",
        "review_notes": (
            "Rejected after review on 6 Oct 2026. Only four independent events and a broad geopolitical "
            "classification. The three-day energy result is too fragile for prospective testing."
        ),
    },
    "27d4378a303512e9456d858c": {
        "review_status": "rejected",
        "review_notes": (
            "Rejected after review on 6 Oct 2026. Five events are insufficient and the sanctions-to-ITA "
            "economic link is inconsistent across the underlying documents."
        ),
    },
}


def headers() -> dict[str, str]:
    h = {"apikey": SUPABASE_KEY, "Content-Type": "application/json"}
    if SUPABASE_KEY.startswith("eyJ"):
        h["Authorization"] = f"Bearer {SUPABASE_KEY}"
    return h


def patch_review(summary_key: str, review: dict[str, str]) -> None:
    response = requests.patch(
        f"{SUPABASE_URL}/rest/v1/context_condition_summaries?summary_key=eq.{summary_key}",
        headers={**headers(), "Prefer": "return=minimal"},
        data=json.dumps(review),
        timeout=60,
    )
    if not response.ok:
        raise RuntimeError(f"Failed to review {summary_key}: {response.status_code} {response.text[:400]}")


def main() -> int:
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Supabase credentials missing; skipping manual context reviews safely.")
        return 0
    for key, review in REVIEWS.items():
        patch_review(key, review)
    print(f"Applied {len(REVIEWS)} version-controlled context review decisions.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
