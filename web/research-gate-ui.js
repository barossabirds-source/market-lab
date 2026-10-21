(function () {
  'use strict';
  const form = document.getElementById('researchGateForm');
  const result = document.getElementById('researchGateResult');
  if (!form || !result || !window.MarketLabResearchGate) return;
  form.addEventListener('submit', event => {
    event.preventDefault();
    const data = new FormData(form);
    const raw = String(data.get('returns') || '').trim().split(/[\s,;]+/);
    const returns = raw.length && raw[0] !== '' ? raw.map(Number) : [];
    const checked = name => data.get(name) === 'on';
    const output = window.MarketLabResearchGate.evaluate({
      returns, costBps: Number(data.get('costBps')), freezeDate: data.get('freezeDate'),
      firstDate: data.get('firstDate'), provenance: data.get('provenance'),
      pointInTime: checked('pointInTime'), noSignalSessions: checked('noSignalSessions'),
      oosCount: Number(data.get('oosCount'))
    });
    const labels = {insufficient_evidence:'Insufficient evidence',not_promising:'Not promising',research_candidate:'Research candidate only'};
    result.replaceChildren();
    const heading = document.createElement('strong');
    heading.textContent = labels[output.status];
    const message = document.createElement('p');
    message.textContent = output.reasons.join('; ');
    result.append(heading,message);
    if (Number.isFinite(output.meanNet)) {
      const metric = document.createElement('p');
      metric.textContent = 'Mean net return: ' + (output.meanNet*100).toFixed(3) + '% | Net win rate: ' + (output.winRate*100).toFixed(1) + '%';
      result.append(metric);
    }
  });
})();
