import copy
import json
import unittest
from datetime import datetime
from scripts.event_evidence import RULE, outcome, summarise, freeze_prediction, register, stats, complete_coverage


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.rule = dict(copy.deepcopy(RULE), registered_at='2026-10-28T00:00:00Z')
        self.now = datetime.fromisoformat('2026-10-29T08:00:00+00:00')
        self.row = {'session_date':'2026-10-29', 'symbol':'A200.AX', 'source':'yahoo_research_v1',
                    'captured_at':self.now.isoformat(), 'observations':{
                        'us_return_pct':1.0, 'us_close_at':'2026-10-28T20:00:00+00:00',
                        'entry_at':'2026-10-29T10:05:00+11:00', 'exit_at':'2026-10-29T15:55:00+11:00',
                        'entry_bar_open':100, 'exit_bar_open':101, 'previous_close':98,
                        'opening_bar_proxy':100}}
        self.pred = {'captured_at':'2026-10-29T09:35:00+11:00',
                     'prediction':{'signal':True,'us_return_pct':1.0,'us_close_at':'2026-10-28T20:00:00+00:00'}}

    def result(self, prediction=True):
        return outcome(self.row, self.pred if prediction else None, self.rule, self.now)

    def test_costs_once_and_open_gap_not_profit(self):
        self.row['observations']['exit_bar_open'] = 99
        r = self.result()['result']
        self.assertGreater(r['opening_gap_proxy'],0)
        self.assertAlmostEqual(r['net_aud'],-32)
        self.assertEqual(r['cost_aud'],12)

    def test_proxy_never_validates_and_historical_never_becomes_frozen(self):
        r = self.result()
        s = summarise([r], self.rule)
        self.assertEqual(s['forward_proxy']['signal']['n'],1)
        self.assertEqual(s['validated']['signal']['n'],0)
        self.assertFalse(self.result(False)['result']['pre_entry_frozen'])
        self.pred['captured_at'] = self.now.isoformat()
        self.assertFalse(self.result()['result']['pre_entry_frozen'])

    def test_missing_prices_count_as_gaps_not_losses_or_zero(self):
        self.row['observations']['entry_bar_open'] = None
        s = summarise([self.result()], self.rule)['all_proxy']
        self.assertEqual(s['observed'],1)
        self.assertEqual(s['missing_or_excluded'],1)
        self.assertIsNone(s['signal']['mean'])

    def test_future_close_and_unfinished_session_excluded(self):
        self.row['observations']['us_close_at'] = self.now.isoformat()
        self.assertIsNone(self.result()['result']['net_aud'])
        self.row['observations']['us_close_at'] = self.pred['prediction']['us_close_at']
        r = outcome(self.row, self.pred, self.rule, datetime.fromisoformat('2026-10-29T11:00:00+11:00'))
        self.assertIsNone(r['result']['net_aud'])

    def test_wrong_window_stale_us_and_source_revisions_excluded(self):
        self.row['observations']['entry_at'] = '2026-10-29T10:06:00+11:00'
        self.assertIn('wrong_session_or_window',self.result()['result']['exclusions'])
        self.row['observations']['us_return_pct'] = 2
        self.assertIn('morning_evening_source_mismatch',self.result()['result']['exclusions'])

    def test_registration_must_precede_prediction(self):
        self.rule['registered_at'] = self.now.isoformat()
        self.assertFalse(self.result()['result']['pre_entry_frozen'])

    def test_baseline_uses_same_costs_and_zero_us_is_comparison(self):
        up = self.result(False)
        self.row['session_date'] = '2026-10-28'
        self.row['observations']['entry_at'] = '2026-10-28T10:05:00+11:00'
        self.row['observations']['exit_at'] = '2026-10-28T15:55:00+11:00'
        self.row['observations']['us_close_at'] = '2026-10-27T20:00:00+00:00'
        self.row['observations']['us_return_pct'] = 0
        other = self.result(False)
        s = summarise([up,other],self.rule)['all_proxy']
        self.assertEqual(s['signal']['n'],1)
        self.assertEqual(s['comparison']['n'],1)
        self.assertEqual(s['mean_difference_aud'],0)

    def test_one_observation_has_wide_uncertainty_and_no_mean_interval(self):
        s = stats([{'net_aud':10}])
        self.assertLess(s['win_interval'][0],0.3)
        self.assertIsNone(s['mean_interval'])

    def test_drawdown_pause_is_based_on_chronological_fixed_size_results(self):
        rows=[]
        for i in range(3):
            r=copy.deepcopy(self.result());r['session_date']=f'2026-10-{27+i}'
            r['result']['net_aud']=-100;rows.append(r)
        self.assertEqual(summarise(rows[::-1],self.rule)['status'],'paused_drawdown')

    def test_empty_summary_fits_existing_status_payload(self):
        s=summarise([],self.rule)
        self.assertEqual(s['status'],'collecting')
        self.assertLess(len(json.dumps(s).encode()),4096)
        self.assertLess(len(json.dumps(summarise([self.result()],self.rule)).encode()),4096)

    def test_late_morning_job_never_backdates_prediction(self):
        class FakeDB:
            def request(self,*args,**kwargs): raise AssertionError('must not write')
        self.assertFalse(freeze_prediction(FakeDB(),self.rule,{'us_return_pct':1},self.now))

    def test_frozen_rule_change_requires_new_version(self):
        class FakeDB:
            def request(self,method,*args,**kwargs):
                if method=='POST': return None
                return [dict(RULE,config={})]
        self.assertRaisesRegex(RuntimeError,'new version',register,FakeDB())

    def test_wholly_missing_session_after_registration_is_visible(self):
        import pandas as pd
        class Calendar:
            def sessions_in_range(self,*args): return pd.DatetimeIndex(['2026-10-28','2026-10-29'])
        rows=complete_coverage([self.row],{},self.rule,self.now,Calendar())
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]['source'],'no_evening_observation')
        self.assertIn('missing_exact_price_bar',outcome(rows[0],None,self.rule,self.now)['result']['exclusions'])


if __name__ == '__main__':
    unittest.main()
