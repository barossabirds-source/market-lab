import unittest
from datetime import datetime, timezone
import pandas as pd
import exchange_calendars as xcals
from scripts.collect_asx_feed import minute_open, us_observation, build_rows, SYDNEY


class FeedTests(unittest.TestCase):
    def setUp(self):
        self.us = pd.DataFrame({'Close':[100,101,102]},index=pd.DatetimeIndex(['2026-10-13','2026-10-14','2026-10-15'],tz='America/New_York'))
        self.us_calendar = xcals.get_calendar('XNYS')
        self.minutes = pd.DataFrame({'Open':[101,101.1,100.6],'Volume':[100,10,30]},index=pd.DatetimeIndex(['2026-10-15T10:00:00+11:00','2026-10-15T10:05:00+11:00','2026-10-15T15:55:00+11:00']))
        self.daily = pd.DataFrame({'Close':[100,999]},index=pd.DatetimeIndex(['2026-10-14','2026-10-15'],tz=SYDNEY))
        self.dates = pd.DatetimeIndex(['2026-10-15'])
        self.now = datetime(2026,10,15,8,tzinfo=timezone.utc)

    def test_future_us_close_not_used(self):
        signal=datetime.fromisoformat('2026-10-15T09:30:00+11:00')
        result=us_observation(self.us,signal,self.us_calendar)
        self.assertAlmostEqual(result['us_return_pct'],1)
        self.assertTrue(result['us_close_at'].startswith('2026-10-14'))

    def test_exact_minute_and_traded_volume_required(self):
        self.assertIsNone(minute_open(self.minutes,datetime.fromisoformat('2026-10-15T10:06:00+11:00')))
        self.minutes.loc[self.minutes.index[1],'Volume']=0
        self.assertIsNone(minute_open(self.minutes,self.minutes.index[1]))

    def test_proxy_prices_never_become_spi_signal_or_auction_price(self):
        row=build_rows(self.us,self.minutes,self.daily,self.dates,self.us_calendar,self.now)[0]
        self.assertEqual(row['quality'],'research_proxy_missing_spi')
        p=row['observations']
        self.assertIsNone(p['spi_change_pct'])
        self.assertFalse(p['execution_verified'])
        self.assertNotIn('open_price',p)
        self.assertEqual(p['previous_close'],100)
        self.assertEqual(p['entry_bar_open'],101.1)

    def test_incomplete_session_and_delay_buffer(self):
        now=datetime.fromisoformat('2026-10-15T16:00:00+11:00')
        self.assertEqual(build_rows(self.us,self.minutes,self.daily,self.dates,self.us_calendar,now),[])

    def test_missing_exact_bar_is_not_filled(self):
        bars=self.minutes.drop(self.minutes.index[1])
        row=build_rows(self.us,bars,self.daily,self.dates,self.us_calendar,self.now)[0]
        self.assertEqual(row['quality'],'missing_intraday')
        self.assertIsNone(row['observations']['entry_bar_open'])

    def test_early_close_and_holidays_from_calendar(self):
        self.assertFalse(self.us_calendar.is_session('2026-12-25'))
        self.assertEqual(self.us_calendar.session_close('2026-11-27').tz_convert('America/New_York').hour,13)
        self.assertFalse(xcals.get_calendar('XASX').is_session('2026-12-25'))

if __name__=='__main__':
    unittest.main()
