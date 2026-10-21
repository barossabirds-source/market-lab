import unittest
import pandas as pd
from research.pair_trade_evidence import completed_pair_trades, research_summary


class PairEvidenceTests(unittest.TestCase):
    def test_closed_trade_accounts_for_both_fees(self):
        # allocation 10,000, round-trip cost 8bps => two 4-dollar fees.
        log = pd.DataFrame([
            {"date": "2026-10-01", "event": "ENTRY", "side": "LONG SPREAD"},
            {"date": "2026-10-06", "event": "EXIT", "pnl": 96.0},
        ])
        rows = completed_pair_trades({"pair": "IWF / SPY", "trade_log": log}, allocation=10000, cost_bps=8)
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["net_pnl"], 92)
        self.assertAlmostEqual(rows[0]["net_return_on_allocation"], 0.0092)
        self.assertFalse(rows[0]["point_in_time_verified"])

    def test_open_trade_not_reported_as_completed(self):
        log = pd.DataFrame([{"date": "2026-10-01", "event": "ENTRY", "side": "SHORT SPREAD"}])
        self.assertEqual(completed_pair_trades({"trade_log": log}, allocation=10000, cost_bps=8), [])

    def test_missing_trades_are_not_profitable_evidence(self):
        result = research_summary({"pair": "IWF / SPY", "trade_log": pd.DataFrame()}, allocation=10000, cost_bps=8)
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertIsNone(result["mean_net_return"])

    def test_exit_without_entry_fails(self):
        with self.assertRaises(ValueError):
            completed_pair_trades({"trade_log": pd.DataFrame([{"event": "EXIT", "date": "2026-10-01", "pnl": 20}])}, allocation=10000, cost_bps=8)


if __name__ == "__main__":
    unittest.main()
