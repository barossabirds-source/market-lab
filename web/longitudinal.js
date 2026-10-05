(() => {
  const money = (value) => new Intl.NumberFormat('en-AU', { style: 'currency', currency: 'AUD', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value) || 0);
  const signedPercent = (value) => `${Number(value) >= 0 ? '+' : ''}${(Number(value) * 100).toFixed(2)}%`;
  const pct = (value) => `${(Number(value) * 100).toFixed(2)}%`;
  const mean = (values) => values.length ? values.reduce((a,b) => a + b, 0) / values.length : NaN;
  const dateTextLong = (value) => value ? new Date(`${String(value).slice(0,10)}T12:00:00Z`).toLocaleDateString('en-AU',{day:'numeric',month:'short',year:'numeric'}) : 'Unknown';
  const yearOf = (value) => Number(String(value || '').slice(0,4));

  let trendData = null;

  function capital() {
    const input = document.getElementById('capitalInput');
    const n = Number(input?.value || 100);
    return Number.isFinite(n) && n > 0 ? n : 100;
  }

  function cost() {
    const input = document.getElementById('costInput');
    const n = Number(input?.value || 0);
    return Number.isFinite(n) && n >= 0 ? n : 0;
  }

  function eventMap() {
    return new Map((state.events || []).map(e => [String(e.id), e]));
  }

  function termOf(value) {
    const y = yearOf(value);
    if (y >= 2017 && y <= 2020) return 'first';
    if (y >= 2025) return 'second';
    return 'other';
  }

  function isTariffTrialEvent(event) {
    if (!event) return false;
    const theme = String(event.policy_theme || '').toLowerCase();
    const tradeLike = theme.includes('tariff') || ['autos_trade','china_trade','canada_trade','semiconductors'].includes(theme);
    return tradeLike && String(event.direction || '').toLowerCase() === 'escalation' && String(event.surprise_level || '').toLowerCase() === 'high';
  }

  async function buildLongitudinalData() {
    if (!state.connected || !state.events?.length) return null;

    const [oneDayRows, pairRows] = await Promise.all([
      supabaseGet('event_impacts', 'select=event_id,event_date,symbol,asset_group,abnormal_return&horizon=eq.1d&symbol=neq.SPY&limit=1600'),
      supabaseGet('event_impacts', 'select=event_id,event_date,symbol,asset_return&horizon=eq.3d&symbol=in.(XLI,QQQ)&limit=500'),
    ]);

    const events = eventMap();
    const eventStats = new Map();

    oneDayRows.forEach(row => {
      const value = Number(row.abnormal_return);
      if (!Number.isFinite(value)) return;
      const id = String(row.event_id);
      const item = eventStats.get(id) || { date: row.event_date, values: [], leaders: [] };
      item.values.push(value);
      item.leaders.push({ group: row.asset_group || row.symbol, value });
      eventStats.set(id, item);
    });

    const byYear = new Map();
    const byTerm = new Map();
    eventStats.forEach((item, id) => {
      if (!item.values.length) return;
      const yr = yearOf(item.date);
      const term = termOf(item.date);
      const leader = [...item.leaders].sort((a,b) => b.value - a.value)[0];
      const dispersion = Math.max(...item.values) - Math.min(...item.values);

      const y = byYear.get(yr) || { eventIds: new Set(), dispersions: [], leaders: new Map() };
      y.eventIds.add(id);
      y.dispersions.push(dispersion);
      if (leader?.group) y.leaders.set(leader.group, (y.leaders.get(leader.group) || 0) + 1);
      byYear.set(yr, y);

      if (term !== 'other') {
        const t = byTerm.get(term) || { eventIds: new Set(), dispersions: [], leaders: new Map() };
        t.eventIds.add(id);
        t.dispersions.push(dispersion);
        if (leader?.group) t.leaders.set(leader.group, (t.leaders.get(leader.group) || 0) + 1);
        byTerm.set(term, t);
      }
    });

    const summarise = (data) => {
      if (!data) return null;
      const leaders = [...data.leaders.entries()].sort((a,b) => b[1] - a[1]);
      return { events: data.eventIds.size, avgDispersion: mean(data.dispersions), leaders, topLeader: leaders[0] || null };
    };

    const yearly = [...byYear.entries()].sort((a,b) => a[0] - b[0]).map(([year, data]) => ({ year, ...summarise(data) }));

    const pairByEvent = new Map();
    pairRows.forEach(row => {
      const id = String(row.event_id);
      const event = events.get(id);
      if (!isTariffTrialEvent(event)) return;
      const item = pairByEvent.get(id) || { id, date: row.event_date || event.event_date, event };
      item[row.symbol] = Number(row.asset_return);
      pairByEvent.set(id, item);
    });

    const pairEvents = [...pairByEvent.values()]
      .filter(x => Number.isFinite(x.XLI) && Number.isFinite(x.QQQ))
      .map(x => ({ ...x, spread: x.XLI - x.QQQ, term: termOf(x.date) }))
      .sort((a,b) => String(a.date).localeCompare(String(b.date)));

    pairEvents.forEach((row, index) => {
      const end = new Date(`${row.date}T12:00:00Z`);
      const start = new Date(end);
      start.setUTCDate(start.getUTCDate() - 183);
      const windowRows = pairEvents.filter(other => {
        const d = new Date(`${other.date}T12:00:00Z`);
        return d <= end && d >= start;
      });
      row.rollingSixMonthSpread = mean(windowRows.map(x => x.spread));
      row.rollingSixMonthN = windowRows.length;
      row.sequence = index + 1;
    });

    const pairYears = new Map();
    const pairTerms = new Map();
    pairEvents.forEach(row => {
      const yr = yearOf(row.date);
      const yearArr = pairYears.get(yr) || [];
      yearArr.push(row.spread);
      pairYears.set(yr, yearArr);
      if (row.term !== 'other') {
        const termArr = pairTerms.get(row.term) || [];
        termArr.push(row.spread);
        pairTerms.set(row.term, termArr);
      }
    });

    const pairYearly = [...pairYears.entries()].sort((a,b) => a[0] - b[0]).map(([year, spreads]) => ({
      year,
      n: spreads.length,
      avgSpread: mean(spreads),
      winRate: spreads.filter(x => x > 0).length / spreads.length,
    }));

    const termStats = {
      first: summarise(byTerm.get('first')),
      second: summarise(byTerm.get('second')),
      pairFirst: pairTerms.has('first') ? { n: pairTerms.get('first').length, avgSpread: mean(pairTerms.get('first')), winRate: pairTerms.get('first').filter(x => x > 0).length / pairTerms.get('first').length } : null,
      pairSecond: pairTerms.has('second') ? { n: pairTerms.get('second').length, avgSpread: mean(pairTerms.get('second')), winRate: pairTerms.get('second').filter(x => x > 0).length / pairTerms.get('second').length } : null,
    };

    const eventDates = state.events.map(e => e.event_date).filter(Boolean).sort();

    return {
      yearly,
      pairEvents,
      pairYearly,
      terms: termStats,
      coverage: {
        events: state.events.length,
        firstEvent: eventDates[0],
        lastEvent: eventDates[eventDates.length - 1],
      },
    };
  }

  function renderLongitudinal() {
    const summary = document.getElementById('longitudinalSummary');
    const cards = document.getElementById('longitudinalCards');
    const rows = document.getElementById('longitudinalRows');
    if (!summary || !cards || !rows) return;

    if (!trendData) {
      summary.innerHTML = '<strong>Longitudinal view unavailable:</strong> persistent reaction data is not connected.';
      cards.innerHTML = '';
      rows.innerHTML = '';
      return;
    }

    const c = capital();
    const tradeCost = cost();
    const years = trendData.yearly;
    const latestYear = years[years.length - 1];
    const latestPairEvent = trendData.pairEvents[trendData.pairEvents.length - 1];
    const firstTerm = trendData.terms.first;
    const secondTerm = trendData.terms.second;
    const firstPair = trendData.terms.pairFirst;
    const secondPair = trendData.terms.pairSecond;

    const firstPairNet = firstPair ? (c / 2) * firstPair.avgSpread - tradeCost : NaN;
    const secondPairNet = secondPair ? (c / 2) * secondPair.avgSpread - tradeCost : NaN;
    const latestRollingNet = latestPairEvent && Number.isFinite(latestPairEvent.rollingSixMonthSpread)
      ? (c / 2) * latestPairEvent.rollingSixMonthSpread - tradeCost
      : NaN;

    if (firstTerm && secondTerm) {
      const direction = secondTerm.avgDispersion < firstTerm.avgDispersion ? 'smaller' : 'larger';
      summary.innerHTML = `<strong>First term vs second term:</strong> the average one-day gap between the strongest and weakest market areas is ${pct(firstTerm.avgDispersion)} across ${firstTerm.events} first-term events and ${pct(secondTerm.avgDispersion)} across ${secondTerm.events} second-term events. The later response is ${direction}. The tariff-pair result is also shown separately below. This can reveal a changing market response, but it is not proof of a repeatable profit opportunity.`;
    } else {
      summary.innerHTML = '<strong>What is changing:</strong> more historical events are being added before comparing the first and second Trump terms.';
    }

    const latestLeader = latestYear?.topLeader;
    const firstLeader = firstTerm?.topLeader;
    const secondLeader = secondTerm?.topLeader;

    cards.innerHTML = `
      <article class="trend-card">
        <p class="eyebrow">DATA COVERAGE</p>
        <p class="trend-kpi">${trendData.coverage.events} events</p>
        <p>${dateTextLong(trendData.coverage.firstEvent)} to ${dateTextLong(trendData.coverage.lastEvent)}.</p>
      </article>
      <article class="trend-card">
        <p class="eyebrow">FIRST TERM MARKET GAP</p>
        <p class="trend-kpi">${firstTerm ? pct(firstTerm.avgDispersion) : '—'}</p>
        <p>${firstTerm ? `${firstTerm.events} events from 2017–2020.` : 'Backfill still loading.'}</p>
      </article>
      <article class="trend-card">
        <p class="eyebrow">SECOND TERM MARKET GAP</p>
        <p class="trend-kpi">${secondTerm ? pct(secondTerm.avgDispersion) : '—'}</p>
        <p>${secondTerm ? `${secondTerm.events} events from 2025 onward.` : 'No second-term data.'}</p>
      </article>
      <article class="trend-card">
        <p class="eyebrow">FIRST TERM TARIFF PAIR</p>
        <p class="trend-kpi">${Number.isFinite(firstPairNet) ? money(firstPairNet) : '—'}</p>
        <p>${firstPair ? `Average net result per ${money(c)} example after ${money(tradeCost)} entered cost; ${firstPair.n} events, ${Math.round(firstPair.winRate*100)}% positive.` : 'No qualifying events yet.'}</p>
      </article>
      <article class="trend-card">
        <p class="eyebrow">SECOND TERM TARIFF PAIR</p>
        <p class="trend-kpi">${Number.isFinite(secondPairNet) ? money(secondPairNet) : '—'}</p>
        <p>${secondPair ? `Average net result per ${money(c)} example after ${money(tradeCost)} entered cost; ${secondPair.n} events, ${Math.round(secondPair.winRate*100)}% positive.` : 'No qualifying events yet.'}</p>
      </article>
      <article class="trend-card">
        <p class="eyebrow">LATEST 6-MONTH TARIFF AVERAGE</p>
        <p class="trend-kpi">${Number.isFinite(latestRollingNet) ? money(latestRollingNet) : '—'}</p>
        <p>${latestPairEvent ? `${latestPairEvent.rollingSixMonthN} qualifying events in the latest six-month window, after entered cost.` : 'No qualifying tariff events.'}</p>
      </article>
      <article class="trend-card">
        <p class="eyebrow">SECTOR LEADERSHIP</p>
        <p class="trend-kpi">${latestLeader ? latestLeader[0] : '—'}</p>
        <p>${secondLeader ? `Second term: ${secondLeader[0]} led ${secondLeader[1]} times.` : ''}${firstLeader ? ` First term: ${firstLeader[0]} led ${firstLeader[1]} times.` : ''}</p>
      </article>`;

    let running = 0;
    rows.innerHTML = trendData.pairEvents.map(row => {
      const gross = (c / 2) * row.spread;
      const result = gross - tradeCost;
      running += result;
      const rolling = (c / 2) * row.rollingSixMonthSpread - tradeCost;
      const event = row.event || {};
      return `<tr>
        <td>${dateTextLong(row.date)}</td>
        <td>${escapeHtml(pretty(event.policy_theme || 'Trade policy'))}</td>
        <td class="${result > 0 ? 'pos' : result < 0 ? 'neg' : ''}">${money(result)}</td>
        <td>${money(rolling)} <span class="muted">(${row.rollingSixMonthN} events)</span></td>
        <td class="${running > 0 ? 'pos' : running < 0 ? 'neg' : ''}">${money(running)}</td>
      </tr>`;
    }).join('') || '<tr><td colspan="5">No qualifying tariff-pair events yet.</td></tr>';
  }

  async function initialiseLongitudinal() {
    const summary = document.getElementById('longitudinalSummary');
    if (!summary) return;
    for (let i = 0; i < 50 && (!state.events?.length); i++) {
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    try {
      trendData = await buildLongitudinalData();
      renderLongitudinal();
    } catch (error) {
      console.warn('Longitudinal analysis could not be calculated', error);
      summary.innerHTML = '<strong>Longitudinal view unavailable:</strong> the trend calculation could not be loaded.';
    }
    document.getElementById('capitalInput')?.addEventListener('input', renderLongitudinal);
    document.getElementById('costInput')?.addEventListener('input', renderLongitudinal);
  }

  window.addEventListener('load', initialiseLongitudinal);
})();
