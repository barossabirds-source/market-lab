(() => {
  const money = (value) => new Intl.NumberFormat('en-AU', { style: 'currency', currency: 'AUD', maximumFractionDigits: 2 }).format(Number(value) || 0);
  const pct = (value) => Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(2)}%` : '—';
  const cap = () => {
    const n = Number(document.getElementById('capitalInput')?.value || 2000);
    return Number.isFinite(n) && n > 0 ? n : 2000;
  };

  function rankDiscovery(d) {
    const n = Number(d.event_count || 0);
    const avg = Number(d.average_return);
    const hit = Number(d.hit_rate);
    const first = Number(d.first_term_average);
    const second = Number(d.second_term_average);
    const bothTerms = Number(d.first_term_count || 0) >= 2 && Number(d.second_term_count || 0) >= 2 && first > 0 && second > 0;
    return (Number.isFinite(avg) ? avg : -1) * Math.sqrt(Math.max(n, 1)) * (Number.isFinite(hit) ? hit : 0) + (bothTerms ? 0.05 : 0);
  }

  async function renderHistoricalBackfill() {
    const summary = document.getElementById('backfillSummary');
    const metrics = document.getElementById('backfillMetrics');
    const body = document.getElementById('discoveryRows');
    if (!summary || !metrics || !body || !state?.connected) return;

    try {
      const [runs, candidates, discoveries] = await Promise.all([
        supabaseGet('backfill_runs', 'select=*&order=started_at.desc&limit=1'),
        supabaseGet('event_candidates', 'select=id,event_date,policy_theme,relevance_score,review_status&order=event_date.asc&limit=2000'),
        supabaseGet('historical_discoveries', 'select=*&event_count=gte.5&limit=2000'),
      ]);

      const latest = runs[0];
      const dates = candidates.map(x => String(x.event_date || '')).filter(Boolean).sort();
      const themes = new Set(candidates.map(x => x.policy_theme).filter(Boolean));
      const reviewed = candidates.filter(x => String(x.review_status || '') !== 'candidate').length;
      const allExploratory = [...discoveries].filter(d => Number(d.average_return) > 0 && Number(d.hit_rate) >= 0.60);
      const ranked = allExploratory.sort((a,b) => rankDiscovery(b) - rankDiscovery(a)).slice(0, 12);

      summary.innerHTML = latest?.status === 'completed'
        ? `<strong>Historical backfill complete.</strong> The automated layer scans official Federal Register presidential documents, classifies market-relevant candidates and measures 1, 3, 5 and 20 trading-day reactions. These records remain separate from the curated event ledger until reviewed.`
        : `<strong>Historical backfill status:</strong> ${escapeHtml(latest?.status || 'waiting')}. Candidate records are kept separate from the curated ledger.`;

      metrics.innerHTML = `
        <article class="backfill-metric"><span>Official documents scanned</span><strong>${Number(latest?.documents_fetched || 0).toLocaleString()}</strong></article>
        <article class="backfill-metric"><span>Market-relevant candidates</span><strong>${candidates.length.toLocaleString()}</strong></article>
        <article class="backfill-metric"><span>Candidate themes</span><strong>${themes.size}</strong></article>
        <article class="backfill-metric"><span>Exploratory pattern summaries</span><strong>${Number(latest?.discoveries_written || discoveries.length).toLocaleString()}</strong></article>
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
          <td>${pct(d.hit_rate)}</td>
          <td>${pct(avg)}<div class="muted">${money(capital * avg)} on ${money(capital)}</div></td>
          <td>${pct(worst)}<div class="muted">${money(capital * worst)}</div></td>
          <td>${crossTerm ? `${pct(first)} / ${pct(second)}` : 'Not enough in both terms'}</td>
          <td><span class="review-pill">Needs review</span></td>
        </tr>`;
      }).join('') || '<tr><td colspan="9">No exploratory discoveries have been calculated yet.</td></tr>';
    } catch (err) {
      console.warn('Historical backfill view unavailable', err);
      summary.innerHTML = '<strong>Historical backfill data is temporarily unavailable.</strong>';
      body.innerHTML = '<tr><td colspan="9">Unable to load the discovery queue.</td></tr>';
    }
  }

  window.addEventListener('load', () => setTimeout(renderHistoricalBackfill, 600));
  document.getElementById('capitalInput')?.addEventListener('input', () => setTimeout(renderHistoricalBackfill, 100));
})();
