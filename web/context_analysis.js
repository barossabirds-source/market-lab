(() => {
  const money = (value) => new Intl.NumberFormat('en-AU', {
    style: 'currency', currency: 'AUD', minimumFractionDigits: 2, maximumFractionDigits: 2,
  }).format(Number(value) || 0);
  const pct = (value) => Number.isFinite(Number(value)) ? `${Number(value) >= 0 ? '+' : ''}${(Number(value) * 100).toFixed(2)}%` : '—';
  const cap = () => {
    const n = Number(document.getElementById('capitalInput')?.value || 2000);
    return Number.isFinite(n) && n > 0 ? n : 2000;
  };
  const cost = () => {
    const n = Number(document.getElementById('costInput')?.value || 0);
    return Number.isFinite(n) && n >= 0 ? n : 0;
  };

  const DIRECT_SYMBOLS = {
    china_trade: ['SOXX','SMH','XLK','EEM'],
    trade_tariffs: ['XLB','XLI','IWM','EEM'],
    energy: ['XLE','XLI','XLU'],
    defense: ['ITA','XLI'],
    financial_regulation: ['XLF','KRE'],
    technology_semiconductors: ['SOXX','SMH','XLK'],
    healthcare_pharma: ['XLV','IBB','XBI'],
    infrastructure_manufacturing: ['XLI','XLB','IWM'],
    sanctions_geopolitics: ['XLE','ITA','EEM'],
    tax_fiscal: ['SPY','XLF','IWM','XLI'],
    labor_immigration: ['IWM','XLY','XLI'],
  };

  function ensureView() {
    if (!document.querySelector('link[href="/context_analysis.css"]')) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = '/context_analysis.css';
      document.head.appendChild(link);
    }
    if (!document.querySelector('.nav a[href="#context-analysis"]')) {
      const nav = document.querySelector('.nav');
      const anchor = document.createElement('a');
      anchor.href = '#context-analysis';
      anchor.textContent = 'Market Conditions';
      const backfillLink = nav?.querySelector('a[href="#historical-backfill"]');
      if (nav) nav.insertBefore(anchor, backfillLink?.nextSibling || null);
    }
    if (!document.getElementById('context-analysis')) {
      const section = document.createElement('section');
      section.id = 'context-analysis';
      section.className = 'section panel';
      section.innerHTML = `
        <div class="section-heading">
          <div><p class="eyebrow">WHEN DOES A PATTERN WORK BEST?</p><h2>Market Conditions</h2></div>
          <p class="section-note">Splits historical results by what the market was already doing before the policy event. This is an exploratory filter, not a trading signal.</p>
        </div>
        <div class="callout" id="contextSummary">Analysing market conditions…</div>
        <div id="contextCards" class="context-card-grid"></div>
        <div class="table-wrap context-table"><table>
          <thead><tr>
            <th>Policy setup</th><th>Fund</th><th>Hold</th><th>Conditions before event</th><th>Events</th><th>Positive</th><th>Average</th><th>Beat broad market</th><th>Worst</th><th>Across both Trump terms</th><th>Status</th>
          </tr></thead>
          <tbody id="contextRows"><tr><td colspan="11">Loading context-conditioned patterns…</td></tr></tbody>
        </table></div>
        <p class="footnote"><strong>Important:</strong> this screen deliberately requires a direct policy-to-fund relationship, at least eight historical observations, positive results in both Trump terms and a positive average versus the broad market. It still uses automatically classified historical events, so every promising setup requires event-by-event review before a rule can be frozen.</p>`;
      const backfill = document.getElementById('historical-backfill');
      const longitudinal = document.getElementById('longitudinal');
      if (backfill?.parentNode) backfill.parentNode.insertBefore(section, backfill.nextSibling);
      else if (longitudinal?.parentNode) longitudinal.parentNode.insertBefore(section, longitudinal.nextSibling);
    }
  }

  function labelTheme(theme) {
    const names = {
      china_trade: 'China trade', trade_tariffs: 'Trade / tariffs', energy: 'Energy', defense: 'Defence',
      financial_regulation: 'Financial regulation', technology_semiconductors: 'Technology / semiconductors',
      healthcare_pharma: 'Health / medicines', infrastructure_manufacturing: 'Infrastructure / manufacturing',
      sanctions_geopolitics: 'Sanctions / geopolitics', tax_fiscal: 'Tax / fiscal', labor_immigration: 'Labour / immigration',
    };
    return names[theme] || pretty(theme || '');
  }

  function labelDirection(direction) {
    const names = { escalation: 'escalation', deescalation: 'de-escalation', sector_support: 'support action', deregulation: 'deregulation', unknown: 'direction unclear' };
    return names[direction] || pretty(direction || '');
  }

  function labelConditions(row) {
    const market = { market_flat: 'market broadly flat', market_rising: 'market already rising', market_falling: 'market already falling' }[row.market_trend] || pretty(row.market_trend || '');
    const vol = { low_volatility: 'low volatility', normal_volatility: 'normal volatility', high_volatility: 'high volatility', very_high_volatility: 'very high volatility' }[row.volatility_bucket] || pretty(row.volatility_bucket || '');
    return `${market}; ${vol}`;
  }

  function passes(row) {
    const n = Number(row.event_count || 0);
    const avg = Number(row.average_return);
    const abn = Number(row.average_abnormal_return);
    const hit = Number(row.hit_rate);
    const beat = Number(row.beat_market_rate);
    const firstN = Number(row.first_term_count || 0);
    const secondN = Number(row.second_term_count || 0);
    const first = Number(row.first_term_average);
    const second = Number(row.second_term_average);
    const allowed = DIRECT_SYMBOLS[row.policy_theme] || [];
    return allowed.includes(row.symbol) && n >= 8 && avg > 0 && abn > 0 && hit >= 0.65 && beat >= 0.60 && firstN >= 3 && secondN >= 3 && first > 0 && second > 0;
  }

  function rank(row) {
    const n = Number(row.event_count || 0);
    const avg = Number(row.average_return || 0);
    const abn = Number(row.average_abnormal_return || 0);
    const hit = Number(row.hit_rate || 0);
    const beat = Number(row.beat_market_rate || 0);
    const downside = Math.abs(Math.min(0, Number(row.worst_return || 0)));
    return (abn * Math.sqrt(n) * beat) + (avg * hit * 0.35) - (downside * 0.08);
  }

  function confidenceLabel(row) {
    const n = Number(row.event_count || 0);
    const beat = Number(row.beat_market_rate || 0);
    if (n >= 15 && beat >= 0.70) return 'Stronger historical lead';
    if (n >= 10) return 'Worth manual review';
    return 'Early historical lead';
  }

  async function renderContextAnalysis() {
    ensureView();
    const summary = document.getElementById('contextSummary');
    const cards = document.getElementById('contextCards');
    const body = document.getElementById('contextRows');
    if (!summary || !cards || !body) return;
    if (!state?.connected) {
      summary.innerHTML = '<strong>Market-condition analysis unavailable:</strong> Supabase is not connected.';
      return;
    }
    try {
      const rows = await supabaseGet('context_pattern_summary', 'select=*&event_count=gte.8&limit=2000');
      const leads = rows.filter(passes).sort((a,b) => rank(b) - rank(a)).slice(0, 12);
      const capital = cap();
      const tradeCost = cost();
      const top = leads.slice(0, 3);

      summary.innerHTML = leads.length
        ? `<strong>${leads.length} context-conditioned historical leads pass the current screen.</strong> The screen asks a stricter question than the basic backfill: did the setup work when the market backdrop was similar, did it beat the broad market on average, and was it positive in both Trump terms? These are still discovery results and are not frozen rules.`
        : '<strong>No context-conditioned lead currently passes the conservative screen.</strong>';

      cards.innerHTML = top.map((d, idx) => {
        const avg = Number(d.average_return);
        const worst = Number(d.worst_return);
        const net = capital * avg - tradeCost;
        const worstNet = capital * worst - tradeCost;
        return `<article class="context-card">
          <p class="eyebrow">RESEARCH LEAD ${idx + 1}</p>
          <h3>${escapeHtml(labelTheme(d.policy_theme))} · ${escapeHtml(labelDirection(d.direction_guess))}</h3>
          <p><strong>${escapeHtml(d.symbol)}</strong> for ${escapeHtml(String(d.horizon).replace('d',' trading days'))}</p>
          <p class="context-condition">Only when: ${escapeHtml(labelConditions(d))}</p>
          <div class="context-money"><span>Historical average on ${money(capital)} after entered cost</span><strong class="${net >= 0 ? 'pos' : 'neg'}">${money(net)}</strong></div>
          <p>${Number(d.event_count)} events · ${Math.round(Number(d.hit_rate) * 100)}% positive · beat broad market ${Math.round(Number(d.beat_market_rate) * 100)}% of the time.</p>
          <p class="muted">Worst historical ${money(capital)} example after entered cost: ${money(worstNet)}.</p>
          <span class="context-status">${escapeHtml(confidenceLabel(d))} · not frozen</span>
        </article>`;
      }).join('');

      body.innerHTML = leads.map(d => {
        const avg = Number(d.average_return);
        const worst = Number(d.worst_return);
        const first = Number(d.first_term_average);
        const second = Number(d.second_term_average);
        const net = capital * avg - tradeCost;
        return `<tr>
          <td><strong>${escapeHtml(labelTheme(d.policy_theme))}</strong><div class="muted">${escapeHtml(labelDirection(d.direction_guess))}</div></td>
          <td>${escapeHtml(d.symbol || '')}</td>
          <td>${escapeHtml(String(d.horizon || '').replace('d',' trading days'))}</td>
          <td>${escapeHtml(labelConditions(d))}</td>
          <td>${Number(d.event_count || 0)}</td>
          <td>${Math.round(Number(d.hit_rate || 0) * 100)}%</td>
          <td>${pct(avg)}<div class="muted">${money(net)} net on ${money(capital)}</div></td>
          <td>${pct(d.average_abnormal_return)}<div class="muted">${Math.round(Number(d.beat_market_rate || 0) * 100)}% of events</div></td>
          <td>${pct(worst)}</td>
          <td>${pct(first)} / ${pct(second)}</td>
          <td><span class="review-pill">${escapeHtml(confidenceLabel(d))}</span></td>
        </tr>`;
      }).join('') || '<tr><td colspan="11">No context-conditioned patterns meet the current screen.</td></tr>';
    } catch (err) {
      console.warn('Market-condition analysis unavailable', err);
      summary.innerHTML = '<strong>Market-condition analysis is temporarily unavailable.</strong>';
      body.innerHTML = '<tr><td colspan="11">Unable to load the market-condition screen.</td></tr>';
    }
  }

  ensureView();
  window.addEventListener('load', () => setTimeout(renderContextAnalysis, 1000));
  document.getElementById('capitalInput')?.addEventListener('input', () => setTimeout(renderContextAnalysis, 100));
  document.getElementById('costInput')?.addEventListener('input', () => setTimeout(renderContextAnalysis, 100));
})();
