"""Run the Federal Register backfill without using information before this source was tradable.

The base collector stores both signing_date and publication_date. For research integrity this
wrapper anchors automated market measurement to publication_date, because a signing date can
precede Federal Register publication by several days.

It also uses the close of the first trading session on or after publication as the hypothetical
entry point. That deliberately gives up any same-day move. Without a verified intraday public
release time, using the previous close would assume the investor could enter before the source
was known and would create look-ahead bias.

Signing_date remains in candidate metadata for reference. If a separate White House source
later proves an earlier public timestamp, that belongs in the curated point-in-time ledger.
"""
from __future__ import annotations

import hashlib

import backfill_federal_register as base

_original_classify = base.classify


def point_in_time_classify(doc):
    candidate = _original_classify(doc)
    if candidate is None:
        return None

    available_date = doc.get("publication_date") or doc.get("signing_date")
    if not available_date:
        return None

    available_date = str(available_date)[:10]
    candidate["event_date"] = available_date

    # Stable key does not depend on which date is used for measurement. This lets later
    # point-in-time improvements update the same official document instead of duplicating it.
    doc_number = str(doc.get("document_number") or "")
    title = str(doc.get("title") or "").strip()
    raw_key = f"federal-register|{doc_number}|{title}"
    candidate["candidate_key"] = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:24]
    candidate["classification_basis"] = (
        str(candidate.get("classification_basis") or "")
        + " Market measurement anchored to Federal Register publication date. Automated strategy returns enter at the first market close on or after publication so the source is already public."
    )
    return candidate


def point_in_time_build_impacts(candidates, ids, close):
    """Measure only returns available after a conservative end-of-session entry."""
    rows = []
    for candidate in candidates:
        cid = ids.get(candidate["candidate_key"])
        if not cid:
            continue
        event_date = base.pd.Timestamp(candidate["event_date"])
        entry_pos = int(close.index.searchsorted(event_date, side="left"))
        if entry_pos >= len(close):
            continue

        # Entry is the close of the first trading session on/after publication. A one-day
        # result is therefore entry close to the next trading-day close, not previous close
        # to publication-day close.
        for symbol, (asset_name, asset_group) in base.CORE_UNIVERSE.items():
            for horizon in base.HORIZONS:
                exit_pos = entry_pos + horizon
                asset = base.period_return(close, symbol, entry_pos, exit_pos)
                benchmark = base.period_return(close, base.BENCHMARK, entry_pos, exit_pos)
                pre_asset = base.period_return(close, symbol, entry_pos - horizon, entry_pos)
                pre_benchmark = base.period_return(close, base.BENCHMARK, entry_pos - horizon, entry_pos)
                abnormal = asset - benchmark if asset is not None and benchmark is not None else None
                pre_abnormal = (
                    pre_asset - pre_benchmark
                    if pre_asset is not None and pre_benchmark is not None
                    else None
                )
                reaction = (
                    abnormal - pre_abnormal
                    if abnormal is not None and pre_abnormal is not None
                    else None
                )
                rows.append({
                    "candidate_id": cid,
                    "event_date": candidate["event_date"],
                    "symbol": symbol,
                    "asset_name": asset_name,
                    "asset_group": asset_group,
                    "benchmark_symbol": base.BENCHMARK,
                    "horizon": f"{horizon}d",
                    "asset_return": asset,
                    "benchmark_return": benchmark,
                    "abnormal_return": abnormal,
                    "pre_event_abnormal_return": pre_abnormal,
                    "reaction_vs_pre": reaction,
                    "data_quality": "federal_register_publication_date_close_entry",
                    "calculated_at": base.datetime.now(base.timezone.utc).isoformat(),
                })
    return rows


def main() -> int:
    base.classify = point_in_time_classify
    base.build_impacts = point_in_time_build_impacts
    # Raw automated summaries are fully regenerated. The refined discovery script separately
    # clears and rebuilds its own generated slice.
    if base.SUPABASE_URL and base.SUPABASE_KEY:
        base.rest(
            "DELETE",
            "historical_discoveries",
            params="source_dataset=eq.auto_federal_register_candidates",
            prefer="return=minimal",
        )
    return base.main()


if __name__ == "__main__":
    raise SystemExit(main())
