import unittest
from datetime import date
from research.agent_gate import ResearchProposal, evaluate


def proposal(**changes):
    args = dict(
        name="Overnight ASX", hypothesis="US up predicts positive post-entry ASX return",
        rule_frozen_on=date(2026, 10, 16),
        first_evaluation_session=date(2026, 10, 19),
        observations=40, out_of_sample_observations=40,
        gross_returns=[0.003] * 40, round_trip_cost_bps=10,
        data_provenance="Recorded ETF bars", includes_no_signal_sessions=True,
        point_in_time_verified=True,
    )
    args.update(changes)
    return ResearchProposal(**args)


class GateTests(unittest.TestCase):
    def test_candidate_is_not_trade_approval(self):
        self.assertEqual(evaluate(proposal()).status, "research_candidate")

    def test_unverified_timing_rejected(self):
        self.assertEqual(evaluate(proposal(point_in_time_verified=False)).status, "insufficient_evidence")

    def test_costs_can_erase_edge(self):
        self.assertEqual(evaluate(proposal(round_trip_cost_bps=40)).status, "not_promising")

    def test_no_signal_comparator_required(self):
        self.assertEqual(evaluate(proposal(includes_no_signal_sessions=False)).status, "insufficient_evidence")

    def test_pre_registration_required(self):
        self.assertEqual(evaluate(proposal(first_evaluation_session=date(2026, 10, 16))).status, "insufficient_evidence")

    def test_minimum_oos_required(self):
        self.assertEqual(evaluate(proposal(out_of_sample_observations=12)).status, "insufficient_evidence")


if __name__ == "__main__":
    unittest.main()
