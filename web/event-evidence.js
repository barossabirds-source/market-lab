(async function () {
  'use strict';
  const host = document.getElementById('eventEvidence');
  const config = window.MARKET_LAB_CONFIG || {};
  const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money = v => v == null ? '—' : Number(v).toLocaleString('en-AU', {style:'currency',currency:'AUD'});
  const pct = v => v == null ? '—' : `${(Number(v)*100).toFixed(1)}%`;
  const date = v => v ? new Date(v).toLocaleString('en-AU',{timeZone:'Australia/Adelaide'}) : 'Not captured before entry';
  const key = 'wall-street-up-asx-v1';
  async function read(table, query) {
    const response = await fetch(`${config.supabaseUrl}/rest/v1/${table}?${query}`, {headers:{apikey:config.supabasePublishableKey}});
    if (!response.ok) throw Error('Evidence request failed');
    return response.json();
  }
  async function all(table, query) {
    const rows = [];
    for (let offset=0;;offset+=500) {
      const page = await read(table, `${query}&limit=500&offset=${offset}`);
      rows.push(...page);
      if (page.length < 500) return rows;
    }
  }
  if (!config.supabaseUrl || !config.supabasePublishableKey) {
    host.textContent = 'Event evidence is unavailable: the database connection is not configured.';
    return;
  }
  try {
    const [rules, health, outcomes, predictions] = await Promise.all([
      read('event_hypotheses',`select=*&hypothesis_key=eq.${key}`),
      read('asx_feed_status','select=*&feed_key=eq.event_evidence'),
      all('event_outcomes',`select=*&hypothesis_key=eq.${key}&order=session_date.desc`),
      all('event_predictions',`select=*&hypothesis_key=eq.${key}&order=event_key`)
    ]);
    const rule = rules[0], summary = health[0]?.details;
    if (!rule) { host.textContent='The hypothesis has not been registered yet. Awaiting the first collection run.'; return; }
    const frozen = new Map(predictions.map(p=>[p.event_key,p]));
    const labels = {collecting:'Collecting evidence', paused_drawdown:'Paused: drawdown rule reached', not_supported:'Not supported at review', mixed:'Mixed evidence', awaiting_validation:'Promising proxy result; awaiting validation'};
    const stale = !health[0] || Date.now()-Date.parse(health[0].checked_at)>4*86400000;
    let html = `<div class="callout"><strong>${esc(labels[summary?.status] || 'Awaiting outcomes')}</strong>${stale?' · Update is missing or over four days old.':''}<br>Fixed rule: S&amp;P 500 return &gt; 0%; A200 at 10:05 → 15:55 Sydney time. Compare with US flat/down days using the same ETF and times.</div>`;
    html += `<p>Registered: ${esc(date(rule.registered_at))} Adelaide time · ${esc(key)}. Research amount ${money(rule.config.capital_aud)}; assumed round-trip brokerage ${money(rule.config.brokerage_round_trip_aud)} plus ${esc(rule.config.friction_round_trip_bps)} basis points for spread and slippage.</p>`;
    html += `<p><strong>Why this might happen:</strong> ${esc(rule.mechanism)}</p>`;
    if (summary) {
      html += '<div class="metric-grid">';
      for (const [label,value] of [['Observed sessions',summary.all_proxy.observed],['Missing or excluded',summary.all_proxy.missing_or_excluded],['Predictions frozen before entry',summary.forward_proxy.observed],['Validated signal outcomes',summary.validated.signal.n]]) {
        html += `<article class="metric"><span>${esc(label)}</span><strong>${esc(value)}</strong></article>`;
      }
      html += '</div><div class="table-wrap"><table><caption>Results after assumed costs · fixed A$2,000 examples</caption><thead><tr><th>Evidence set</th><th>US-up sessions</th><th>Flat/down sessions</th><th>US-up average / median</th><th>Comparison average</th><th>Average difference</th><th>US-up wins</th><th>Approx. 95% win interval</th><th>Average win / loss</th><th>Worst / largest cumulative fall</th></tr></thead><tbody>';
      for (const [field,label] of [['all_proxy','All collected prices · exploratory proxies'],['forward_proxy','Prediction saved before entry · proxies'],['validated','Verified execution · validation']]) {
        const g=summary[field], s=g.signal;
        html += `<tr><td>${label}</td><td>${s.n}</td><td>${g.comparison.n}</td><td>${money(s.mean)} / ${money(s.median)}</td><td>${money(g.comparison.mean)}</td><td>${money(g.mean_difference_aud)}</td><td>${pct(s.win_rate)}</td><td>${s.win_interval?s.win_interval.map(pct).join(' to '):'—'}</td><td>${money(s.average_win)} / ${money(s.average_loss)}</td><td>${money(s.worst)} / ${money(s.drawdown)}</td></tr>`;
      }
      html += `</tbody></table></div><p class="footnote">${esc(summary.limitations)} Latest outcome: ${esc(summary.latest_session || 'none')}. Last summary: ${esc(date(health[0].checked_at))} Adelaide time. Intervals are descriptive uncertainty estimates, not a forecast probability.</p>`;
    }
    html += `<details><summary>Frozen review and stop rules</summary><p>${esc(rule.config.stop_rule)}</p><p>At least ${esc(rule.config.minimum_per_group)} usable observations in each group is an initial review threshold, not proof. Rule changes require a new version and new validation. No proxy outcome is treated as verified execution.</p></details>`;
    html += '<p>Morning predictions are saved before entry when the scheduled job arrives on time. Evening collection attaches results. Missed morning jobs remain visible as missing pre-entry evidence. Shared news and other explanations remain unreviewed.</p><button type="button" id="exportEventEvidence">Download evidence (JSON)</button>';
    html += '<div class="table-wrap"><table><caption>Latest 60 sessions · every group, including missing results</caption><thead><tr><th>Session</th><th>US move</th><th>Group</th><th>Prediction captured (Adelaide)</th><th>Net research A$</th><th>Opening gap proxy</th><th>Evidence quality</th><th>Source</th></tr></thead><tbody>';
    for (const row of outcomes.slice(0,60)) {
      const p=frozen.get(row.event_key), r=row.result;
      const quality=r.exclusions.length?r.exclusions.join(', '):r.pre_entry_frozen?'Frozen prediction; unverified price proxy':'Exploratory; unverified price proxy';
      html += `<tr><td>${esc(row.session_date)}</td><td>${row.us_return_pct==null?'—':esc(row.us_return_pct.toFixed(2)+'%')}</td><td>${row.signal===null?'Unknown':row.signal?'US up':'Flat/down'}</td><td>${esc(date(p?.captured_at))}</td><td>${money(r.net_aud)}</td><td>${pct(r.opening_gap_proxy)}</td><td>${esc(quality)}</td><td><a href="https://finance.yahoo.com/quote/A200.AX/history/" target="_blank" rel="noopener">Yahoo research bars</a></td></tr>`;
    }
    html += '</tbody></table></div><p class="footnote">An opening gap is movement before entry, not profit from the proposed trade. Intraday best/worst movement, surprise and competing-event reviews are not yet measured. Source observations remain private; this register exposes derived research results.</p>';
    host.innerHTML=html;
    document.getElementById('exportEventEvidence').addEventListener('click',()=>{
      const url=URL.createObjectURL(new Blob([JSON.stringify({exported_at:new Date().toISOString(),rule,summary,predictions,outcomes},null,2)],{type:'application/json'}));
      const link=document.createElement('a');link.href=url;link.download='market-lab-event-evidence.json';link.click();URL.revokeObjectURL(url);
    });
  } catch (error) {
    host.textContent='Event evidence could not be loaded. Check the collection run and database setup. No result is inferred from missing data.';
  }
})();
