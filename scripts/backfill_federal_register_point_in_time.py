"""Run the Federal Register backfill using the earliest date this source definitely makes public.

The base collector stores both signing_date and publication_date. For research integrity this
wrapper anchors market measurement to publication_date, because a signing date can precede
Federal Register publication by several days. Using the signing date without another
point-in-time source can create look-ahead bias.

This wrapper intentionally leaves signing_date in the candidate metadata for reference. It
only changes the date used to measure market reactions. If we later verify an earlier public
White House timestamp for an event, that can be added as a separate curated source.
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
        + " Market measurement anchored to Federal Register publication date to avoid using the document before this source confirms it was public."
    )
    return candidate


def main() -> int:
    base.classify = point_in_time_classify
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
