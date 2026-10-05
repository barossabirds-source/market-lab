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

  function tradingCost() {
    const input = document.getElementById('costInput');
    const n = Number(input?.value || 0);
    return Number.isFinite(n) && n >= 0 ? n : 0;
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

  function breakEvenCapital(rate, cost) {
    if (!Number.isFinite(rate) || rate <= 0 || !Number.isFinite(cost) || cost <= 0) return NaN;
    return cost / rate;
  }

  async function buildFindings() {
    if (!state.connected || !state.events?.length) return null;

    const [pairRows, energyRows, oneDayRows] = await Promise.all([
      supabaseGet('event_impacts', 'select=event_id,symbol,asset_return,benchmark_return,abnormal_return&horizon=eq.3d&symbol=in.(XLI,QQQ)&limit=500'),
      supabaseGet('event_impacts', 'select=event_id,symbol,asset_return,benchmark_return,abnormal_return&horizon=eq.5d&symbol=eq.XLE&limit=200'),
      supabaseGet('event_impacts', 'select=event_id,symbol,abnormal_return&horizon=eq.1d&symbol=neq.SPY&limit=1500'),
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
    const tariffTrial = (state.trials || []).find(t => String(t.trial_key || '').includes('tariff-industrials-vs-tech'));
    const outOfSample = tariffTrial?.out_of_sample_effect === null || tariffTrial?.out_of_sample_effect === undefined
      ? NaN
      : Number(tariffTrial.out_of_sample_effect);

    return {
      tariff: {
        n: tariffSpreads.length,
        avg: mean(tariffSpreads),
        min: min(tariffSpreads),
        max: max(tariffSpreads),
        winRate: tariffSpreads.length ? tariffSpreads.filter(x => x > 0).length / tariffSpreads.length : NaN,
        outOfSample,
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

  function renderReadiness(c, cost, tariffPairAvg) {
    const box = document.getElementById('capitalReadiness');
    if (!box || !findings) return;

    const enoughEvents = findings.tariff.n >= 20;
    const grossPositive = Number.isFinite(findings.tariff.avg) && findings.tariff.avg > 0;
    const netPositive = Number.isFinite(tariffPairAvg) && tariffPairAvg - cost > 0;
    const unseenPassed = Number.isFinite(findings.tariff.outOfSample) && findings.tariff.outOfSample > 0;
    const ready = enoughEvents && grossPositive && netPositive && unseenPassed;

    const row = (ok, label) => `<div class="readiness-item ${ok ? 'pass' : 'wait'}"><span>${ok ? '✓' : '•'}</span><strong>${label}</strong></div>`;
    box.innerHTML = `
      <div class="readiness-head">
        <div>
          <p class="eyebrow">MODEST-CAPITAL CHECK</p>
          <h3>${ready ? 'Research gates passed' : 'Research only for now'}</h3>
        </div>
        <span class="readiness-pill ${ready ? 'pass' : 'wait'}">${ready ? 'SIMULATION ELIGIBLE' : 'DO NOT USE FAMILY CAPITAL YET'}</span>
      </div>
      <p>Market Lab is being built to protect a small starting balance. Long-only ideas are the first candidates for eventual simulation; short selling and leverage stay research-only.</p>
      <div class="readiness-grid">
        ${row(enoughEvents, `At least 20 qualifying events (${findings.tariff.n} now)`)}
        ${row(grossPositive, 'Positive average historical result')}
        ${row(netPositive, `Positive after your entered cost of ${money(cost)}`)}
        ${row(unseenPassed, 'Positive test on later unseen data')}
      </div>
      <p class="readiness-note">This is a research gate, not a recommendation to invest. The app will keep showing gross and cost-adjusted historical examples before any real-money decision is considered.</p>`;
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
    const cost = tradingCost();
    const tariffPairAvg = Number.isFinite(findings.tariff.avg) ? (c / 2) * findings.tariff.avg : NaN;
    const tariffPairBest = Number.isFinite(findings.tariff.max) ? (c / 2) * findings.tariff.max : NaN;
    const tariffPairWorst = Number.isFinite(findings.tariff.min) ? (c / 2) * findings.tariff.min : NaN;
    const tariffPairNet = Number.isFinite(tariffPairAvg) ? tariffPairAvg - cost : NaN;
    const tariffRate = Number.isFinite(findings.tariff.avg) ? findings.tariff.avg / 2 : NaN;
    const tariffBreakEven = breakEvenCapital(tariffRate, cost);

    const energyLong = Number.isFinite(findings.energy.avgAsset) ? c * findings.energy.avgAsset : NaN;
    const energyLongNet = Number.isFinite(energyLong) ? energyLong - cost : NaN;
    const energyHedged = Number.isFinite(findings.energy.avgRelative) ? (c / 2) * findings.energy.avgRelative : NaN;
    const energyBreakEven = breakEvenCapital(findings.energy.avgAsset, cost);
    const timingPct = findings.timing.total ? Math.round(100 * findings.timing.unknown / findings.timing.total) : 0;

    status.innerHTML = '<strong>Current conclusion:</strong> nothing is ready for real-money use. Market Lab is expanding the history first, measuring costs explicitly, and keeping live trading outside the system.';

    renderReadiness(c, cost, tariffPairAvg);

    cards.innerHTML = `
      <article class="exec-card">
        <p class="eyebrow">TARIFF ESCALATION · 3 TRADING DAYS</p>
        <h3>Industrials long / technology short</h3>
        <p class="exec-lead">${Number.isFinite(tariffPairAvg) ? money(tariffPairAvg) : '—'}</p>
        <p>Average gross profit/loss using <strong>${money(c)}</strong> total exposure, split equally between industrials and technology.</p>
        <dl class="exec-stats">
          <div><dt>Events</dt><dd>${findings.tariff.n}</dd></div>
          <div><dt>Positive examples</dt><dd>${Number.isFinite(findings.tariff.winRate) ? `${Math.round(findings.tariff.winRate*100)}%` : '—'}</dd></div>
          <div><dt>Best observed</dt><dd>${Number.isFinite(tariffPairBest) ? money(tariffPairBest) : '—'}</dd></div>
          <div><dt>Worst observed</dt><dd>${Number.isFinite(tariffPairWorst) ? money(tariffPairWorst) : '—'}</dd></div>
          <div><dt>Net after entered cost</dt><dd>${Number.isFinite(tariffPairNet) ? money(tariffPairNet) : '—'}</dd></div>
          <div><dt>Break-even capital at average rate</dt><dd>${Number.isFinite(tariffBreakEven) ? money(tariffBreakEven) : 'No break-even at current average'}</dd></div>
        </dl>
        <p class="exec-verdict bad"><strong>Drop for now.</strong> The average result is not positive.</p>
      </article>

      <article class="exec-card">
        <p class="eyebrow">FORMAL ENERGY ACTION · 5 TRADING DAYS</p>
        <h3>Energy sector example</h3>
        <p class="exec-lead">${Number.isFinite(energyLong) ? money(energyLong) : '—'}</p>
        <p>Gross historical change from putting <strong>${money(c)}</strong> into the US energy-sector fund after qualifying formal energy actions.</p>
        <dl class="exec-stats">
          <div><dt>Formal actions measured</dt><dd>${findings.energy.n}</dd></div>
          <div><dt>Fund return</dt><dd>${Number.isFinite(findings.energy.avgAsset) ? percent(findings.energy.avgAsset) : '—'}</dd></div>
          <div><dt>Net after entered cost</dt><dd>${Number.isFinite(energyLongNet) ? money(energyLongNet) : '—'}</dd></div>
          <div><dt>Break-even capital at observed rate</dt><dd>${Number.isFinite(energyBreakEven) ? money(energyBreakEven) : (cost > 0 ? 'Not available' : 'Enter a cost to calculate')}</dd></div>
          <div><dt>${money(c/2)} long energy / ${money(c/2)} short broad market</dt><dd>${Number.isFinite(energyHedged) ? money(energyHedged) : '—'}</dd></div>
          <div><dt>Relative return</dt><dd>${Number.isFinite(findings.energy.avgRelative) ? percent(findings.energy.avgRelative) : '—'}</dd></div>
        </dl>
        <p class="exec-verdict warn"><strong>Keep watching.</strong> The sample is still too small for a money decision.</p>
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
      <article class="recommendation"><strong>1. No proven edge yet.</strong><p>Keep real money out until the research gates pass.</p></article>
      <article class="recommendation"><strong>2. Improve event timing.</strong><p>${findings.timing.unknown} of ${findings.timing.total} events (${timingPct}%) still have unknown trading time.</p></article>
      <article class="recommendation"><strong>3. Keep watching energy.</strong><p>The result is interesting, but the evidence is still thin.</p></article>
      <article class="recommendation"><strong>4. Enter your real trading costs.</strong><p>The A$ figures above will then show a more realistic net result.</p></article>`;
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
    document.getElementById('costInput')?.addEventListener('input', renderExecutive);
  }

  window.addEventListener('load', initialiseExecutive);
})();
