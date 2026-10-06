(() => {
  const money = (value) => new Intl.NumberFormat('en-AU', { style: 'currency', currency: 'AUD', maximumFractionDigits: 2 }).format(Number(value) || 0);
  const pct = (value) => Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(2)}%` : '—';
  const cap = () => {
    const n = Number(document.getElementById('capitalInput')?.value || 2000);
    return Number.isFinite(n) && n > 0 ? n : 2000;
  };

  function ensureContextScript() {
    if (!document.querySelector('script[src="/context_insights.js"]')) {
      const script = document.createElement('script');
      script.src = '/context_insights.js';
      script.defer = true;
      document.body.appendChild(script);
    }
  }

  function ensureView() {
    if (!document.querySelector('link[href="/backfill.css"]')) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = '/backfill.css';
      document.head.appendChild(link);
    }
    if (!document.querySelector('.nav a[href="#historical-backfill"]')) {
      const nav = document.querySelector('.nav');
      const anchor = document.createElement('a');
      anchor.href = '#historical-backfill';
      anchor.textContent = 'Historical Backfill';
      const longLink = nav?.querySelector('a[href="#longitudinal"]');
      if (nav) nav.insertBefore(anchor, longLink?.nextSibling || null);
    }
    if (!document.getElementById('historical-backfill')) {
      const section = document.createElement('section');
      section.id = 'historical-backfill';
      section.className = 'section panel';
      section.innerHTML = `
        <div class="section-heading">
          <div><p class="eyebrow">DEEPER HISTORICAL DISCOVERY</p><h2>Historical Backfill</h2></div>
          <p class="section-note">Scans official Trump-era Presidential Documents, keeps automated classifications separate from the curated ledger, and searches the larger history for long-only ideas worth reviewing.</p>
        </div>
        <div class="callout" id="backfillSummary">Loading historical backfill…</div>
        <div id="backfillMetrics" class="backfill-grid"></div>
        <div class="discovery-note"><strong>Discovery queue:</strong> these patterns use predefined theme-relevant funds, remove obvious routine renewals, cluster same-day documents and avoid overlapping holding windows. They still need manual event review before any rule is frozen.</div>
        <div class="table-wrap discovery-table"><table>
          <thead><tr><th>Theme</th><th>Fund</th><th>Hold</th><th>Independent events</th><th>Positive</th><th>Average</th><th>Worst</th><th>First / second term avg</th><th>Status</th></tr></thead>
          <tbody id="discoveryRows"><tr><td colspan="9">Loading exploratory patterns…</td></tr></tbody>
        </table></div>
        <p class="footnote"><strong>Source and limitation:</strong> the automated layer uses official Federal Register Presidential Documents and signing dates where available. Theme and direction labels are transparent keyword-based guesses. Routine renewals are excluded from discovery because they are usually expected rather than new policy surprises. The discovery table also requires positive performance against the broad market, but that still does not prove causation or future profitability.</p>`;
      const long = document.getElementById('longitudinal');
      if (long?.parentNode) long.parentNode.insertBefore(section, long.nextSibling);
    }
    ensureContextScript();
  }

  function rankDiscovery(d) {
    const n = Number(d.event_count || 0);
    const avg = Number(d.average_return);
    const hit = Number(d.hit_rate);
    const abnormal = Number(d.average_abnormal_return);
    const beat = Number(d.beat_market_rate);
    const first = Number(d.first_term_average);
    const second = Number(d.second_term_average);
    const bothTerms = Number(d.first_term_count || 0) >= 2 && Number(d.second_term_count || 0) >= 2 && first > 0 && second > 0;
    return (Number.isFinite(abnormal) ? abnormal : -1) * Math.sqrt(Math.max(n, 1)) * (Number.isFinite(beat) ? beat : 0) + (bothTerms ? 0.025 : 0) + (Number.isFinite(avg) && Number.isFinite(hit) ? avg * hit * 0.25 : 0);
  }

  async function renderHistoricalBackfill() {
    ensureView();
    const summary = document.getElementById('backfillSummary');
    const metrics = document.getElementById('backfillMetrics');
    const body = document.getElementById('discoveryRows');
    if (!summary || !metrics || !body) return;
    if (!state?.connected) {
      summary.innerHTML = '<strong>Historical backfill unavailable:</strong> Supabase is not connected.';
      return;
    }

    try {
      const [runs, candidates, discoveries, contextRows] = await Promise.all([
        supabaseGet('backfill_runs', 'select=*&order=started_at.desc&limit=1'),
        supabaseGet('event_candidates', 'select=id,event_date,policy_theme,relevance_score,review_status&order=event_date.asc&limit=2000'),
        supabaseGet('historical_discoveries', 'select=*&source_dataset=eq.federal_register_clustered_nonoverlap&event_count=gte.5&limit=2000'),
        supabaseGet('candidate_market_context', 'select=candidate_id&limit=2000'),
      ]);

      const latest = runs[0];
      const dates = candidates.map(x => String(x.event_date || '')).filter(Boolean).sort();
      const themes = new Set(candidates.map(x => x.policy_theme).filter(Boolean));
      const reviewed = candidates.filter(x => String(x.review_status || '') !== 'candidate').length;
      const allExploratory = [...discoveries].filter(d =>
        Number(d.average_return) > 0 &&
        Number(d.hit_rate) >= 0.60 &&
        Number(d.average_abnormal_return) > 0 &&
        Number(d.beat_market_rate) >= 0.55
      );
      const ranked = allExploratory.sort((a,b) => rankDiscovery(b) - rankDiscovery(a)).slice(0, 12);

      summary.innerHTML = latest?.status === 'completed'
        ? `<strong>Historical backfill complete.</strong> The automated layer scanned official Federal Register presidential documents, classified market-relevant candidates and measured 1, 3, 5 and 20 trading-day reactions. Discovery results are restricted to relevant funds, obvious routine renewals are removed, and duplicate or overlapping observations are reduced.`
        : `<strong>Historical backfill status:</strong> ${escapeHtml(latest?.status || 'waiting')}. Candidate records are kept separate from the curated ledger.`;

      metrics.innerHTML = `
        <article class="backfill-metric"><span>Official documents scanned</span><strong>${Number(latest?.documents_fetched || 0).toLocaleString()}</strong></article>
        <article class="backfill-metric"><span>Market-relevant candidates</span><strong>${candidates.length.toLocaleString()}</strong></article>
        <article class="backfill-metric"><span>Candidate themes</span><strong>${themes.size}</strong></article>
        <article class="backfill-metric"><span>Refined pattern summaries</span><strong>${discoveries.length.toLocaleString()}</strong></article>
        <article class="backfill-metric"><span>Market backdrop records</span><strong>${contextRows.length.toLocaleString()}</strong></article>
        <article class="backfill-metric"><span>Historical coverage</span><strong>${dates.length ? `${dates[0]} → ${dates[dates.length-1]}` : '—'}</strong></article>
        <article class="backfill-metric"><span>Manually reviewed candidates</span><strong>${reviewed.toLocaleString()}</strong></article>`;

      const capital = cap();
      body.innerHTML = ranked.map(d => {
        const avg = Number(d.average_return);
        const worst = Number(d.worst_return);
        const first = Number(d.first_term_average);
        const second = Number(d.second_term_average);
        const crossTerm = Number(d.first_term_count || 0) >= 2 && Number(d.second_term_count || 0) >= 2;
        return `<tr>
          <td><strong>${escapeHtml(pretty(d.policy_theme || ''))}</strong><div class="muted">${escapeHtml(d.direction_guess === 'any' ? 'Any direction' : pretty(d.direction_guess || ''))}</div></td>
          <td>${escapeHtml(d.symbol || '')}</td>
          <td>${escapeHtml(String(d.horizon || '').replace('d',' trading days'))}</td>
          <td>${Number(d.event_count || 0)}</td>
          <td>${pct(d.hit_rate)}<div class="muted">Beat broad market ${pct(d.beat_market_rate)}</div></td>
          <td>${pct(avg)}<div class="muted">${money(capital * avg)} on ${money(capital)}</div></td>
          <td>${pct(worst)}<div class="muted">${money(capital * worst)}</div></td>
          <td>${crossTerm ? `${pct(first)} / ${pct(second)}` : 'Not enough in both terms'}</td>
          <td><span class="review-pill">Needs review</span></td>
        </tr>`;
      }).join('') || '<tr><td colspan="9">No refined discoveries meet the current screening rules yet.</td></tr>';
    } catch (err) {
      console.warn('Historical backfill view unavailable', err);
      summary.innerHTML = '<strong>Historical backfill data is temporarily unavailable.</strong>';
      body.innerHTML = '<tr><td colspan="9">Unable to load the discovery queue.</td></tr>';
    }
  }

  ensureView();
  window.addEventListener('load', () => setTimeout(renderHistoricalBackfill, 800));
  document.getElementById('capitalInput')?.addEventListener('input', () => setTimeout(renderHistoricalBackfill, 100));
})();
