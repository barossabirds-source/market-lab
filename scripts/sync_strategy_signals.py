"""Persist Market Lab simulated strategy signals and trade events in Supabase.

This turns the forward strategy checks into a durable daily history so later
checks can reliably tell whether a signal, position or completed trade changed.
No brokerage orders are created.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests

from engine import load_prices, forward_dashboard, forward_long_only_dashboard

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")


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


def clean_pair(pair: str) -> str:
    return " / ".join(x.strip() for x in str(pair).split("/"))


def as_number(value):
    if value is None:
        return None
    try:
        n = float(value)
        return None if pd.isna(n) else n
    except Exception:
        return None


def event_key(model_type: str, pair_key: str, event_date: str, event_type: str, side: str) -> str:
    raw = "|".join([model_type, pair_key, event_date, event_type, side])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def snapshot_rows(model_type: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for x in results:
        observed = pd.Timestamp(x["latest_date"]).date().isoformat()
        rows.append({
            "model_type": model_type,
            "pair_key": clean_pair(x["pair"]),
            "observed_on": observed,
            "latest_z": as_number(x.get("latest_z")),
            "signal": str(x.get("signal", "")),
            "position": str(x.get("position", "")),
            "forward_return": as_number(x.get("return")),
            "completed_trades": int(x.get("trades", 0) or 0),
            "win_rate": as_number(x.get("win_rate")),
            "max_drawdown": as_number(x.get("max_dd")),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        })
    return rows


def event_rows(model_type: str, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for x in results:
        pair_key = clean_pair(x["pair"])
        log = x.get("trade_log")
        if log is None or not len(log):
            continue
        for _, r in log.iterrows():
            dt = pd.Timestamp(r.get("date")).date().isoformat()
            et = str(r.get("event", ""))
            side = str(r.get("side", ""))
            rows.append({
                "event_key": event_key(model_type, pair_key, dt, et, side),
                "model_type": model_type,
                "pair_key": pair_key,
                "event_date": dt,
                "event_type": et,
                "side": side or None,
                "z_score": as_number(r.get("z")),
                "equity": as_number(r.get("equity")),
                "pnl": as_number(r.get("pnl")),
                "days_held": int(r.get("days")) if pd.notna(r.get("days")) else None,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            })
    return rows


def main() -> int:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError("Supabase server-side credentials are required")

    prices = load_prices()
    if prices.empty:
        raise RuntimeError("Market price download returned no usable rows; no snapshots saved")
    pair_results = forward_dashboard(prices)
    buy_only_results = forward_long_only_dashboard(prices)

    snapshots = snapshot_rows("two_fund", pair_results) + snapshot_rows("buy_only", buy_only_results)
    events = event_rows("two_fund", pair_results) + event_rows("buy_only", buy_only_results)

    if not snapshots:
        raise RuntimeError("No strategy snapshots were generated; check price coverage and configured pairs")

    if snapshots:
        rest(
            "POST",
            "strategy_snapshots",
            params="on_conflict=model_type,pair_key,observed_on",
            rows=snapshots,
            prefer="resolution=merge-duplicates,return=minimal",
        )
    if events:
        rest(
            "POST",
            "strategy_events",
            params="on_conflict=event_key",
            rows=events,
            prefer="resolution=merge-duplicates,return=minimal",
        )

    print(f"Stored {len(snapshots)} strategy snapshots and {len(events)} strategy events.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
