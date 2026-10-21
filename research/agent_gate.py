"""Deterministic validation gate for AI-proposed trading research.

No LLM dependency, brokerage integration, or paid feed is required.
Run: python -m unittest discover -s tests -p 'test_research_gate.py'
"""
from dataclasses import dataclass
from datetime import date
from math import isfinite
from typing import Sequence


@dataclass(frozen=True)
class ResearchProposal:
    name: str
    hypothesis: str
    rule_frozen_on: date
    first_evaluation_session: date
    observations: int
    out_of_sample_observations: int
    gross_returns: Sequence[float]
    round_trip_cost_bps: float
    data_provenance: str
    includes_no_signal_sessions: bool
    point_in_time_verified: bool


@dataclass(frozen=True)
class GateResult:
    status: str
    reasons: tuple[str, ...]
    mean_net_return: float | None
    win_rate: float | None


def evaluate(proposal: ResearchProposal, min_oos: int = 30) -> GateResult:
    """Reject weak evidence; passing means research-worthy, never trade-ready."""
    reasons = []
    if not proposal.name.strip() or not proposal.hypothesis.strip():
        reasons.append("Missing registered name or hypothesis")
    if proposal.first_evaluation_session <= proposal.rule_frozen_on:
        reasons.append("Evaluation sessions must follow rule freeze date")
    if proposal.observations < 1 or len(proposal.gross_returns) != proposal.observations:
        reasons.append("Observation count mismatch")
    if proposal.out_of_sample_observations < min_oos:
        reasons.append("Insufficient out-of-sample observations")
    if proposal.out_of_sample_observations > proposal.observations:
        reasons.append("Out-of-sample count exceeds total")
    if not proposal.data_provenance.strip():
        reasons.append("Missing data provenance")
    if not proposal.includes_no_signal_sessions:
        reasons.append("No-signal comparator sessions missing")
    if not proposal.point_in_time_verified:
        reasons.append("Point-in-time integrity not verified")
    if not isfinite(proposal.round_trip_cost_bps) or proposal.round_trip_cost_bps < 0:
        reasons.append("Invalid trading costs")
    if any(not isfinite(r) for r in proposal.gross_returns):
        reasons.append("Non-finite return")
    if reasons:
        return GateResult("insufficient_evidence", tuple(reasons), None, None)
    net = [r - proposal.round_trip_cost_bps / 10000 for r in proposal.gross_returns]
    avg = sum(net) / len(net)
    win = sum(r > 0 for r in net) / len(net)
    if avg <= 0:
        return GateResult("not_promising", ("Non-positive average net return",), avg, win)
    return GateResult("research_candidate", ("Requires independent forward validation",), avg, win)
