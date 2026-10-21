"""Extract completed forward-paper pair trades for evidence review.

Read-only transformation. No brokerage, API keys, or database writes.
Existing forward_paper EXIT pnl excludes entry fee; adjust it here.
"""
from __future__ import annotations

from datetime import date
from math import isfinite
from typing import Any

import pandas as pd


def completed_pair_trades(result: dict[str, Any], *, allocation: float, cost_bps: float) -> list[dict[str, Any]]:
    """Return closed trades, preserving dates and explicit cost assumptions.

    The engine records entry equity after the entry half-fee. Thus EXIT pnl
    includes exit half-fee but excludes entry half-fee. Subtract that missing
    entry fee here. Open positions are not included.
    """
    if not isfinite(allocation) or allocation <= 0:
        raise ValueError("Allocation must be positive")
    if not isfinite(cost_bps) or cost_bps < 0:
        raise ValueError("Cost must be non-negative")
    log = result.get("trade_log")
    if log is None or not isinstance(log, pd.DataFrame) or log.empty:
        return []
    half_fee = allocation * cost_bps / 20000
    entry = None
    output = []
    for _, row in log.iterrows():
        event = str(row.get("event", ""))
        if event == "ENTRY":
            if entry is not None:
                raise ValueError("Overlapping entry records")
            entry = row
        elif event == "EXIT":
            if entry is None:
                raise ValueError("Exit without entry")
            pnl = float(row["pnl"])
            if not isfinite(pnl):
                raise ValueError("Non-finite P&L")
            start = pd.Timestamp(entry["date"]).date()
            end = pd.Timestamp(row["date"]).date()
            if end < start:
                raise ValueError("Exit before entry")
            net_pnl = pnl - half_fee
            output.append({
                "pair": str(result.get("pair", "")),
                "entry_date": start.isoformat(),
                "exit_date": end.isoformat(),
                "side": str(entry.get("side", "")),
                "net_pnl": net_pnl,
                "net_return_on_allocation": net_pnl / allocation,
                "round_trip_cost_bps": cost_bps,
                "source": "engine.forward_paper trade_log",
                "point_in_time_verified": False,
                "genuine_out_of_sample_verified": False,
            })
            entry = None
    return output


def research_summary(result: dict[str, Any], *, allocation: float, cost_bps: float) -> dict[str, Any]:
    trades = completed_pair_trades(result, allocation=allocation, cost_bps=cost_bps)
    returns = [trade["net_return_on_allocation"] for trade in trades]
    return {
        "pair": str(result.get("pair", "")),
        "closed_trades": len(trades),
        "mean_net_return": sum(returns) / len(returns) if returns else None,
        "net_win_rate": sum(r > 0 for r in returns) / len(returns) if returns else None,
        "status": "insufficient_evidence",
        "reason": "Point-in-time verification, preregistration and 30 independent out-of-sample trades not established",
        "trades": trades,
    }
