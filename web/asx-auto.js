(async function(){
  'use strict';
  const status=document.getElementById('asxAutoStatus'), metrics=document.getElementById('asxAutoMetrics'), note=document.getElementById('asxAutoNote');
  const config=window.MARKET_LAB_CONFIG||{};
  const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  if(!config.supabaseUrl||!config.supabasePublishableKey){status.textContent='Automatic collection status is unavailable: database connection is not configured.';return;}
  try{
    const response=await fetch(`${config.supabaseUrl}/rest/v1/asx_feed_status?select=*&order=feed_key`,{headers:{apikey:config.supabasePublishableKey}});
    if(!response.ok)throw Error('Status request failed');
    const rows=await response.json();const prices=rows.find(r=>r.feed_key==='research_prices'), spi=rows.find(r=>r.feed_key==='spi_futures'), storage=rows.find(r=>r.feed_key==='storage');
    if(!prices){status.textContent='Automatic collection is installed; its first successful run has not been recorded. SPI futures access still needs setup.';return;}
    const stale=!Number.isFinite(Date.parse(prices.checked_at))||Date.now()-Date.parse(prices.checked_at)>4*86400000;
    status.textContent=stale?'Collection status is over four days old. Check the scheduled job before interpreting stored observations.':prices.status==='error'?prices.message:`Automatic research collection: ${prices.status}. ${prices.message}`;
    const details=storage?.details||{};
    const mb=value=>Number.isFinite(Number(value))&&value!==null?`${(Number(value)/1048576).toFixed(2)} MB`:'Not measured yet';
    const cards=[['Stored ASX session records',details.sessions??'—'],['Latest stored session',details.latest_session??'Awaiting first collection'],['ASX study storage',mb(details.study_bytes)],['Whole database storage',mb(details.database_bytes)]];
    metrics.innerHTML=cards.map(([label,value])=>`<article class="metric"><span>${esc(label)}</span><strong>${esc(value)}</strong></article>`).join('');
    const time=new Date(prices.checked_at).toLocaleString('en-AU',{timeZone:'Australia/Adelaide'});
    const batch=prices.details||{};
    note.textContent=`Last attempt: ${time} Adelaide time. Latest batch: ${batch.attempted_sessions??'—'} sessions checked; ${batch.sessions_with_gaps??'—'} have missing US or ETF price observations. ${spi?.message||'SPI futures feed is not configured.'} Collection runs after the Australian close, not as a live alert service. Minute-bar prices are research estimates; they do not establish executable entry prices. No automatic result is eligible for the fixed rule yet. Raw provider observations are private. Storage figures were measured at the last successful run; they are not a quota estimate.`;
  }catch(error){status.textContent='Could not read automatic collection status. Check the collection job; CSV analysis remains available.';}
})();
