(() => {
  const money = (value) => new Intl.NumberFormat('en-AU', { style: 'currency', currency: 'AUD', maximumFractionDigits: 2 }).format(Number(value) || 0);
  const pct = (value) => Number.isFinite(Number(value)) ? `${(Number(value) * 100).toFixed(2)}%` : '—';
  const cap = () => {
    const n = Number(document.getElementById('capitalInput')?.value || 2000);
    return Number.isFinite(n) && n > 0 ? n : 2000;
  };

  function ensureView() {
    if (!document.querySelector('link[href="/context_insights.css"]')) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = '/context_insights.css';
      document.head.appendChild(link);
    }
    if (!document.querySelector('.nav a[href="#market-context"]')) {
      const nav = document.querySelector('.nav');
      const anchor = document.createElement('a');
      anchor.href = '#market-context';
      anchor.textContent = 'Market Context';
      const backfill = nav?.querySelector('a[href="#historical-backfill"]');
      if (nav) nav.insertBefore(anchor, backfill?.nextSibling || null);
    }
    if (!document.getElementById('market-context')) {
      const section = document.createElement('section');
      section.id = 'market-context';
      section.className = 'section panel';
      section.innerHTML = `
        <div class="section-heading">
          <div><p class="eyebrow">WHEN A PATTERN WORKED BETTER</p><h2>Market Context</h2></div>
          <p class="section-note">Tests simple pre-event conditions such as market direction, volatility, bond yields, oil and the US dollar. This is exploratory and does not change any frozen rule.</p>
        </div>
        <div class="callout" id="contextSummary">Loading market-context analysis…</div>
        <div class="context-warning"><strong>Important:</strong> these conditions were found by looking backwards. A stronger historical result under one condition is a research lead, not permission to change a frozen rule or use real money.</div>
        <div id="contextCards" class="context-grid"></div>
        <div class="table-wrap context-table"><table>
          <thead><tr><th>Policy pattern</th><th>Pre-event condition</th><th>Independent events</th><th>Average return</th><th>Positive</th><th>Beat broad market</th><th>Improvement vs base</th><th>A$ effect</th></tr></thead>
          <tbody id="contextRows"><tr><td colspan="8">Loading context summaries…</td></tr></tbody>
        </table></div>
        <p class="footnote">Only simple one-factor conditions are tested here. Market Lab deliberately avoids searching thousands of combinations because that would make accidental historical patterns much easier to manufacture.</p>`;
      const historical = document.getElementById('historical-backfill');
      if (historical?.parentNode) historical.parentNode.insertBefore(section, historical.nextSibling);
      else document.querySelector('main')?.appendChild(section);
    }
  }

  function score(row) {
    const lift = Number(row.return_lift || 0);
    const hitLift = Number(row.hit_rate_lift || 0);
    const beat = Number(row.beat_market_rate || 0);
    const n = Number(row.event_count || 0);
    return lift * Math.sqrt(Math.max(n, 1)) + hitLift * 0.01 + beat * 0.002;
  }

  function patternLabel(row) {
    const theme = pretty(row.policy_theme || '');
    const direction = pretty(row.direction_guess || '');
    const hold = String(row.horizon || '').replace('d', ' trading days');
    return `${theme} · ${direction} → ${row.symbol} · ${hold}`;
  }

  async function renderContextInsights() {
    ensureView();
    const summary = document.getElementById('contextSummary');
    const cards = document.getElementById('contextCards');
    const body = document.getElementById('contextRows');
    if (!summary || !cards || !body) return;
    if (!state?.connected) {
      summary.innerHTML = '<strong>Market-context analysis unavailable:</strong> Supabase is not connected.';
      return;
    }
    try {
      const rows = await supabaseGet(
        'context_condition_summaries',
        'select=*&source_dataset=eq.federal_register_context_v1&event_count=gte.4&order=event_count.desc&limit=1000'
      );
      const usable = rows.filter(r =>
        Number(r.base_event_count || 0) >= 8 &&
        Number(r.average_abnormal_return || 0) > 0 &&
        Number(r.beat_market_rate || 0) >= 0.60
      );
      const stronger = usable.filter(r =>
        Number(r.return_lift || 0) >= 0.003 &&
        Number(r.hit_rate_lift || 0) >= 0
      ).sort((a,b) => score(b) - score(a));
      const display = stronger.slice(0, 12);
      const capital = cap();

      summary.innerHTML = display.length
        ? `<strong>${display.length} context leads currently clear the display screen.</strong> These are conditions where an already-defined historical policy pattern looked stronger than its own overall average. They remain exploratory until tested on unseen events.`
        : `<strong>No context condition currently clears the display screen.</strong> That is a useful result: the present data does not justify adding a market-condition filter to a frozen rule.`;

      const top = display.slice(0, 3);
      cards.innerHTML = top.map(r => {
        const avg = Number(r.average_return || 0);
        const lift = Number(r.return_lift || 0);
        return `<article class="context-card">
          <span class="context-pill">Exploratory only</span>
          <h3>${escapeHtml(patternLabel(r))}</h3>
          <p><strong>${escapeHtml(r.condition_label || '')}</strong></p>
          <div class="context-money">${money(capital * avg)} average on ${money(capital)}</div>
          <dl>
            <div><dt>Independent events</dt><dd>${Number(r.event_count || 0)}</dd></div>
            <div><dt>Positive</dt><dd>${pct(r.hit_rate)}</dd></div>
            <div><dt>Average return</dt><dd>${pct(avg)}</dd></div>
            <div><dt>Better than base by</dt><dd>${pct(lift)}</dd></div>
          </dl>
        </article>`;
      }).join('');

      body.innerHTML = display.map(r => {
        const avg = Number(r.average_return || 0);
        const lift = Number(r.return_lift || 0);
        return `<tr>
          <td><strong>${escapeHtml(patternLabel(r))}</strong><div class="muted">Base sample ${Number(r.base_event_count || 0)} events</div></td>
          <td>${escapeHtml(r.condition_label || '')}</td>
          <td>${Number(r.event_count || 0)}</td>
          <td>${pct(avg)}</td>
          <td>${pct(r.hit_rate)}</td>
          <td>${pct(r.beat_market_rate)}</td>
          <td>${pct(lift)}<div class="muted">Hit-rate change ${pct(r.hit_rate_lift)}</div></td>
          <td>${money(capital * avg)}<div class="muted">gross historical average</div></td>
        </tr>`;
      }).join('') || '<tr><td colspan="8">No simple market condition has yet improved a sufficiently large policy pattern enough to display.</td></tr>';
    } catch (err) {
      console.warn('Market context view unavailable', err);
      summary.innerHTML = '<strong>Market-context data is temporarily unavailable.</strong>';
      body.innerHTML = '<tr><td colspan="8">Unable to load context summaries.</td></tr>';
    }
  }

  ensureView();
  window.addEventListener('load', () => setTimeout(renderContextInsights, 1000));
  document.getElementById('capitalInput')?.addEventListener('input', () => setTimeout(renderContextInsights, 100));
})();
