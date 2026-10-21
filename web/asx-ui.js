(function(){
  'use strict';
  const el=id=>document.getElementById(id);
  const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const money=v=>v===null?'—':v.toLocaleString('en-AU',{style:'currency',currency:'AUD'});
  const pct=v=>v===null?'—':`${(v*100).toFixed(2)}%`;
  let observations=[], rejected=[], loaded=false;
  function render(){
    if(!loaded)return;
    try{
      const number=id=>el(id).value.trim()===''?NaN:Number(el(id).value);
      const result=ASXStudy.analyse(observations,{capital:number('asxCapital'),brokerage:number('asxBrokerage'),frictionBps:number('asxFriction')});
      const gateStatus=el('asxGateStatus');
      if(gateStatus && window.MarketLabGateAdapters && window.MarketLabResearchGate) {
        const assessment=window.MarketLabGateAdapters.assessAsx(result,{
          capital:number('asxCapital'),
          provenance:'',
          pointInTime:false,
          noSignalSessions:observations.some(r=>!(r.us_return_pct>0 && r.spi_change_pct>=0.5)),
          oosCount:0
        });
        gateStatus.textContent='ASX evidence: '+assessment.status.replaceAll('_',' ')+' · '+assessment.reasons.join('; ')+'. Automated data import cannot verify provenance or genuine out-of-sample status.';
      }
      el('asxStatus').textContent=`${observations.length} usable completed sessions · ${rejected.length} rejected rows · assumed cost ${money(result.cost)} per round trip. ${observations.length?'Imported observations; coverage and sources require review.':'No usable observations. No result can be calculated.'}`;
      let html=rejected.length?`<details><summary>Rejected rows (${rejected.length})</summary><ul>${rejected.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></details>`:'';
      for(const [key,label] of [['history','Earlier history · exploratory'],['future','From 16 October 2026 · prospective rule period']]){
        const g=result[key];
        html+=`<table><caption>${label}</caption><thead><tr><th>Sessions</th><th>Count</th><th>Average net A$</th><th>Positive after cost</th><th>Average win</th><th>Average loss</th><th>Worst trade</th><th>Largest cumulative fall</th></tr></thead><tbody>`;
        for(const [k,name] of [['signal','US up + SPI ≥ 0.5%'],['other','Other observed days'],['all','All observed days']]){const s=g[k];html+=`<tr><td>${name}</td><td>${s.n}</td><td>${money(s.mean)}</td><td>${pct(s.winRate)}</td><td>${money(s.averageWin)}</td><td>${money(s.averageLoss)}</td><td>${money(s.worst)}</td><td>${money(s.drawdown)}</td></tr>`;}
        html+='</tbody></table>';
        const difference=g.signal.n&&g.other.n?g.signal.mean-g.other.mean:null;
        html+=`<p>Signal-day average minus other-day average: <strong>${money(difference)}</strong> per fixed-size example. ${g.signal.n<20||g.other.n<20?'Too few observations for a useful initial comparison.':'A positive difference is descriptive evidence; independent validation is still required.'}</p>`;
      }
      html+='<p class="asx-warning">The date split does not certify unseen data: keep a source archive proving observations were available at the stated times. Changing costs is a sensitivity check; the signal threshold and trade times remain fixed. Repeated sessions can be correlated. Cumulative falls use fixed-size trades, not a compounded portfolio.</p>';
      html+='<table><caption>Latest 30 imported sessions · opening gap versus money earned after entry</caption><thead><tr><th>Date</th><th>Signal</th><th>Opening gap</th><th>Entry</th><th>Exit</th><th>Gross A$</th><th>Net A$</th></tr></thead><tbody>';
      for(const t of result.trades.slice(-30).reverse())html+=`<tr><td>${esc(t.session_date)}</td><td>${t.signal?'Yes':'No'}</td><td>${pct(t.gap)}</td><td>${money(t.entry_price)}</td><td>${money(t.exit_price)}</td><td>${money(t.gross)}</td><td>${money(t.net)}</td></tr>`;
      el('asxResults').innerHTML=html+'</tbody></table>';
    }catch(e){el('asxStatus').textContent=e.message;el('asxResults').replaceChildren();}
  }
  el('asxFile').addEventListener('change',async event=>{
    observations=[];rejected=[];loaded=false;el('asxResults').replaceChildren();
    const file=event.target.files[0];if(!file){el('asxStatus').textContent='Awaiting data. No feed is connected.';return;}
    if(file.size>5*1024*1024){el('asxStatus').textContent='File too large. Import a CSV below 5 MB.';return;}
    try{const checked=ASXStudy.validate(ASXStudy.csv(await file.text()));observations=checked.rows;rejected=checked.errors;loaded=true;render();}
    catch(e){el('asxStatus').textContent=`Import failed: ${e.message}`;}
  });
  for(const id of ['asxCapital','asxBrokerage','asxFriction'])el(id).addEventListener('input',render);
})();
