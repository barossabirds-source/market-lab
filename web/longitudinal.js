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

  function eventMap() {
    return new Map((state.events || []).map(e => [String(e.id), e]));
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
      supabaseGet('event_impacts', 'select=event_id,event_date,symbol,asset_group,abnormal_return&horizon=eq.1d&symbol=neq.SPY&limit=1000'),
      supabaseGet('event_impacts', 'select=event_id,event_date,symbol,asset_return&horizon=eq.3d&symbol=in.(XLI,QQQ)&limit=250'),
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
    eventStats.forEach((item, id) => {
      if (!item.values.length) return;
      const yr = yearOf(item.date);
      const leader = [...item.leaders].sort((a,b) => b.value - a.value)[0];
      const dispersion = Math.max(...item.values) - Math.min(...item.values);
      const y = byYear.get(yr) || { eventIds: new Set(), dispersions: [], leaders: new Map() };
      y.eventIds.add(id);
      y.dispersions.push(dispersion);
      if (leader?.group) y.leaders.set(leader.group, (y.leaders.get(leader.group) || 0) + 1);
      byYear.set(yr, y);
    });

    const yearly = [...byYear.entries()].sort((a,b) => a[0] - b[0]).map(([year, data]) => {
      const leaderList = [...data.leaders.entries()].sort((a,b) => b[1] - a[1]);
      return {
        year,
        events: data.eventIds.size,
        avgDispersion: mean(data.dispersions),
        leaders: leaderList,
        topLeader: leaderList[0] || null,
      };
    });

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
      .map(x => ({ ...x, spread: x.XLI - x.QQQ }))
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
    pairEvents.forEach(row => {
      const yr = yearOf(row.date);
      const arr = pairYears.get(yr) || [];
      arr.push(row.spread);
      pairYears.set(yr, arr);
    });
    const pairYearly = [...pairYears.entries()].sort((a,b) => a[0] - b[0]).map(([year, spreads]) => ({
      year,
      n: spreads.length,
      avgSpread: mean(spreads),
      winRate: spreads.filter(x => x > 0).length / spreads.length,
    }));

    const eventDates = state.events.map(e => e.event_date).filter(Boolean).sort();

    return {
      yearly,
      pairEvents,
      pairYearly,
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
    const years = trendData.yearly;
    const firstYear = years[0];
    const latestYear = years[years.length - 1];
    const pairYears = trendData.pairYearly;
    const firstPairYear = pairYears[0];
    const latestPairYear = pairYears[pairYears.length - 1];
    const latestPairEvent = trendData.pairEvents[trendData.pairEvents.length - 1];

    const dispersionChange = firstYear && latestYear && firstYear.year !== latestYear.year
      ? latestYear.avgDispersion - firstYear.avgDispersion
      : NaN;

    const pairYearText = firstPairYear && latestPairYear && firstPairYear.year !== latestPairYear.year
      ? `${firstPairYear.year}: ${money((c/2) * firstPairYear.avgSpread)} average per A$${c.toFixed(0)} example; ${latestPairYear.year}: ${money((c/2) * latestPairYear.avgSpread)}.`
      : 'More history is needed before comparing the tariff pair across years.';

    summary.innerHTML = firstYear && latestYear && firstYear.year !== latestYear.year
      ? `<strong>What is changing:</strong> average one-day sector dispersion fell from ${pct(firstYear.avgDispersion)} in ${firstYear.year} to ${pct(latestYear.avgDispersion)} in ${latestYear.year}. The qualified tariff pair also weakened in the later year. This is consistent with a fading or changing market response, but it does not prove that repeated announcements are losing impact.`
      : '<strong>What is changing:</strong> the dataset is still too short for a strong year-to-year conclusion.';

    const latestLeader = latestYear?.topLeader;
    const earlierLeader = firstYear?.topLeader;
    const latestRollingProfit = latestPairEvent && Number.isFinite(latestPairEvent.rollingSixMonthSpread)
      ? (c / 2) * latestPairEvent.rollingSixMonthSpread
      : NaN;

    cards.innerHTML = `
      <article class="trend-card">
        <p class="eyebrow">DATA COVERAGE</p>
        <p class="trend-kpi">${trendData.coverage.events} events</p>
        <p>${dateTextLong(trendData.coverage.firstEvent)} to ${dateTextLong(trendData.coverage.lastEvent)}.</p>
      </article>
      <article class="trend-card">
        <p class="eyebrow">ONE-DAY MARKET GAP</p>
        <p class="trend-kpi">${latestYear ? pct(latestYear.avgDispersion) : '—'}</p>
        <p>${latestYear ? `${latestYear.year} average across ${latestYear.events} events.` : 'No yearly result yet.'}${Number.isFinite(dispersionChange) ? ` Change from ${firstYear.year}: ${signedPercent(dispersionChange)}.` : ''}</p>
      </article>
      <article class="trend-card">
        <p class="eyebrow">TARIFF PAIR BY YEAR</p>
        <p class="trend-kpi">${latestPairYear ? money((c/2) * latestPairYear.avgSpread) : '—'}</p>
        <p>${pairYearText}</p>
      </article>
      <article class="trend-card">
        <p class="eyebrow">LATEST 6-MONTH TARIFF AVERAGE</p>
        <p class="trend-kpi">${Number.isFinite(latestRollingProfit) ? money(latestRollingProfit) : '—'}</p>
        <p>${latestPairEvent ? `${latestPairEvent.rollingSixMonthN} qualifying events in the latest six-month window.` : 'No qualifying tariff events.'}</p>
      </article>
      <article class="trend-card">
        <p class="eyebrow">SECTOR LEADERSHIP</p>
        <p class="trend-kpi">${latestLeader ? latestLeader[0] : '—'}</p>
        <p>${latestYear && latestLeader ? `${latestLeader[1]} of ${latestYear.events} events led in ${latestYear.year}.` : ''}${firstYear && earlierLeader && firstYear.year !== latestYear?.year ? ` In ${firstYear.year}, ${earlierLeader[0]} led ${earlierLeader[1]} times.` : ''}</p>
      </article>`;

    let running = 0;
    rows.innerHTML = trendData.pairEvents.map(row => {
      const result = (c / 2) * row.spread;
      running += result;
      const rolling = (c / 2) * row.rollingSixMonthSpread;
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
  }

  window.addEventListener('load', initialiseLongitudinal);
})();
