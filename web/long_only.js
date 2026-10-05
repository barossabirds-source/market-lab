(() => {
  const money = (value) => new Intl.NumberFormat('en-AU', {
    style: 'currency', currency: 'AUD', minimumFractionDigits: 2, maximumFractionDigits: 2,
  }).format(Number(value) || 0);
  const percent = (value) => `${Number(value) >= 0 ? '+' : ''}${(Number(value) * 100).toFixed(2)}%`;

  const RULES = [
    {
      key: 'china-deescalation-semiconductors-5d-future',
      title: 'China trade de-escalation',
      trigger: 'A qualifying China-trade de-escalation event',
      symbol: 'SOXX',
      asset: 'Semiconductor fund',
      hold: '5 trading days',
      n: 8,
      avg: 0.022432777534689903,
      hit: 0.875,
      worst: -0.07042330039405942,
      best: 0.09894803979606692,
      evidence: 'Seen in both Trump terms. Historical discovery only.',
    },
    {
      key: 'metals-escalation-materials-5d-future',
      title: 'Metals tariff escalation',
      trigger: 'A qualifying escalation in steel, aluminium or related metals tariffs',
      symbol: 'XLB',
      asset: 'US materials-sector fund',
      hold: '5 trading days',
      n: 5,
      avg: 0.018992804772460614,
      hit: 0.80,
      worst: -0.00016603971579431942,
      best: 0.03920238073754545,
      evidence: 'Positive average in both Trump terms. Historical discovery only.',
    },
    {
      key: 'defense-support-defense-5d-future',
      title: 'Formal defence-support action',
      trigger: 'A qualifying formal US defence-support policy action',
      symbol: 'ITA',
      asset: 'US aerospace and defence fund',
      hold: '5 trading days',
      n: 7,
      avg: 0.03239044269831483,
      hit: 5 / 7,
      worst: -0.04014520724896942,
      best: 0.09395926986102365,
      evidence: 'Current discovery sample is second-term only, so regime evidence is weaker.',
    },
  ];

  function capital() {
    const n = Number(document.getElementById('capitalInput')?.value || 2000);
    return Number.isFinite(n) && n > 0 ? n : 2000;
  }

  function cost() {
    const n = Number(document.getElementById('costInput')?.value || 0);
    return Number.isFinite(n) && n >= 0 ? n : 0;
  }

  function futureTrial(key) {
    return (state.trials || []).find(t => String(t.trial_key || '') === key) || null;
  }

  function futureStatus(trial) {
    const n = Number(trial?.event_count || 0);
    const avg = trial?.average_effect === null || trial?.average_effect === undefined ? NaN : Number(trial.average_effect);
    const hit = trial?.hit_rate === null || trial?.hit_rate === undefined ? NaN : Number(trial.hit_rate);
    if (n < 5) return { cls: 'waiting', label: `Collecting unseen events · ${n}/5 minimum` };
    if (Number.isFinite(avg) && Number.isFinite(hit) && avg > 0 && hit >= 0.60) {
      return { cls: 'support', label: 'Early future support · simulation review only' };
    }
    return { cls: 'fail', label: 'Future test is not supporting this rule' };
  }

  function renderLongOnly() {
    const root = document.getElementById('longOnlyCandidates');
    const intro = document.getElementById('longOnlyIntro');
    if (!root || !intro) return;

    const c = capital();
    const tradeCost = cost();
    const costWarning = tradeCost === 0
      ? ' Trading cost is currently set to A$0, so the net figures below are still optimistic.'
      : ` The figures subtract ${money(tradeCost)} per completed example.`;

    intro.innerHTML = `<strong>Frozen on 5 Oct 2026:</strong> these three rules were selected from historical discovery, then locked. They are now judged only on new events. The starting amount is <strong>${money(c)}</strong>.${costWarning}`;

    root.innerHTML = RULES.map(rule => {
      const trial = futureTrial(rule.key);
      const status = futureStatus(trial);
      const historicalGross = c * rule.avg;
      const historicalNet = historicalGross - tradeCost;
      const worstNet = c * rule.worst - tradeCost;
      const bestNet = c * rule.best - tradeCost;
      const futureN = Number(trial?.event_count || 0);
      const futureAvg = trial?.average_effect === null || trial?.average_effect === undefined ? NaN : Number(trial.average_effect);
      const futureHit = trial?.hit_rate === null || trial?.hit_rate === undefined ? NaN : Number(trial.hit_rate);
      const futureNet = Number.isFinite(futureAvg) ? c * futureAvg - tradeCost : NaN;

      return `<article class="long-card">
        <div class="long-card-top">
          <div>
            <p class="eyebrow">FROZEN LONG-ONLY RULE</p>
            <h3>${escapeHtml(rule.title)}</h3>
          </div>
          <span class="long-status ${status.cls}">${escapeHtml(status.label)}</span>
        </div>
        <p><strong>Trigger:</strong> ${escapeHtml(rule.trigger)}.</p>
        <p><strong>Action being tested:</strong> buy ${escapeHtml(rule.asset)} (${escapeHtml(rule.symbol)}) and hold for ${escapeHtml(rule.hold)}.</p>
        <div class="long-money">
          <div><span>Historical average on ${money(c)}</span><strong>${money(historicalGross)}</strong></div>
          <div><span>After entered cost</span><strong class="${historicalNet >= 0 ? 'pos' : 'neg'}">${money(historicalNet)}</strong></div>
        </div>
        <dl class="long-stats">
          <div><dt>Historical events</dt><dd>${rule.n}</dd></div>
          <div><dt>Historically positive</dt><dd>${Math.round(rule.hit * 100)}%</dd></div>
          <div><dt>Worst historical ${money(c)} result</dt><dd class="${worstNet >= 0 ? 'pos' : 'neg'}">${money(worstNet)}</dd></div>
          <div><dt>Best historical ${money(c)} result</dt><dd class="${bestNet >= 0 ? 'pos' : 'neg'}">${money(bestNet)}</dd></div>
          <div><dt>Future unseen events</dt><dd>${futureN}</dd></div>
          <div><dt>Future average after cost</dt><dd>${Number.isFinite(futureNet) ? money(futureNet) : 'Waiting'}</dd></div>
          <div><dt>Future positive rate</dt><dd>${Number.isFinite(futureHit) ? `${Math.round(futureHit * 100)}%` : 'Waiting'}</dd></div>
        </dl>
        <p class="long-note">${escapeHtml(rule.evidence)}</p>
        <p class="long-gate"><strong>Gate:</strong> no family-capital use from this dashboard. First review point is 5 unseen events with a positive average after costs and at least 60% positive outcomes. A stronger review requires 10 unseen events.</p>
      </article>`;
    }).join('');
  }

  async function initialiseLongOnly() {
    const root = document.getElementById('longOnlyCandidates');
    if (!root) return;
    for (let i = 0; i < 60 && !(state.trials || []).length; i++) {
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    renderLongOnly();
    document.getElementById('capitalInput')?.addEventListener('input', renderLongOnly);
    document.getElementById('costInput')?.addEventListener('input', renderLongOnly);
  }

  window.addEventListener('load', initialiseLongOnly);
})();
