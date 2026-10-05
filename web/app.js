const cfg = window.MARKET_LAB_CONFIG || {};
const state = { events: [], trials: [], syncRuns: [], connected: false, impactCache: new Map() };

const $ = (id) => document.getElementById(id);
const pct = (v) => v === null || v === undefined || Number.isNaN(Number(v)) ? '—' : `${(Number(v) * 100).toFixed(2)}%`;
const pretty = (s='') => s.replaceAll('_',' ').replace(/\b\w/g, c => c.toUpperCase());
const dateText = (value) => value ? new Date(`${String(value).slice(0,10)}T12:00:00Z`).toLocaleDateString('en-AU',{day:'numeric',month:'short',year:'numeric'}) : 'Unknown';
const tone = (v) => Number(v) > 0 ? 'pos' : Number(v) < 0 ? 'neg' : 'muted';
const escapeHtml = (s='') => String(s).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));

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
    {id:'trial-1',status:'registered',hypothesis:'High-surprise tariff escalations are followed by stronger 3-day relative performance in US industrial companies than in large technology companies.',policy_theme:'tariffs',horizon:'3d',test_method:'Compare XLI and QQQ after pre-registered qualifying events; report event count, average difference and consistency before any simulated rule is considered.',result_summary:'Awaiting sufficient measured events.'},
    {id:'trial-2',status:'registered',hypothesis:'Formal energy-support actions produce a larger 5-day energy-sector reaction than public remarks about energy.',policy_theme:'energy',horizon:'5d',test_method:'Compare XLE relative moves for formal actions versus remarks. Keep event classification frozen before outcomes are inspected.',result_summary:'Awaiting sufficient measured events.'},
    {id:'trial-3',status:'registered',hypothesis:'Formal policy actions create greater one-day sector dispersion than routine public remarks.',policy_theme:'all',horizon:'1d',test_method:'For each event, calculate the spread between the strongest and weakest sector response, then compare formal actions with remarks.',result_summary:'Awaiting sufficient measured events.'},
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
  $('eventSelect').innerHTML=state.events.map(e=>`<option value="${escapeHtml(e.id)}">${escapeHtml(dateText(e.event_date))} · ${escapeHtml(e.summary)}</option>`).join('');
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
    <td>${escapeHtml(pretty(e.direction||''))}</td><td>${escapeHtml(pretty(e.surprise_level||''))}</td>
    <td>${escapeHtml(pretty(e.market_session||'unknown'))}<div class="muted">${escapeHtml(pretty(e.timing_confidence||'low'))} confidence</div></td>
    <td>${e.source_url?`<a class="source-link" href="${escapeHtml(e.source_url)}" target="_blank" rel="noopener">Open source</a>`:'—'}</td>
  </tr>`).join('') || '<tr><td colspan="8">No matching events.</td></tr>';
}

async function renderImpact() {
  const event=state.events.find(e=>String(e.id)===$('eventSelect').value) || state.events[0];
  if (!event) return;
  $('eventCard').innerHTML=`<h3>${escapeHtml(event.summary||'')}</h3><p>${escapeHtml(dateText(event.event_date))} · ${escapeHtml(pretty(event.policy_theme||''))}</p>
    <div class="badges"><span class="badge">${escapeHtml(pretty(event.source_type||''))}</span><span class="badge">${escapeHtml(pretty(event.direction||''))}</span><span class="badge">${escapeHtml(pretty(event.surprise_level||''))} surprise</span><span class="badge">${escapeHtml(pretty(event.market_session||'unknown'))}</span></div>`;
  const horizon=$('horizonSelect').value;
  const cacheKey=`${event.id}|${horizon}`;
  let rows=state.impactCache.get(cacheKey) || [];
  if (state.connected && !state.impactCache.has(cacheKey)) {
    $('impactRows').innerHTML='<tr><td colspan="8">Loading measured reactions…</td></tr>';
    try {
      rows=await supabaseGet('event_impacts',`select=*&event_id=eq.${encodeURIComponent(event.id)}&horizon=eq.${encodeURIComponent(horizon)}&order=abnormal_return.desc.nullslast&limit=100`);
      state.impactCache.set(cacheKey,rows);
    } catch (err) {
      console.warn('Could not load event impacts',err);
      rows=[];
    }
  }
  rows=[...rows].sort((a,b)=>Number(b.abnormal_return)-Number(a.abnormal_return));
  if (!rows.length) {
    $('impactRows').innerHTML='<tr><td colspan="8">No measured reaction is stored for this event and period yet.</td></tr>';
    $('impactSummary').textContent=state.connected?'The event is recorded, but this reaction has not been calculated yet.':'Connect Supabase and run the daily sync to calculate reactions across the market universe.';
    return;
  }
  const hi=rows[0], lo=rows[rows.length-1], spread=Number(hi.abnormal_return)-Number(lo.abnormal_return);
  $('impactSummary').innerHTML=`The strongest relative response was <strong>${escapeHtml(hi.asset_name||hi.symbol)}</strong> and the weakest was <strong>${escapeHtml(lo.asset_name||lo.symbol)}</strong>. The cross-market spread was <strong>${pct(spread)}</strong>. This describes the observed pattern only; it does not establish causation.`;
  $('impactRows').innerHTML=rows.map(x=>`<tr>
    <td>${escapeHtml(x.asset_group||'')}</td><td><strong>${escapeHtml(x.asset_name||x.symbol)}</strong><div class="muted">${escapeHtml(x.symbol)}</div></td>
    <td class="num ${tone(x.asset_return)}">${pct(x.asset_return)}</td><td class="num ${tone(x.benchmark_return)}">${pct(x.benchmark_return)}</td>
    <td class="num ${tone(x.abnormal_return)}">${pct(x.abnormal_return)}</td><td class="num ${tone(x.pre_event_abnormal_return)}">${pct(x.pre_event_abnormal_return)}</td>
    <td class="num ${tone(x.reaction_vs_pre)}">${pct(x.reaction_vs_pre)}</td><td>${escapeHtml(pretty(x.data_quality||'unknown'))}${x.is_candidate?'<div class="muted">Pre-event candidate</div>':''}</td>
  </tr>`).join('');
}

function renderTrials() {
  $('trialCards').innerHTML=state.trials.map(t=>`<article class="trial"><p class="eyebrow">${escapeHtml(pretty(t.status||'registered'))} · ${escapeHtml((t.horizon||'').toUpperCase())}</p><h3>${escapeHtml(t.hypothesis||'')}</h3><p>${escapeHtml(t.test_method||'')}</p><p class="result"><strong>Current result:</strong> ${escapeHtml(t.result_summary||'Not tested yet.')}</p></article>`).join('');
}

$('eventSelect').addEventListener('change',renderImpact);
$('horizonSelect').addEventListener('change',renderImpact);
$('ledgerSearch').addEventListener('input',renderLedger);
$('themeFilter').addEventListener('change',renderLedger);
loadData();
