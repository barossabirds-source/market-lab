"""Build a richer Trump-era historical candidate dataset from the Federal Register.

This script deliberately separates automatically collected historical candidates from the
curated event ledger. It fetches official Presidential Documents, applies transparent
keyword-based market classifications, measures later market moves, and stores exploratory
patterns. Nothing here is a trading instruction and nothing is promoted into the frozen
research trials automatically.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import date, datetime, timedelta, timezone
from statistics import mean, median
from typing import Any

import pandas as pd
import requests
import yfinance as yf

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
FR_URL = "https://www.federalregister.gov/api/v1/documents.json"
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

# Transparent deterministic rules. Title matches are weighted more heavily than abstracts.
THEME_RULES: dict[str, dict[str, Any]] = {
    "china_trade": {
        "keywords": ["china", "chinese", "technology transfer", "section 301"],
        "context": ["trade", "tariff", "import", "export", "intellectual property", "investment"],
        "symbols": ["SOXX", "SMH", "QQQ", "XLK", "EEM", "XLI"],
    },
    "trade_tariffs": {
        "keywords": ["tariff", "tariffs", "trade", "imports", "import", "exports", "export", "customs", "duties", "steel", "aluminum", "aluminium", "section 232", "section 301", "reciprocal"],
        "symbols": ["XLI", "XLB", "SOXX", "QQQ", "XLY", "IWM", "EEM"],
    },
    "energy": {
        "keywords": ["energy", "oil", "petroleum", "natural gas", "lng", "pipeline", "offshore", "drilling", "coal", "nuclear", "electricity", "electric grid", "mining"],
        "symbols": ["XLE", "XLI", "XLB", "XLU"],
    },
    "defense": {
        "keywords": ["defense", "defence", "military", "missile", "weapons", "aerospace", "armed forces", "shipbuilding", "defense industrial base", "national defense"],
        "symbols": ["ITA", "XLI"],
    },
    "financial_regulation": {
        "keywords": ["financial system", "financial regulation", "banking", "banks", "bank", "securities", "capital markets", "fiduciary", "private equity", "digital assets", "cryptocurrency", "crypto"],
        "symbols": ["XLF", "KRE", "QQQ"],
    },
    "technology_semiconductors": {
        "keywords": ["semiconductor", "semiconductors", "artificial intelligence", "technology", "telecommunications", "5g", "cyber", "cloud computing", "quantum", "microelectronics"],
        "symbols": ["SOXX", "SMH", "QQQ", "XLK"],
    },
    "healthcare_pharma": {
        "keywords": ["drug prices", "drug pricing", "medicines", "pharmaceutical", "health care", "healthcare", "medicare", "medicaid", "biotechnology", "vaccine", "medical countermeasures"],
        "symbols": ["XLV", "IBB", "XBI"],
    },
    "infrastructure_manufacturing": {
        "keywords": ["infrastructure", "construction", "permitting", "investment accelerator", "manufacturing", "domestic production", "critical minerals", "supply chain", "transportation"],
        "symbols": ["XLI", "XLB", "IWM"],
    },
    "sanctions_geopolitics": {
        "keywords": ["sanctions", "sanction", "iran", "russia", "venezuela", "north korea", "cuba", "foreign adversary", "export controls", "national emergency"],
        "symbols": ["EEM", "XLE", "ITA", "QQQ"],
    },
    "tax_fiscal": {
        "keywords": ["tax", "taxation", "budget", "fiscal", "treasury", "government spending", "procurement", "federal contracting"],
        "symbols": ["SPY", "XLF", "IWM", "XLI"],
    },
    "labor_immigration": {
        "keywords": ["immigration", "visa", "border", "workforce", "labor", "worker", "wage", "employment"],
        "symbols": ["IWM", "XLY", "XLI"],
    },
}

CEREMONIAL_WORDS = [
    "month", "day", "week", "anniversary", "heritage", "prayer", "memorial",
    "flag", "thanksgiving", "christmas", "columbus day", "independence day",
]

DIRECTION_RULES = {
    "deescalation": ["suspend", "pause", "exemption", "exempt", "terminate", "remove", "reduce", "relief", "agreement", "settlement"],
    "escalation": ["impose", "increase", "additional tariff", "restrict", "prohibit", "sanctions", "safeguard", "emergency", "adjusting imports"],
    "sector_support": ["promote", "support", "unleashing", "accelerating", "revitalizing", "domestic production", "investment", "expanding", "strengthening"],
    "deregulation": ["regulatory relief", "reducing regulation", "deregulation", "rescission", "revocation", "removing barriers"],
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


def chunks(items: list[dict[str, Any]], size: int = 200):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def fetch_period(start: str, end: str) -> list[dict[str, Any]]:
    fields = [
        "document_number", "title", "abstract", "publication_date", "signing_date",
        "html_url", "subtype", "executive_order_number", "proclamation_number",
    ]
    params: list[tuple[str, str | int]] = [
        ("conditions[president][]", "donald-trump"),
        ("conditions[type][]", "PRESDOCU"),
        ("conditions[publication_date][gte]", start),
        ("conditions[publication_date][lte]", end),
        ("per_page", 1000),
        ("order", "oldest"),
    ]
    params.extend(("fields[]", f) for f in fields)
    out: list[dict[str, Any]] = []
    url: str | None = FR_URL
    first = True
    while url:
        response = requests.get(url, params=params if first else None, timeout=90)
        response.raise_for_status()
        payload = response.json()
        out.extend(payload.get("results", []))
        url = payload.get("next_page_url")
        first = False
    return out


def theme_score(title: str, abstract: str, rule: dict[str, Any]) -> tuple[int, list[str]]:
    title_l, abstract_l = title.lower(), abstract.lower()
    hits: list[str] = []
    score = 0
    for kw in rule.get("keywords", []):
        if kw in title_l:
            score += 3
            hits.append(kw)
        elif kw in abstract_l:
            score += 1
            hits.append(kw)
    context = rule.get("context", [])
    if context:
        if not any(c in title_l or c in abstract_l for c in context):
            return 0, []
        score += 1
    return score, hits


def classify(doc: dict[str, Any]) -> dict[str, Any] | None:
    title = str(doc.get("title") or "").strip()
    abstract = str(doc.get("abstract") or "").strip()
    if not title:
        return None

    scored: list[tuple[int, str, list[str]]] = []
    for theme, rule in THEME_RULES.items():
        score, hits = theme_score(title, abstract, rule)
        if score:
            scored.append((score, theme, hits))
    if not scored:
        return None
    scored.sort(reverse=True)
    top_score, theme, hits = scored[0]

    # Ceremonial proclamations are common and usually irrelevant to market research.
    title_l = title.lower()
    if any(word in title_l for word in CEREMONIAL_WORDS) and top_score < 6:
        return None
    if top_score < 3:
        return None

    text = f"{title} {abstract}".lower()
    direction = "unknown"
    direction_hits: list[str] = []
    best_dir_score = 0
    for label, words in DIRECTION_RULES.items():
        d_hits = [w for w in words if w in text]
        if len(d_hits) > best_dir_score:
            best_dir_score = len(d_hits)
            direction = label
            direction_hits = d_hits

    # Pull symbols from the primary theme and any strong secondary theme.
    symbols = set(THEME_RULES[theme]["symbols"])
    for score, other_theme, _ in scored[1:]:
        if score >= max(3, math.ceil(top_score * 0.6)):
            symbols.update(THEME_RULES[other_theme]["symbols"])

    event_date = doc.get("signing_date") or doc.get("publication_date")
    if not event_date:
        return None
    doc_number = str(doc.get("document_number") or "")
    raw_key = f"federal-register|{doc_number}|{event_date}|{title}"
    candidate_key = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:24]
    basis = f"Theme {theme}: {', '.join(hits[:8]) or 'rule match'}. Direction guess {direction}: {', '.join(direction_hits[:5]) or 'no strong direction words'}."

    return {
        "candidate_key": candidate_key,
        "event_date": str(event_date)[:10],
        "signing_date": str(doc.get("signing_date"))[:10] if doc.get("signing_date") else None,
        "publication_date": str(doc.get("publication_date"))[:10] if doc.get("publication_date") else None,
        "document_number": doc_number or None,
        "title": title,
        "abstract": abstract or None,
        "source_url": doc.get("html_url"),
        "source_name": "Federal Register",
        "source_kind": "presidential_document",
        "document_subtype": doc.get("subtype"),
        "executive_order_number": str(doc.get("executive_order_number")) if doc.get("executive_order_number") else None,
        "proclamation_number": str(doc.get("proclamation_number")) if doc.get("proclamation_number") else None,
        "policy_theme": theme,
        "direction_guess": direction,
        "relevance_score": int(top_score),
        "affected_symbols": sorted(symbols),
        "classification_basis": basis,
        "review_status": "candidate",
        "auto_collected": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def download_prices(start: date) -> pd.DataFrame:
    raw = yf.download(
        list(CORE_UNIVERSE),
        start=start.isoformat(),
        end=(date.today() + timedelta(days=1)).isoformat(),
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="column",
    )
    if raw.empty:
        raise RuntimeError("No market data returned by yfinance")
    close = raw["Close"].copy()
    close.index = pd.to_datetime(close.index).tz_localize(None)
    return close.sort_index()


def period_return(close: pd.DataFrame, symbol: str, start_pos: int, end_pos: int) -> float | None:
    if symbol not in close.columns or start_pos < 0 or end_pos >= len(close) or end_pos <= start_pos:
        return None
    a, b = close[symbol].iloc[start_pos], close[symbol].iloc[end_pos]
    if pd.isna(a) or pd.isna(b) or float(a) == 0:
        return None
    return float(b / a - 1.0)


def build_impacts(candidates: list[dict[str, Any]], ids: dict[str, str], close: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for c in candidates:
        cid = ids.get(c["candidate_key"])
        if not cid:
            continue
        d = pd.Timestamp(c["event_date"])
        first = int(close.index.searchsorted(d, side="left"))
        if first >= len(close):
            continue
        base = max(0, first - 1)
        for symbol, (asset_name, asset_group) in CORE_UNIVERSE.items():
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
                    "candidate_id": cid,
                    "event_date": c["event_date"],
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
                    "data_quality": "daily_date_only",
                    "calculated_at": datetime.now(timezone.utc).isoformat(),
                })
    return rows


def build_discoveries(candidates: list[dict[str, Any]], ids: dict[str, str], impacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    id_to_candidate = {ids[c["candidate_key"]]: c for c in candidates if c["candidate_key"] in ids}
    df = pd.DataFrame(impacts)
    if df.empty:
        return []
    rows: list[dict[str, Any]] = []

    def add_group(theme: str, direction: str, symbol: str, horizon: str, group: pd.DataFrame) -> None:
        vals = [float(v) for v in group["asset_return"].dropna().tolist()]
        if len(vals) < 5:
            return
        abnormal = [float(v) for v in group["abnormal_return"].dropna().tolist()]
        dates = [str(v)[:10] for v in group["event_date"].tolist()]
        first_vals = [v for v, d in zip(vals, dates) if d <= "2021-01-20"]
        second_vals = [v for v, d in zip(vals, dates) if d >= "2025-01-20"]
        sample = group.iloc[0]
        raw_key = f"{theme}|{direction}|{symbol}|{horizon}"
        rows.append({
            "discovery_key": hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:24],
            "policy_theme": theme,
            "direction_guess": direction,
            "symbol": symbol,
            "asset_name": sample["asset_name"],
            "asset_group": sample["asset_group"],
            "horizon": horizon,
            "event_count": len(vals),
            "average_return": mean(vals),
            "median_return": median(vals),
            "hit_rate": sum(v > 0 for v in vals) / len(vals),
            "worst_return": min(vals),
            "best_return": max(vals),
            "average_abnormal_return": mean(abnormal) if abnormal else None,
            "beat_market_rate": sum(v > 0 for v in abnormal) / len(abnormal) if abnormal else None,
            "first_term_count": len(first_vals),
            "first_term_average": mean(first_vals) if first_vals else None,
            "second_term_count": len(second_vals),
            "second_term_average": mean(second_vals) if second_vals else None,
            "source_dataset": "auto_federal_register_candidates",
            "status": "exploratory_auto",
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        })

    # Add candidate metadata into the impact frame.
    df["policy_theme"] = df["candidate_id"].map(lambda cid: id_to_candidate.get(cid, {}).get("policy_theme"))
    df["direction_guess"] = df["candidate_id"].map(lambda cid: id_to_candidate.get(cid, {}).get("direction_guess", "unknown"))

    for (theme, direction, symbol, horizon), group in df.groupby(["policy_theme", "direction_guess", "symbol", "horizon"], dropna=True):
        add_group(str(theme), str(direction), str(symbol), str(horizon), group)
    # Also create theme-only summaries so uncertain direction labels do not hide broad patterns.
    for (theme, symbol, horizon), group in df.groupby(["policy_theme", "symbol", "horizon"], dropna=True):
        add_group(str(theme), "any", str(symbol), str(horizon), group)
    return rows


def main() -> int:
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Supabase credentials missing; skipping historical backfill safely.")
        return 0

    started = datetime.now(timezone.utc).isoformat()
    run = rest("POST", "backfill_runs", rows={"started_at": started, "status": "running"}, prefer="return=representation")
    run_id = run[0]["id"] if run else None
    try:
        periods = [("2017-01-20", "2021-01-20"), ("2025-01-20", date.today().isoformat())]
        docs: list[dict[str, Any]] = []
        for start, end in periods:
            docs.extend(fetch_period(start, end))
        dedup = {str(d.get("document_number") or f"{d.get('publication_date')}|{d.get('title')}"): d for d in docs}
        docs = list(dedup.values())

        candidates = [c for c in (classify(d) for d in docs) if c is not None]
        written: list[dict[str, Any]] = []
        for batch in chunks(candidates, 100):
            result = rest(
                "POST", "event_candidates", params="on_conflict=candidate_key", rows=batch,
                prefer="resolution=merge-duplicates,return=representation",
            ) or []
            written.extend(result)
        ids = {row["candidate_key"]: row["id"] for row in written}
        # If an API gateway returns only a subset, fetch IDs back explicitly.
        if len(ids) < len(candidates):
            stored = rest("GET", "event_candidates", params="select=id,candidate_key&auto_collected=eq.true&limit=2000") or []
            ids.update({row["candidate_key"]: row["id"] for row in stored})

        start_date = min(date.fromisoformat(c["event_date"]) for c in candidates) - timedelta(days=45)
        close = download_prices(start_date)
        impacts = build_impacts(candidates, ids, close)
        for batch in chunks(impacts, 250):
            rest(
                "POST", "candidate_event_impacts",
                params="on_conflict=candidate_id,symbol,horizon", rows=batch,
                prefer="resolution=merge-duplicates,return=minimal",
            )

        discoveries = build_discoveries(candidates, ids, impacts)
        for batch in chunks(discoveries, 200):
            rest(
                "POST", "historical_discoveries", params="on_conflict=discovery_key", rows=batch,
                prefer="resolution=merge-duplicates,return=minimal",
            )

        message = (
            f"Federal Register backfill complete: {len(docs)} Trump presidential documents fetched, "
            f"{len(candidates)} market-relevant candidates classified, {len(impacts)} reactions measured, "
            f"{len(discoveries)} exploratory pattern summaries. Candidates remain separate from the curated ledger."
        )
        if run_id:
            rest("PATCH", "backfill_runs", params=f"id=eq.{run_id}", rows={
                "finished_at": datetime.now(timezone.utc).isoformat(), "status": "completed",
                "documents_fetched": len(docs), "candidates_written": len(candidates),
                "impacts_written": len(impacts), "discoveries_written": len(discoveries),
                "message": message,
            }, prefer="return=minimal")
        print(message)
        return 0
    except Exception as exc:
        if run_id:
            rest("PATCH", "backfill_runs", params=f"id=eq.{run_id}", rows={
                "finished_at": datetime.now(timezone.utc).isoformat(), "status": "failed", "message": str(exc)[:1000],
            }, prefer="return=minimal")
        raise


if __name__ == "__main__":
    raise SystemExit(main())
