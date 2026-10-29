"""Versioned event predictions and descriptive evidence; no orders or causal claims."""
from __future__ import annotations

import math
from datetime import datetime, timezone
from statistics import mean, median, stdev
from zoneinfo import ZoneInfo

SYDNEY = ZoneInfo('Australia/Sydney')
KEY = 'wall-street-up-asx-v1'
RULE = {
    'hypothesis_key': KEY,
    'title': 'Wall Street up → ASX movement after opening',
    'event_category': 'overnight_market_move',
    'mechanism': 'US equity sentiment may carry into Australian trading; shared news may also drive both markets.',
    'config': {
        'symbol': 'A200.AX', 'us_symbol': '^GSPC', 'threshold_pct': 0,
        'entry_time_sydney': '10:05:00', 'exit_time_sydney': '15:55:00',
        'capital_aud': 2000, 'brokerage_round_trip_aud': 10,
        'friction_round_trip_bps': 10,
        'minimum_per_group': 30, 'review_after_signal_sessions': 60,
        'pause_drawdown_aud': 200, 'validation_requirement': 'pre-entry frozen prediction plus verified execution prices',
        'comparison': 'same ETF and time window on US flat/down sessions',
        'stop_rule': 'Pause at A$200 fixed-size cumulative drawdown; review after 60 signal sessions. No support if the signal mean is nonpositive or fails to exceed comparison days. Never auto-promote to live trading.',
    },
}


def number(value):
    if value is None or isinstance(value, bool) or value == '':
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def instant(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result if result.utcoffset() is not None else None
    except (ValueError, TypeError):
        return None


def stats(rows):
    values = [r['net_aud'] for r in rows]
    if not values:
        return {'n': 0, 'mean': None, 'median': None, 'win_rate': None,
                'win_interval': None, 'mean_interval': None, 'average_win': None,
                'average_loss': None, 'worst': None, 'drawdown': None}
    n = len(values)
    wins, losses = [v for v in values if v > 0], [v for v in values if v < 0]
    p, z = len(wins) / n, 1.96
    centre = (p + z*z/(2*n)) / (1 + z*z/n)
    radius = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / (1+z*z/n)
    margin = z * stdev(values) / math.sqrt(n) if n > 1 else None
    running = peak = fall = 0
    for value in values:
        running += value
        peak = max(peak, running)
        fall = min(fall, running - peak)
    return {'n': n, 'mean': mean(values), 'median': median(values), 'win_rate': p,
            'win_interval': [max(0, centre-radius), min(1, centre+radius)],
            'mean_interval': [mean(values)-margin, mean(values)+margin] if margin is not None else None,
            'average_win': mean(wins) if wins else None,
            'average_loss': mean(losses) if losses else None, 'worst': min(values), 'drawdown': fall}


def outcome(row, prediction, rule, now):
    p, config = row.get('observations') or {}, rule['config']
    us = number(p.get('us_return_pct'))
    entry, exit_at, close = (instant(p.get(k)) for k in ['entry_at', 'exit_at', 'us_close_at'])
    a, b = number(p.get('entry_bar_open')), number(p.get('exit_bar_open'))
    reasons = []
    if us is None or close is None:
        reasons.append('missing_us_observation')
    if entry is None or exit_at is None or close is None or not close < entry < exit_at <= now:
        reasons.append('invalid_or_incomplete_timing')
    if entry and exit_at:
        if (entry.astimezone(SYDNEY).date().isoformat() != row['session_date']
            or exit_at.astimezone(SYDNEY).date().isoformat() != row['session_date']
            or entry.astimezone(SYDNEY).strftime('%H:%M:%S') != config['entry_time_sydney']
            or exit_at.astimezone(SYDNEY).strftime('%H:%M:%S') != config['exit_time_sydney']):
            reasons.append('wrong_session_or_window')
    if close and entry and (entry-close).total_seconds() > 96*3600:
        reasons.append('stale_us_observation')
    if a is None or b is None or a <= 0 or b <= 0:
        reasons.append('missing_exact_price_bar')
    frozen = prediction.get('prediction') if prediction else None
    if frozen and (number(frozen.get('us_return_pct')) != us or frozen.get('us_close_at') != p.get('us_close_at')):
        reasons.append('morning_evening_source_mismatch')
    captured = instant(prediction.get('captured_at')) if prediction else None
    registered = instant(rule.get('registered_at'))
    pre_entry = bool(captured and entry and registered and registered <= captured < entry)
    signal = frozen['signal'] if frozen else us > config['threshold_pct'] if us is not None else None
    gross = config['capital_aud'] * (b/a-1) if not reasons else None
    cost = config['brokerage_round_trip_aud'] + config['capital_aud'] * config['friction_round_trip_bps']/10000
    previous, opening = number(p.get('previous_close')), number(p.get('opening_bar_proxy'))
    return {'hypothesis_key': KEY, 'event_key': row['session_date'],
            'session_date': row['session_date'], 'symbol': row['symbol'],
            'source': row['source'], 'source_captured_at': row['captured_at'],
            'signal': signal, 'us_return_pct': us, 'entry_at': p.get('entry_at'), 'exit_at': p.get('exit_at'),
            'result': {'gross_aud': gross, 'net_aud': gross-cost if gross is not None else None,
                       'cost_aud': cost, 'pre_entry_frozen': pre_entry,
                       'execution_verified': False, 'exclusions': reasons,
                       'opening_gap_proxy': opening/previous-1 if opening and previous and previous > 0 else None,
                       'confounder_review': 'unreviewed', 'surprise': 'not_assessed',
                       'intraday_adverse_excursion': None, 'intraday_favourable_excursion': None},
            'updated_at': now.isoformat()}


def summarise(outcomes, rule):
    ordered = sorted(outcomes, key=lambda r: r['session_date'])
    def group(rows):
        usable = [dict(r, net_aud=r['result']['net_aud']) for r in rows
                  if r['result']['net_aud'] is not None and not r['result']['exclusions']]
        signal = stats([r for r in usable if r['signal'] is True])
        other = stats([r for r in usable if r['signal'] is False])
        return {'observed': len(rows), 'missing_or_excluded': len(rows)-len(usable),
                'signal': signal, 'comparison': other,
                'mean_difference_aud': signal['mean']-other['mean'] if signal['n'] and other['n'] else None,
                'win_rate_difference': signal['win_rate']-other['win_rate'] if signal['n'] and other['n'] else None}
    frozen = [r for r in ordered if r['result']['pre_entry_frozen']]
    forward = group(frozen)
    status = 'collecting'
    s, c = forward['signal'], forward['comparison']
    if s['drawdown'] is not None and s['drawdown'] <= -rule['config']['pause_drawdown_aud']:
        status = 'paused_drawdown'
    elif s['n'] >= rule['config']['review_after_signal_sessions'] and (s['mean'] <= 0 or (c['n'] and s['mean'] <= c['mean'])):
        status = 'not_supported'
    elif min(s['n'], c['n']) >= rule['config']['minimum_per_group']:
        status = 'awaiting_validation' if s['mean'] > 0 and s['mean'] > c['mean'] else 'mixed'
    return {'hypothesis_key': KEY, 'status': status, 'all_proxy': group(ordered),
            'forward_proxy': forward,
            'validated': group([r for r in frozen if r['result']['execution_verified']]),
            'latest_session': ordered[-1]['session_date'] if ordered else None,
            'limitations': 'Association only. Yahoo minute bars are proxies. Confounders unreviewed. Approximate 95% intervals assume independent sessions; serial dependence and multiple testing are not adjusted. Tax and whole-unit rounding excluded.'}


def read_all(db, table, query):
    rows, offset = [], 0
    while True:
        batch = db.request('GET', table, query=f'{query}&limit=500&offset={offset}') or []
        rows.extend(batch)
        if len(batch) < 500:
            return rows
        offset += len(batch)


def register(db):
    db.request('POST', 'event_hypotheses', [RULE], query='on_conflict=hypothesis_key',
               prefer='resolution=ignore-duplicates,return=minimal')
    saved = db.request('GET', 'event_hypotheses', query=f'hypothesis_key=eq.{KEY}&select=*')[0]
    if any(saved.get(k) != RULE[k] for k in RULE):
        raise RuntimeError('Frozen hypothesis changed: create a new version key')
    return saved


def freeze_prediction(db, rule, us, now):
    local = now.astimezone(SYDNEY)
    if not '09:30:00' <= local.strftime('%H:%M:%S') < '10:00:00' or us is None:
        return False
    day = local.date().isoformat()
    record = {'hypothesis_key': KEY, 'event_key': day, 'session_date': day,
              'captured_at': now.isoformat(), 'source_url': 'https://finance.yahoo.com/quote/%5EGSPC/history/',
              'published_at': us['us_close_at'], 'prediction': {
                  **us, 'signal': us['us_return_pct'] > rule['config']['threshold_pct'],
                  'direction': 'positive_after_cost_vs_flat_down_days', 'expected': None,
                  'surprise': 'not_assessed', 'confounders': 'unreviewed'}}
    db.request('POST', 'event_predictions', [record], query='on_conflict=hypothesis_key,event_key',
               prefer='resolution=ignore-duplicates,return=minimal')
    return True


def sync_evidence(db, rule, now):
    raw = read_all(db, 'asx_session_observations', 'select=*&symbol=eq.A200.AX&source=eq.yahoo_research_v1&order=session_date')
    predictions = {r['event_key']: r for r in read_all(db, 'event_predictions', f'select=*&hypothesis_key=eq.{KEY}&order=event_key')}
    outcomes = [outcome(r, predictions.get(r['session_date']), rule, now) for r in raw]
    for start in range(0, len(outcomes), 100):
        db.request('POST', 'event_outcomes', outcomes[start:start+100], query='on_conflict=hypothesis_key,event_key',
                   prefer='resolution=merge-duplicates,return=minimal')
    summary = summarise(outcomes, rule)
    db.status('event_evidence', summary['status'], 'Wall Street → ASX evidence updated. Research proxies; no validated trading edge.', summary)
    return summary
