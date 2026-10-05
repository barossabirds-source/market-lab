const cfg = window.MARKET_LAB_CONFIG || {};
const state = { events: [], trials: [], syncRuns: [], connected: false, impactCache: new Map() };

const $ = (id) => document.getElementById(id);
const pct = (v) => v === null || v === undefined || Number.isNaN(Number(v)) ? '—' : `${(Number(v) * 100).toFixed(2)}%`;
const signedPct = (v) => {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—';
  const n = Number(v) * 100;
  return `${n > 0 ? '+' : ''}${n.toFixed(2)}%`;
};
const ppText = (v) => {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '—';
  const n = Number(v) * 100;
  return `${Math.abs(n).toFixed(2)} percentage points`;
};
const pretty = (s='') => s.replaceAll('_',' ').replace(/\b\w/g, c => c.toUpperCase());
const dateText = (value) => value ? new Date(`${String(value).slice(0,10)}T12:00:00Z`).toLocaleDateString('en-AU',{day:'numeric',month:'short',year:'numeric'}) : 'Unknown';
const tone = (v) => Number(v) > 0 ? 'pos' : Number(v) < 0 ? 'neg' : 'muted';
const escapeHtml = (s='') => String(s).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const shorten = (s='', max=108) => String(s).length <= max ? String(s) : `${String(s).slice(0,max-1).trim()}…`;

function timingLabel(value='unknown') {
  const v = String(value || 'unknown').toLowerCase();
  return ({ pre_market:'Before market opened', during_market:'During trading', after_hours:'After market closed', unknown:'Trading time unknown' })[v] || pretty(v);
}

function surpriseLabel(value='unknown') {
  const v = String(value || 'unknown').toLowerCase();
  return ({ high:'Highly unexpected', medium:'Moderately unexpected', low:'Low surprise', unknown:'Surprise unknown' })[v] || `${pretty(v)} surprise`;
}

function directionLabel(value='unknown') {
  const v = String(value || 'unknown').toLowerCase();
  return ({ deescalation:'De-escalation', escalation:'Escalation', sector_support:'Sector support', mixed:'Mixed', unknown:'Direction unknown' })[v] || pretty(v);
}

function qualityLabel(value='unknown') {
  const v = String(value || 'unknown').toLowerCase();
  return ({ daily_date_only:'Daily data · timing uncertain', daily_session_aligned:'Daily data · timing known' })[v] || pretty(v);
}

function evidenceStatus(trial) {
  const server = String(trial.status || '').toLowerCase();
  const mapped = {
    too_little_data:'Too little data',
    early_mixed:'Early / mixed',
    mixed_not_supported:'Mixed / not supported yet',
    some_support:'Some support',
    strong_repeated_support:'Strong repeated support',
    out_of_sample_passed:'Unseen-data test passed',
    simulation_eligible:'Eligible for simulated strategy testing',
  };
  if (mapped[server]) return mapped[server];

  const n = Number(trial.event_count || 0);
  const avg = Number(trial.average_effect);
  const hit = Number(trial.hit_rate);
  if (n < 5) return 'Too little data';
  if (Number.isFinite(avg) && avg <= 0) return 'Mixed / not supported yet';
  if (n < 12 || !Number.isFinite(hit) || hit < 0.60) return 'Early / mixed';
  if (n < 20 || hit < 0.65) return 'Some support';
  return 'Strong repeated support';
}

function trialResultText(trial) {
  const key = String(trial.trial_key || trial.id || '');
  const n = Number(trial.event_count || 0);
  const avg = trial.average_effect === null || trial.average_effect === undefined ? NaN : Number(trial.average_effect);
  const hit = trial.hit_rate === null || trial.hit_rate === undefined ? NaN : Number(trial.hit_rate);

  if (key.includes('tariff-industrials-vs-tech')) {
    if (!Number.isFinite(avg) || n === 0) return 'Not enough measured events yet.';
    const direction = avg >= 0 ? 'better' : 'worse';
    const support = avg > 0 && Number.isFinite(hit) && hit >= 0.60
      ? 'There is early support, but the sample is not yet large enough for a strategy conclusion.'
      : 'Current evidence is mixed and does not support the hypothesis yet.';
    return `Across ${n} qualifying events, industrial companies performed ${ppText(avg)} ${direction} than large technology companies on average over 3 trading days. Industrials performed better in ${Number.isFinite(hit) ? `${Math.round(hit*100)}%` : 'an unknown share'} of events. ${support}`;
  }

  if (key.includes('energy-formal-vs-remarks')) {
    if (!Number.isFinite(avg) || n === 0) return `Only ${n} usable energy events are available so far. Keep collecting data.`;
    const direction = avg >= 0 ? 'larger' : 'smaller';
    return `Only ${n} qualifying energy events are measurable so far. Formal energy actions show a ${ppText(avg)} ${direction} 5-day energy-sector response than energy remarks on average, but this is too little data to draw a conclusion.`;
  }

  if (key.includes('formal-action-dispersion')) {
    if (!Number.isFinite(avg) || n === 0) return `Only ${n} usable events are available so far. Keep collecting data.`;
    const direction = avg >= 0 ? 'more' : 'less';
    const conclusion = avg > 0 ? 'This is directionally consistent with the hypothesis, but repeated support and balanced comparison groups are still required.' : 'This currently runs against the hypothesis. Keep collecting data, especially remarks/interviews, before drawing a firm conclusion.';
    return `Across ${n} qualifying events, formal actions produced ${ppText(avg)} ${direction} one-day cross-market dispersion on average than remarks/interviews. ${conclusion}`;
  }

  return trial.result_summary || 'Not tested yet.';
}

function simulationGate(trial) {
  const n = Number(trial.event_count || 0);
  const avg = Number(trial.average_effect);
  const hit = Number(trial.hit_rate);
  const oos = trial.out_of_sample_effect === null || trial.out_of_sample_effect === undefined ? NaN : Number(trial.out_of_sample_effect);
  const repeated = n >= 20 && Number.isFinite(avg) && avg > 0 && Number.isFinite(hit) && hit >= 0.65;
  const unseenPassed = Number.isFinite(oos) && oos > 0;
  return {
    label: repeated && unseenPassed ? 'Simulation eligible' : 'Simulation locked',
    unseen: Number.isFinite(oos) ? (oos > 0 ? 'Unseen-data test passed' : 'Unseen-data test did not hold') : 'Unseen-data test not run',
  };
}

async function supabaseGet(table, query='') {
  const response = await fetch(`${cfg.supabaseUrl}/rest/v1/${table}?${query}`, { headers: { apikey: cfg.supabasePublishableKey } });
  if (!response.ok) throw new Error(`${table}: ${response.status}`);
  return response.json();
}

function parseCsv(text) {
  const rows=[]; let row=[], field='', quoted=false;
  for (let i=0;i<text.length;i++) {
    const c=text[i], n=text[i+1];
    if (quoted && c==='"' && n==='"') { field+='"'; i++; continue; }
    if (c==='"') { quoted=!quoted; continue; }
    if (!quoted && c===',') { row.push(field); field=''; continue; }
    if (!quoted && (c==='\n' || c==='\r')) {
      if (c==='\r' && n==='\n') i++;
      row.push(field); field=''; if (row.some(x=>x!=='')) rows.push(row); row=[]; continue;
    }
    field+=c;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  if (!rows.length) return [];
  const headers=rows[0].map(h=>h.trim());
  return rows.slice(1).map(r=>Object.fromEntries(headers.map((h,i)=>[h,r[i] ?? ''])));
}

async function loadCsvEvents() {
  const files=['/data/trump_events.csv','/data/trump_events_additions.csv'];
  const chunks=[];
  for (const path of files) {
    try { const r=await fetch(path); if(r.ok) chunks.push(...parseCsv(await r.text())); } catch (_) {}
  }
  return chunks.map((e,i)=>({
    id:`csv-${i}-${e.date}-${e.theme}`,
    event_date:e.date,
    event_type:e.event_type,
    source_type:e.source_type,
    policy_theme:e.theme,
    direction:e.direction,
    surprise_level:e.surprise_proxy,
    surprise_basis:e.surprise_basis,
    market_session:e.market_session,
    timing_confidence:e.timing_confidence,
    summary:e.summary,
    source_url:e.source,
    source_name:e.source?.includes('whitehouse.gov')?'White House':'Source',
    candidate_symbols:(e.etfs||'').split(';').filter(Boolean),
  }));
}

async function loadData() {
  const canConnect=Boolean(cfg.supabaseUrl && cfg.supabasePublishableKey);
  if (canConnect) {
    try {
      const [events,trials,syncRuns]=await Promise.all([
        supabaseGet('events','select=*&order=event_date.desc&limit=250'),
        supabaseGet('research_trials','select=*&order=registered_at.desc&limit=100'),
        supabaseGet('sync_runs','select=*&order=started_at.desc&limit=5'),
      ]);
      state.events=events; state.trials=trials; state.syncRuns=syncRuns; state.connected=true;
    } catch (err) {
      console.warn('Supabase unavailable; using repository event ledger.', err);
    }
  }
  if (!state.events.length) state.events=await loadCsvEvents();
  if (!state.trials.length) state.trials=defaultTrials();
  render();
}

function defaultTrials() {
  return [
    {id:'trial-1',status:'too_little_data',hypothesis:'High-surprise tariff escalations are followed by stronger 3-day relative performance in US industrial companies than in large technology companies.',policy_theme:'tariffs',horizon:'3d',test_method:'Compare XLI and QQQ after pre-registered qualifying events; report event count, average difference and consistency before any simulated rule is considered.',result_summary:'Awaiting sufficient measured events.'},
    {id:'trial-2',status:'too_little_data',hypothesis:'Formal energy-support actions produce a larger 5-day energy-sector reaction than public remarks about energy.',policy_theme:'energy',horizon:'5d',test_method:'Compare XLE relative moves for formal actions versus remarks. Keep event classification frozen before outcomes are inspected.',result_summary:'Awaiting sufficient measured events.'},
    {id:'trial-3',status:'too_little_data',hypothesis:'Formal policy actions create greater one-day sector dispersion than routine public remarks.',policy_theme:'all',horizon:'1d',test_method:'For each event, calculate the spread between the strongest and weakest sector response, then compare formal actions with remarks.',result_summary:'Awaiting sufficient measured events.'},
  ];
}

function render() {
  $('connectionStatus').textContent=state.connected?'Supabase data connected':'Repository ledger mode';
  $('metricEvents').textContent=state.events.length.toLocaleString();
  $('metricThemes').textContent=new Set(state.events.map(e=>e.policy_theme).filter(Boolean)).size;
  $('metricImpacts').textContent=state.syncRuns[0]?.impacts_written?.toLocaleString?.() || (state.connected ? '—' : '0');
  $('metricSync').textContent=state.syncRuns[0]?.finished_at ? dateText(state.syncRuns[0].finished_at) : 'Not synced yet';
  $('dataMessage').innerHTML=state.connected
    ? 'Market Lab is reading the persistent research ledger and measured market reactions from Supabase.'
    : '<strong>The event ledger is working from the repository.</strong> Add the Supabase URL and publishable key in Netlify to turn on persistent reaction data and the full Policy Impact Map.';
  buildFilters(); renderLedger(); renderImpact(); renderTrials();
}

function buildFilters() {
  const current=$('eventSelect').value;
  $('eventSelect').innerHTML=state.events.map(e=>`<option value="${escapeHtml(e.id)}">${escapeHtml(dateText(e.event_date))} · ${escapeHtml(shorten(e.summary))}</option>`).join('');
  if (current && state.events.some(e=>String(e.id)===current)) $('eventSelect').value=current;
  const themes=[...new Set(state.events.map(e=>e.policy_theme).filter(Boolean))].sort();
  $('themeFilter').innerHTML='<option value="">All themes</option>'+themes.map(t=>`<option value="${escapeHtml(t)}">${escapeHtml(pretty(t))}</option>`).join('');
}

function renderLedger() {
  const q=$('ledgerSearch').value.trim().toLowerCase(), theme=$('themeFilter').value;
  const rows=state.events.filter(e=>{
    const hay=`${e.summary} ${e.policy_theme} ${e.direction} ${e.source_type}`.toLowerCase();
    return (!q || hay.includes(q)) && (!theme || e.policy_theme===theme);
  }).slice(0,150);
  $('ledgerRows').innerHTML=rows.map(e=>`<tr>
    <td>${escapeHtml(dateText(e.event_date))}</td><td>${escapeHtml(pretty(e.policy_theme||''))}</td>
    <td>${escapeHtml(e.summary||'')}</td><td>${escapeHtml(pretty(e.source_type||''))}</td>
    <td>${escapeHtml(directionLabel(e.direction))}</td><td>${escapeHtml(surpriseLabel(e.surprise_level))}</td>
    <td>${escapeHtml(timingLabel(e.market_session))}<div class="muted">${escapeHtml(pretty(e.timing_confidence||'low'))} confidence</div></td>
    <td>${e.source_url?`<a class="source-link" href="${escapeHtml(e.source_url)}" target="_blank" rel="noopener">Open source</a>`:'—'}</td>
  </tr>`).join('') || '<tr><td colspan="8">No matching events.</td></tr>';
}

async function renderImpact() {
  const event=state.events.find(e=>String(e.id)===$('eventSelect').value) || state.events[0];
  if (!event) return;
  const timingWarning = String(event.market_session || 'unknown').toLowerCase() === 'unknown'
    ? '<div class="callout"><strong>Timing uncertain:</strong> the exact announcement time is not known, so the one-day reaction may include market movement that happened before the announcement.</div>'
    : '';
  $('eventCard').innerHTML=`<h3>${escapeHtml(event.summary||'')}</h3><p>${escapeHtml(dateText(event.event_date))} · ${escapeHtml(pretty(event.policy_theme||''))}</p>
    <div class="badges"><span class="badge">${escapeHtml(pretty(event.source_type||''))}</span><span class="badge">${escapeHtml(directionLabel(event.direction))}</span><span class="badge">${escapeHtml(surpriseLabel(event.surprise_level))}</span><span class="badge">${escapeHtml(timingLabel(event.market_session))}</span></div>${timingWarning}`;
  const horizon=$('horizonSelect').value;
  const cacheKey=`${event.id}|${horizon}`;
  let rows=state.impactCache.get(cacheKey) || [];
  if (state.connected && !state.impactCache.has(cacheKey)) {
    $('impactRows').innerHTML='<tr><td colspan="8">Loading measured reactions…</td></tr>';
    try {
      rows=await supabaseGet('event_impacts',`select=*&event_id=eq.${encodeURIComponent(event.id)}&horizon=eq.${encodeURIComponent(horizon)}&limit=100`);
      state.impactCache.set(cacheKey,rows);
    } catch (err) {
      console.warn('Could not load event impacts',err);
      rows=[];
    }
  }
  rows=[...rows].sort((a,b)=>{
    const av = a.reaction_vs_pre === null || a.reaction_vs_pre === undefined ? -Infinity : Number(a.reaction_vs_pre);
    const bv = b.reaction_vs_pre === null || b.reaction_vs_pre === undefined ? -Infinity : Number(b.reaction_vs_pre);
    return bv-av;
  });
  if (!rows.length) {
    $('impactRows').innerHTML='<tr><td colspan="8">No measured reaction is stored for this event and period yet.</td></tr>';
    $('impactSummary').textContent=state.connected?'The event is recorded, but this reaction has not been calculated yet.':'Connect Supabase and run the daily sync to calculate reactions across the market universe.';
    return;
  }
  const comparable=rows.filter(x=>x.reaction_vs_pre !== null && x.reaction_vs_pre !== undefined && !Number.isNaN(Number(x.reaction_vs_pre)));
  const hi=comparable[0] || rows[0], lo=comparable[comparable.length-1] || rows[rows.length-1];
  const spread=Number(hi.reaction_vs_pre)-Number(lo.reaction_vs_pre);
  $('impactSummary').innerHTML=`Compared with how they had been moving before the event, <strong>${escapeHtml(hi.asset_name||hi.symbol)}</strong> improved most relative to the broad US market and <strong>${escapeHtml(lo.asset_name||lo.symbol)}</strong> weakened most. The difference between them was <strong>${ppText(spread)}</strong>. This describes the observed pattern only; it does not establish causation.`;
  $('impactRows').innerHTML=rows.map(x=>`<tr>
    <td>${escapeHtml(x.asset_group||'')}</td><td><strong>${escapeHtml(x.asset_name||x.symbol)}</strong><div class="muted">${escapeHtml(x.symbol)}</div></td>
    <td class="num ${tone(x.asset_return)}">${signedPct(x.asset_return)}</td><td class="num ${tone(x.benchmark_return)}">${signedPct(x.benchmark_return)}</td>
    <td class="num ${tone(x.abnormal_return)}">${signedPct(x.abnormal_return)}</td><td class="num ${tone(x.pre_event_abnormal_return)}">${signedPct(x.pre_event_abnormal_return)}</td>
    <td class="num ${tone(x.reaction_vs_pre)}">${signedPct(x.reaction_vs_pre)}</td><td>${escapeHtml(qualityLabel(x.data_quality))}${x.is_candidate?'<div class="muted">Identified as potentially affected before results were measured</div>':''}</td>
  </tr>`).join('');
}

function renderTrials() {
  $('trialCards').innerHTML=state.trials.map(t=>{
    const evidence=evidenceStatus(t);
    const gate=simulationGate(t);
    const theme=t.policy_theme && t.policy_theme !== 'all' ? pretty(t.policy_theme) : 'All policy themes';
    const n=Number(t.event_count || 0);
    return `<article class="trial">
      <p class="eyebrow">${escapeHtml((t.horizon||'').toUpperCase())} · ${escapeHtml(theme)}</p>
      <div class="badges"><span class="badge">Evidence: ${escapeHtml(evidence)}</span><span class="badge">${escapeHtml(gate.unseen)}</span><span class="badge">${escapeHtml(gate.label)}</span></div>
      <h3>${escapeHtml(t.hypothesis||'')}</h3><p>${escapeHtml(t.test_method||'')}</p>
      <p class="result"><strong>Current result:</strong> ${escapeHtml(trialResultText(t))}</p>
      <p class="muted">Qualifying events measured: ${Number.isFinite(n) ? n : 0}. A trial cannot reach simulated strategy testing until it has repeated support across at least 20 events and then passes an unseen-data test.</p>
    </article>`;
  }).join('');
}

$('eventSelect').addEventListener('change',renderImpact);
$('horizonSelect').addEventListener('change',renderImpact);
$('ledgerSearch').addEventListener('input',renderLedger);
$('themeFilter').addEventListener('change',renderLedger);
loadData();
