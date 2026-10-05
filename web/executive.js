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

    const [pairRows, energyRows, oneDayRows, semiRows] = await Promise.all([
      supabaseGet('event_impacts', 'select=event_id,symbol,asset_return,benchmark_return,abnormal_return&horizon=eq.3d&symbol=in.(XLI,QQQ)&limit=500'),
      supabaseGet('event_impacts', 'select=event_id,symbol,asset_return,benchmark_return,abnormal_return&horizon=eq.5d&symbol=eq.XLE&limit=200'),
      supabaseGet('event_impacts', 'select=event_id,symbol,abnormal_return&horizon=eq.1d&symbol=neq.SPY&limit=1600'),
      supabaseGet('event_impacts', 'select=event_id,symbol,asset_return&horizon=eq.5d&symbol=eq.SOXX&limit=200'),
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

    const semiDiscovery = semiRows.filter(row => {
      const event = events.get(String(row.event_id));
      return event && String(event.policy_theme || '').toLowerCase() === 'china_trade' && String(event.direction || '').toLowerCase() === 'deescalation';
    });
    const semiReturns = semiDiscovery.map(x => Number(x.asset_return)).filter(Number.isFinite);
    const semiFutureTrial = (state.trials || []).find(t => String(t.trial_key || '') === 'china-deescalation-semiconductors-5d-future');
    const semiFutureAvg = semiFutureTrial?.average_effect === null || semiFutureTrial?.average_effect === undefined ? NaN : Number(semiFutureTrial.average_effect);
    const semiFutureN = Number(semiFutureTrial?.event_count || 0);

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
      semiLead: {
        n: semiReturns.length,
        avg: mean(semiReturns),
        min: min(semiReturns),
        max: max(semiReturns),
        winRate: semiReturns.length ? semiReturns.filter(x => x > 0).length / semiReturns.length : NaN,
        futureN: semiFutureN,
        futureAvg: semiFutureAvg,
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

  function renderReadiness(c, cost) {
    const box = document.getElementById('capitalReadiness');
    if (!box || !findings) return;

    const lead = findings.semiLead;
    const historicalNet = Number.isFinite(lead.avg) ? c * lead.avg - cost : NaN;
    const futureNet = Number.isFinite(lead.futureAvg) ? c * lead.futureAvg - cost : NaN;
    const enoughTotal = (lead.n + lead.futureN) >= 20;
    const historicalPositive = Number.isFinite(historicalNet) && historicalNet > 0;
    const enoughFuture = lead.futureN >= 5;
    const futurePositive = Number.isFinite(futureNet) && futureNet > 0;
    const ready = enoughTotal && historicalPositive && enoughFuture && futurePositive;

    const row = (ok, label) => `<div class="readiness-item ${ok ? 'pass' : 'wait'}"><span>${ok ? '✓' : '•'}</span><strong>${label}</strong></div>`;
    box.innerHTML = `
      <div class="readiness-head">
        <div>
          <p class="eyebrow">MODEST-CAPITAL CHECK</p>
          <h3>${ready ? 'Research gates passed' : 'Research only for now'}</h3>
        </div>
        <span class="readiness-pill ${ready ? 'pass' : 'wait'}">${ready ? 'SIMULATION ELIGIBLE' : 'DO NOT USE FAMILY CAPITAL YET'}</span>
      </div>
      <p>The long-only semiconductor lead is the first candidate being tracked for a modest starting balance. It was discovered from old data, so it must prove itself on future events before it can be treated seriously.</p>
      <div class="readiness-grid">
        ${row(enoughTotal, `At least 20 total qualifying events (${lead.n + lead.futureN} now)`)}
        ${row(historicalPositive, `Historical average remains positive after ${money(cost)} entered cost`)}
        ${row(enoughFuture, `At least 5 future unseen events (${lead.futureN} now)`)}
        ${row(futurePositive, 'Future unseen average is positive after entered cost')}
      </div>
      <p class="readiness-note">This is a research gate, not a recommendation to invest. Long-only ideas are prioritised; short selling and leverage remain research-only.</p>`;
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

    const semiGross = Number.isFinite(findings.semiLead.avg) ? c * findings.semiLead.avg : NaN;
    const semiNet = Number.isFinite(semiGross) ? semiGross - cost : NaN;
    const semiBest = Number.isFinite(findings.semiLead.max) ? c * findings.semiLead.max : NaN;
    const semiWorst = Number.isFinite(findings.semiLead.min) ? c * findings.semiLead.min : NaN;
    const semiBreakEven = breakEvenCapital(findings.semiLead.avg, cost);

    const timingPct = findings.timing.total ? Math.round(100 * findings.timing.unknown / findings.timing.total) : 0;

    status.innerHTML = '<strong>Current conclusion:</strong> nothing is ready for real-money use. The historical backfill has identified one long-only research lead worth freezing and testing on future events, while the tariff pair remains unattractive.';

    renderReadiness(c, cost);

    cards.innerHTML = `
      <article class="exec-card">
        <p class="eyebrow">LONG-ONLY RESEARCH LEAD · 5 TRADING DAYS</p>
        <h3>China trade de-escalation → semiconductors</h3>
        <p class="exec-lead">${Number.isFinite(semiGross) ? money(semiGross) : '—'}</p>
        <p>Historical discovery average from putting <strong>${money(c)}</strong> into SOXX after qualifying China-trade de-escalation events. This pattern was found by looking backwards, so it is not proof.</p>
        <dl class="exec-stats">
          <div><dt>Historical discovery events</dt><dd>${findings.semiLead.n}</dd></div>
          <div><dt>Positive historical examples</dt><dd>${Number.isFinite(findings.semiLead.winRate) ? `${Math.round(findings.semiLead.winRate*100)}%` : '—'}</dd></div>
          <div><dt>Net after entered cost</dt><dd>${Number.isFinite(semiNet) ? money(semiNet) : '—'}</dd></div>
          <div><dt>Break-even capital at historical average</dt><dd>${Number.isFinite(semiBreakEven) ? money(semiBreakEven) : (cost > 0 ? 'Not available' : 'Enter a cost to calculate')}</dd></div>
          <div><dt>Best historical example</dt><dd>${Number.isFinite(semiBest) ? money(semiBest) : '—'}</dd></div>
          <div><dt>Worst historical example</dt><dd>${Number.isFinite(semiWorst) ? money(semiWorst) : '—'}</dd></div>
          <div><dt>Future unseen events measured</dt><dd>${findings.semiLead.futureN}</dd></div>
          <div><dt>Future unseen average</dt><dd>${Number.isFinite(findings.semiLead.futureAvg) ? percent(findings.semiLead.futureAvg) : 'Waiting'}</dd></div>
        </dl>
        <p class="exec-verdict warn"><strong>Watch only.</strong> The rule is now frozen. Future events, not the old data, will decide whether it survives.</p>
      </article>

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
      <article class="recommendation"><strong>1. Test the long-only lead on new events.</strong><p>Do not count the historical discovery sample as confirmation.</p></article>
      <article class="recommendation"><strong>2. Keep real money out for now.</strong><p>The future-validation count is still ${findings.semiLead.futureN}.</p></article>
      <article class="recommendation"><strong>3. Improve event timing.</strong><p>${findings.timing.unknown} of ${findings.timing.total} events (${timingPct}%) still have unknown trading time.</p></article>
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
