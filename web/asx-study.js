/* Pure research calculations shared by the dashboard and Node tests. */
(function (root) {
  'use strict';
  const fields = ['session_date','symbol','us_return_pct','us_close_at','spi_change_pct','spi_observed_at','signal_at','previous_close','open_price','open_at','entry_price','entry_at','exit_price','exit_at','source'];
  function csv(text) {
    const rows=[]; let row=[], field='', quoted=false;
    text=text.replace(/^\uFEFF/,'');
    for(let i=0;i<text.length;i++) {
      const c=text[i];
      if(c==='"') { if(quoted && text[i+1]==='"'){field+='"';i++;} else quoted=!quoted; }
      else if(!quoted && c===','){row.push(field.trim());field='';}
      else if(!quoted && (c==='\n'||c==='\r')){if(c==='\r'&&text[i+1]==='\n')i++;row.push(field.trim());if(row.some(Boolean))rows.push(row);row=[];field='';}
      else field+=c;
    }
    if(quoted)throw Error('CSV contains an unclosed quote.');
    row.push(field.trim());if(row.some(Boolean))rows.push(row);
    if(!rows.length)throw Error('CSV is empty.');
    const header=rows.shift();
    if(new Set(header).size!==header.length)throw Error('Duplicate CSV column names.');
    for(const key of fields)if(!header.includes(key))throw Error(`Missing column: ${key}`);
    return rows.map((values,i)=>{if(values.length!==header.length)throw Error(`CSV row ${i+2}: incorrect number of fields.`);return Object.fromEntries(header.map((k,j)=>[k,values[j]]));});
  }
  function sydney(value) {
    const parts=new Intl.DateTimeFormat('en-CA',{timeZone:'Australia/Sydney',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hourCycle:'h23'}).formatToParts(new Date(value));
    const p=Object.fromEntries(parts.map(x=>[x.type,x.value]));return {date:`${p.year}-${p.month}-${p.day}`,time:`${p.hour}:${p.minute}:${p.second}`};
  }
  function validate(rows, now=Date.now()) {
    const valid=[], errors=[], seen=new Set(); let symbol=null, source=null;
    for(const [i,r] of rows.entries()) {
      try {
        if(!/^\d{4}-\d{2}-\d{2}$/.test(r.session_date)||new Date(r.session_date+'T00:00:00Z').toISOString().slice(0,10)!==r.session_date)throw Error('invalid session date');
        if([0,6].includes(new Date(r.session_date+'T00:00:00Z').getUTCDay()))throw Error('session date is a weekend');
        if(!r.symbol||!r.source)throw Error('symbol and source are required');
        if(symbol!==null && (r.symbol!==symbol||r.source!==source))throw Error('use one symbol and one consistent source per import');
        const n={...r};
        for(const k of ['us_return_pct','spi_change_pct','previous_close','open_price','entry_price','exit_price']){
          if(r[k]===''||r[k]==null||!Number.isFinite(Number(r[k])))throw Error(`${k} must be numeric`);
          n[k]=Number(r[k]);if(k.includes('price')||k==='previous_close'){if(n[k]<=0)throw Error(`${k} must be positive`);}
        }
        for(const k of ['us_close_at','spi_observed_at','signal_at','open_at','entry_at','exit_at']){
          if(!/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)$/.test(r[k])||!Number.isFinite(Date.parse(r[k])))throw Error(`${k} needs an ISO timestamp with seconds and timezone`);
          n[k]=Date.parse(r[k]);
        }
        for(const [key,time] of [['signal_at','09:30:00'],['spi_observed_at','09:30:00'],['entry_at','10:05:00'],['exit_at','15:55:00']]){
          const p=sydney(n[key]);if(p.date!==r.session_date||p.time!==time)throw Error(`${key} must be ${time} Sydney time on the session date`);
        }
        const o=sydney(n.open_at);if(o.date!==r.session_date||o.time<'10:00:00'||o.time>'10:05:00')throw Error('open_at must be the ETF opening auction between 10:00 and 10:05 Sydney time');
        if(n.us_close_at>=n.signal_at||n.signal_at-n.us_close_at>96*3600000)throw Error('US close must precede the signal by less than 96 hours');
        if(n.exit_at>now)throw Error('session has not finished yet');
        if(seen.has(r.session_date))throw Error('duplicate session date');
        symbol=r.symbol;source=r.source;seen.add(r.session_date);valid.push(n);
      } catch(e){errors.push(`Row ${i+2}: ${e.message}.`);}
    }
    return {rows:valid.sort((a,b)=>a.session_date.localeCompare(b.session_date)), errors};
  }
  function stats(rows) {
    if(!rows.length)return {n:0,mean:null,winRate:null,averageWin:null,averageLoss:null,worst:null,drawdown:null,sum:0};
    const mean=rows.reduce((s,r)=>s+r.net,0)/rows.length;
    const wins=rows.filter(r=>r.net>0),losses=rows.filter(r=>r.net<0);
    let sum=0,peak=0,drawdown=0;for(const r of rows){sum+=r.net;peak=Math.max(peak,sum);drawdown=Math.min(drawdown,sum-peak);}
    const avg=rs=>rs.length?rs.reduce((s,r)=>s+r.net,0)/rs.length:null;
    return {n:rows.length,mean,winRate:wins.length/rows.length,averageWin:avg(wins),averageLoss:avg(losses),worst:Math.min(...rows.map(r=>r.net)),drawdown,sum};
  }
  function analyse(rows,{capital=2000,brokerage=10,frictionBps=10}={}) {
    if(![capital,brokerage,frictionBps].every(Number.isFinite)||capital<=0||brokerage<0||frictionBps<0)throw Error('Enter a positive amount and non-negative costs.');
    const cost=brokerage+capital*frictionBps/10000;
    const trades=rows.map(r=>({...r,signal:r.us_return_pct>0 && r.spi_change_pct>=0.5,gap:r.open_price/r.previous_close-1,gross:capital*(r.exit_price/r.entry_price-1),net:capital*(r.exit_price/r.entry_price-1)-cost}));
    const group=rs=>({signal:stats(rs.filter(r=>r.signal)),other:stats(rs.filter(r=>!r.signal)),all:stats(rs)});
    return {cost,trades,history:group(trades.filter(r=>r.session_date<'2026-10-16')),future:group(trades.filter(r=>r.session_date>='2026-10-16'))};
  }
  const api={fields,csv,validate,analyse,stats};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.ASXStudy=api;
})(typeof window!=='undefined'?window:globalThis);
