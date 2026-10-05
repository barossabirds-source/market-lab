(() => {
  const money = (value) => new Intl.NumberFormat('en-AU', { style: 'currency', currency: 'AUD', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(value) || 0);
  const percent = (value) => `${Number(value) >= 0 ? '+' : ''}${(Number(value) * 100).toFixed(2)}%`;
  const mean = (values) => values.length ? values.reduce((a,b) => a + b, 0) / values.length : NaN;
  const min = (values) => values.length ? Math.min(...values) : NaN;
  const max = (values) => values.length ? Math.max(...values) : NaN;

  let findings = null;

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
    return tradeLike && String(event.direction).toLowerCase() === 'escalation' && String(event.surprise_level).toLowerCase() === 'high';
  }

  async function buildFindings() {
    if (!state.connected || !state.events?.length) return null;

    const [pairRows, energyRows, oneDayRows] = await Promise.all([
      supabaseGet('event_impacts', 'select=event_id,symbol,asset_return,benchmark_return,abnormal_return&horizon=eq.3d&symbol=in.(XLI,QQQ)&limit=250'),
      supabaseGet('event_impacts', 'select=event_id,symbol,asset_return,benchmark_return,abnormal_return&horizon=eq.5d&symbol=eq.XLE&limit=100'),
      supabaseGet('event_impacts', 'select=event_id,symbol,abnormal_return&horizon=eq.1d&symbol=neq.SPY&limit=1000'),
    ]);

    const events = eventMap();

    const pairByEvent = new Map();
    pairRows.forEach(row => {
      const id = String(row.event_id);
      if (!isTariffTrialEvent(events.get(id))) return;
      const item = pairByEvent.get(id) || {};
      item[row.symbol] = row;
      pairByEvent.set(id, item);
    });
    const tariffSpreads = [...pairByEvent.values()]
      .filter(x => x.XLI && x.QQQ && x.XLI.asset_return !== null && x.QQQ.asset_return !== null)
      .map(x => Number(x.XLI.asset_return) - Number(x.QQQ.asset_return));

    const formalEnergy = energyRows.filter(row => {
      const event = events.get(String(row.event_id));
      return event && String(event.policy_theme || '').toLowerCase().includes('energy') && String(event.source_type || '').toLowerCase() === 'formal_action';
    });
    const formalEnergyAssetReturns = formalEnergy.map(x => Number(x.asset_return)).filter(Number.isFinite);
    const formalEnergyRelativeReturns = formalEnergy.map(x => Number(x.asset_return) - Number(x.benchmark_return)).filter(Number.isFinite);

    const dispersionByEvent = new Map();
    oneDayRows.forEach(row => {
      const value = Number(row.abnormal_return);
      if (!Number.isFinite(value)) return;
      const id = String(row.event_id);
      const values = dispersionByEvent.get(id) || [];
      values.push(value);
      dispersionByEvent.set(id, values);
    });
    const formalDispersion = [];
    const otherDispersion = [];
    dispersionByEvent.forEach((values, id) => {
      if (!values.length) return;
      const event = events.get(id);
      const spread = Math.max(...values) - Math.min(...values);
      if (String(event?.source_type || '').toLowerCase() === 'formal_action') formalDispersion.push(spread);
      else otherDispersion.push(spread);
    });

    const unknownTiming = state.events.filter(e => String(e.market_session || 'unknown').toLowerCase() === 'unknown').length;

    return {
      tariff: {
        n: tariffSpreads.length,
        avg: mean(tariffSpreads),
        min: min(tariffSpreads),
        max: max(tariffSpreads),
        winRate: tariffSpreads.length ? tariffSpreads.filter(x => x > 0).length / tariffSpreads.length : NaN,
      },
      energy: {
        n: formalEnergyAssetReturns.length,
        avgAsset: mean(formalEnergyAssetReturns),
        avgRelative: mean(formalEnergyRelativeReturns),
      },
      dispersion: {
        formalN: formalDispersion.length,
        otherN: otherDispersion.length,
        formalAvg: mean(formalDispersion),
        otherAvg: mean(otherDispersion),
      },
      timing: { unknown: unknownTiming, total: state.events.length },
    };
  }

  function renderExecutive() {
    const cards = document.getElementById('executiveCards');
    const recommendations = document.getElementById('recommendationCards');
    const status = document.getElementById('executiveStatus');
    if (!cards || !recommendations || !status) return;

    if (!findings) {
      status.innerHTML = '<strong>Executive summary unavailable:</strong> persistent market-reaction data is not connected.';
      cards.innerHTML = '';
      recommendations.innerHTML = '';
      return;
    }

    const c = capital();
    const tariffPairAvg = Number.isFinite(findings.tariff.avg) ? (c / 2) * findings.tariff.avg : NaN;
    const tariffPairBest = Number.isFinite(findings.tariff.max) ? (c / 2) * findings.tariff.max : NaN;
    const tariffPairWorst = Number.isFinite(findings.tariff.min) ? (c / 2) * findings.tariff.min : NaN;
    const energyLong = Number.isFinite(findings.energy.avgAsset) ? c * findings.energy.avgAsset : NaN;
    const energyHedged = Number.isFinite(findings.energy.avgRelative) ? (c / 2) * findings.energy.avgRelative : NaN;
    const timingPct = findings.timing.total ? Math.round(100 * findings.timing.unknown / findings.timing.total) : 0;

    status.innerHTML = '<strong>Current conclusion:</strong> nothing is ready for simulated trading yet. The tariff pair has a slightly negative average result, the energy result is based on one formal action, and the formal-action dispersion idea is not supported by the current sample.';

    cards.innerHTML = `
      <article class="exec-card">
        <p class="eyebrow">TARIFF ESCALATION · 3 TRADING DAYS</p>
        <h3>Industrials long / technology short</h3>
        <p class="exec-lead">${Number.isFinite(tariffPairAvg) ? money(tariffPairAvg) : '—'}</p>
        <p>Average gross profit/loss using <strong>${money(c)}</strong> of total exposure, split ${money(c/2)} long US industrials and ${money(c/2)} short large technology.</p>
        <dl class="exec-stats">
          <div><dt>Events</dt><dd>${findings.tariff.n}</dd></div>
          <div><dt>Positive trades</dt><dd>${Number.isFinite(findings.tariff.winRate) ? `${Math.round(findings.tariff.winRate*100)}%` : '—'}</dd></div>
          <div><dt>Best observed</dt><dd>${Number.isFinite(tariffPairBest) ? money(tariffPairBest) : '—'}</dd></div>
          <div><dt>Worst observed</dt><dd>${Number.isFinite(tariffPairWorst) ? money(tariffPairWorst) : '—'}</dd></div>
        </dl>
        <p class="exec-verdict bad"><strong>Drop for now.</strong> The average result is negative.</p>
      </article>

      <article class="exec-card">
        <p class="eyebrow">FORMAL ENERGY ACTION · 5 TRADING DAYS</p>
        <h3>Energy sector example</h3>
        <p class="exec-lead">${Number.isFinite(energyLong) ? money(energyLong) : '—'}</p>
        <p>Gross change from putting <strong>${money(c)}</strong> long into the US energy-sector fund after the formal energy action measured so far.</p>
        <dl class="exec-stats">
          <div><dt>Formal actions measured</dt><dd>${findings.energy.n}</dd></div>
          <div><dt>Fund return</dt><dd>${Number.isFinite(findings.energy.avgAsset) ? percent(findings.energy.avgAsset) : '—'}</dd></div>
          <div><dt>${money(c/2)} long energy / ${money(c/2)} short broad market</dt><dd>${Number.isFinite(energyHedged) ? money(energyHedged) : '—'}</dd></div>
          <div><dt>Relative return</dt><dd>${Number.isFinite(findings.energy.avgRelative) ? percent(findings.energy.avgRelative) : '—'}</dd></div>
        </dl>
        <p class="exec-verdict warn"><strong>Keep watching.</strong> One formal energy event is not enough evidence.</p>
      </article>

      <article class="exec-card">
        <p class="eyebrow">FORMAL ACTIONS VS REMARKS</p>
        <h3>Sector dispersion</h3>
        <p class="exec-lead">No trade yet</p>
        <p>Formal actions produced an average one-day gap of <strong>${Number.isFinite(findings.dispersion.formalAvg) ? percent(findings.dispersion.formalAvg) : '—'}</strong> between the strongest and weakest market areas, versus <strong>${Number.isFinite(findings.dispersion.otherAvg) ? percent(findings.dispersion.otherAvg) : '—'}</strong> for remarks/interviews.</p>
        <dl class="exec-stats">
          <div><dt>Formal actions</dt><dd>${findings.dispersion.formalN}</dd></div>
          <div><dt>Remarks/other</dt><dd>${findings.dispersion.otherN}</dd></div>
        </dl>
        <p class="exec-verdict bad"><strong>No trade rule yet.</strong> The current result does not support the idea.</p>
      </article>`;

    recommendations.innerHTML = `
      <article class="recommendation"><strong>1. No proven arbitrage yet.</strong><p>Nothing is ready to trade.</p></article>
      <article class="recommendation"><strong>2. Improve event timing.</strong><p>${findings.timing.unknown} of ${findings.timing.total} events (${timingPct}%) still have unknown trading time.</p></article>
      <article class="recommendation"><strong>3. Keep watching energy.</strong><p>The result is interesting, but the sample is only ${findings.energy.n} formal event${findings.energy.n === 1 ? '' : 's'}.</p></article>
      <article class="recommendation"><strong>4. Include trading costs.</strong><p>Small gross gains can disappear after fees, spreads and currency conversion.</p></article>`;
  }

  async function initialiseExecutive() {
    const status = document.getElementById('executiveStatus');
    if (!status) return;
    for (let i = 0; i < 50 && (!state.events?.length); i++) {
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    try {
      findings = await buildFindings();
      renderExecutive();
    } catch (error) {
      console.warn('Executive findings could not be calculated', error);
      status.innerHTML = '<strong>Executive summary unavailable:</strong> the detailed market-reaction calculation could not be loaded.';
    }
    document.getElementById('capitalInput')?.addEventListener('input', renderExecutive);
  }

  window.addEventListener('load', initialiseExecutive);
})();
