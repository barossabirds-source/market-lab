"""Capture compact US / ASX research observations after Australian market close.

Yahoo minute-bar opens are research proxies, not executable quotes. No SPI
contract is guessed. Raw observations remain private and never enter the strict
ASX signal study while SPI and verified quote/auction data are missing.
"""
from __future__ import annotations

import json
import math
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

SYDNEY = ZoneInfo('Australia/Sydney')
SOURCE = 'yahoo_research_v1'
SYMBOL = 'A200.AX'


def finite(value):
    try:
        n = float(value)
        return n if math.isfinite(n) and n > 0 else None
    except (TypeError, ValueError):
        return None


def minute_open(frame, instant):
    """Require the exact minute and a nonzero traded volume; never fill forward."""
    if frame.empty or instant not in frame.index:
        return None
    row = frame.loc[instant]
    if not finite(row.get('Volume')):
        return None
    return finite(row.get('Open'))


def us_observation(frame, signal_at, calendar):
    eligible = []
    for stamp, row in frame.iterrows():
        day = stamp.date().isoformat()
        if not calendar.is_session(day):
            continue
        close_at = calendar.session_close(day).to_pydatetime()
        value = finite(row.get('Close'))
        if close_at < signal_at and value:
            eligible.append((close_at, value))
    eligible.sort()
    if len(eligible) < 2:
        return None
    latest, previous = eligible[-1], eligible[-2]
    if signal_at - latest[0] > timedelta(hours=96):
        return None
    return {'us_return_pct': (latest[1] / previous[1] - 1) * 100,
            'us_close_at': latest[0].isoformat(), 'us_previous_close_at': previous[0].isoformat()}


def build_rows(us, intraday, daily, dates, us_calendar, now):
    rows = []
    for day in dates:
        session = day.date().isoformat()
        def at(clock):
            return datetime.fromisoformat(f'{session}T{clock}').replace(tzinfo=SYDNEY)
        signal, entry, exit_at = at('09:30:00'), at('10:05:00'), at('15:55:00')
        # Leave time for a delayed intraday response. Partial sessions never enter storage.
        if exit_at + timedelta(minutes=30) > now:
            continue
        us_data = us_observation(us, signal, us_calendar)
        entry_price, exit_price = minute_open(intraday, entry), minute_open(intraday, exit_at)
        earlier = daily[[x.date().isoformat() < session for x in daily.index]]
        previous_close = finite(earlier.iloc[-1]['Close']) if not earlier.empty else None
        # The first traded minute is NOT asserted to be the opening auction.
        day_bars = intraday[[x.tz_convert(SYDNEY).date().isoformat() == session for x in intraday.index]]
        first_bar = next(((stamp, finite(row['Open'])) for stamp, row in day_bars.iterrows()
                          if at('10:00:00') <= stamp <= entry and finite(row.get('Volume')) and finite(row.get('Open'))), None)
        quality = 'missing_us_close' if us_data is None else 'missing_intraday' if None in (entry_price, exit_price, previous_close) else 'research_proxy_missing_spi'
        payload = {**(us_data or {}), 'signal_at': signal.isoformat(),
                   'spi_change_pct': None, 'spi_observed_at': None,
                   'previous_close': previous_close,
                   'entry_bar_open': entry_price, 'entry_at': entry.isoformat(),
                   'exit_bar_open': exit_price, 'exit_at': exit_at.isoformat(),
                   'opening_bar_proxy': first_bar[1] if first_bar else None,
                   'opening_bar_at': first_bar[0].isoformat() if first_bar else None,
                   'price_basis': 'unadjusted_1m_bar_open', 'execution_verified': False}
        rows.append({'session_date': session, 'symbol': SYMBOL, 'source': SOURCE,
                     'captured_at': now.isoformat(), 'quality': quality, 'observations': payload})
    return rows


class Database:
    def __init__(self):
        import requests
        self.requests = requests
        self.url = os.getenv('SUPABASE_URL', '').rstrip('/')
        key = os.getenv('SUPABASE_SECRET_KEY') or os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')
        if not self.url or not key:
            raise RuntimeError('Database credentials are not configured')
        self.headers = {'apikey': key, 'Content-Type': 'application/json'}
        if key.startswith('eyJ'):
            self.headers['Authorization'] = 'Bearer ' + key

    def request(self, method, table, rows=None, query='', prefer=None):
        headers = dict(self.headers)
        if prefer:
            headers['Prefer'] = prefer
        response = self.requests.request(method, self.url + '/rest/v1/' + table + ('?' + query if query else ''),
                                         headers=headers, data=json.dumps(rows, allow_nan=False) if rows is not None else None, timeout=40)
        if not response.ok:
            # Never put credentials, URLs or provider responses into public health records.
            raise RuntimeError(f'Database operation failed ({response.status_code})')
        return response.json() if response.text else None

    def status(self, key, status, message, details=None):
        self.request('POST', 'asx_feed_status', [{'feed_key': key, 'checked_at': datetime.now(timezone.utc).isoformat(),
                     'status': status, 'message': message, 'details': details or {}}], query='on_conflict=feed_key',
                     prefer='resolution=merge-duplicates,return=minimal')


def main():
    db = Database()
    db.status('spi_futures', 'not_configured', 'An authorised SPI futures feed is required. No futures contract or settlement value is inferred.')
    try:
        import exchange_calendars as xcals
        import yfinance as yf
        now = datetime.now(timezone.utc)
        asx, nyse = xcals.get_calendar('XASX'), xcals.get_calendar('XNYS')
        us = yf.Ticker('^GSPC').history(period='1mo', interval='1d', auto_adjust=False)
        intraday = yf.Ticker(SYMBOL).history(period='5d', interval='1m', auto_adjust=False, prepost=False)
        daily = yf.Ticker(SYMBOL).history(period='1mo', interval='1d', auto_adjust=False)
        if intraday.empty or us.empty or daily.empty:
            raise RuntimeError('Provider returned an empty dataset')
        if intraday.index.tz is None or us.index.tz is None or daily.index.tz is None:
            raise RuntimeError('Provider timestamps have no timezone')
        first = intraday.index.min().tz_convert(SYDNEY).date()
        dates = asx.sessions_in_range(first.isoformat(), now.astimezone(SYDNEY).date().isoformat())
        rows = build_rows(us, intraday, daily, dates, nyse, now)
        # Preserve first acquisition; repeating a run never rewrites history or adds duplicates.
        if rows:
            db.request('POST', 'asx_session_observations', rows,
                       query='on_conflict=session_date,symbol,source',
                       prefer='resolution=ignore-duplicates,return=minimal')
        missing = sum(r['quality'] != 'research_proxy_missing_spi' for r in rows)
        db.status('research_prices', 'partial' if rows else 'waiting',
                  'US closes and ETF minute bars collected for research. SPI futures and executable quote/auction data remain unconnected.',
                  {'attempted_sessions': len(rows), 'sessions_with_gaps': missing,
                   'latest_attempted_session': rows[-1]['session_date'] if rows else None,
                   'provider': 'Yahoo via yfinance', 'symbol': SYMBOL, 'live_signal_ready': False})
        print(f'ASX collection completed: {len(rows)} sessions submitted, {missing} with additional data gaps. SPI remains unconnected.')
    except Exception as error:
        db.status('research_prices', 'error', 'Automatic collection failed. No missing values have been filled or treated as trading signals.', {'error_type': type(error).__name__})
        raise
    finally:
        usage = db.request('POST', 'rpc/asx_collection_storage', {})
        db.status('storage', 'ok', 'One private row per session and source; latest operational status only. No full tick stream or raw API response archive.', usage)


if __name__ == '__main__':
    main()
