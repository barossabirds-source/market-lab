const {test}=require('node:test');
const assert=require('node:assert/strict');
const s=require('../web/asx-study.js');
const base={session_date:'2026-10-16',symbol:'A200.AX',us_return_pct:'1',us_close_at:'2026-10-15T16:00:00-04:00',spi_change_pct:'0.5',spi_observed_at:'2026-10-16T09:30:00+11:00',signal_at:'2026-10-16T09:30:00+11:00',previous_close:'100',open_price:'101',open_at:'2026-10-16T10:00:00+11:00',entry_price:'101',entry_at:'2026-10-16T10:05:00+11:00',exit_price:'100.6',exit_at:'2026-10-16T15:55:00+11:00',source:'test only'};
const now=Date.parse('2026-10-17T00:00:00Z');
function validated(r=base){return s.validate([r],now);}
test('green day can lose money after opening; includes both cost components',()=>{
 const r=s.analyse(validated().rows);assert.equal(r.future.signal.n,1);assert.ok(r.trades[0].gap>0);assert.ok(r.trades[0].gross<0);assert.equal(r.cost,12);assert.equal(r.trades[0].net,r.trades[0].gross-12);
});
test('future US close cannot leak into the signal',()=>assert.equal(validated({...base,us_close_at:'2026-10-16T10:00:00+11:00'}).rows.length,0));
test('later futures observations are rejected',()=>assert.equal(validated({...base,spi_observed_at:'2026-10-16T10:00:00+11:00'}).rows.length,0));
test('unfinished session is not a completed trade',()=>assert.equal(s.validate([base],Date.parse(base.entry_at)).rows.length,0));
test('explicit timezone and exchange local times are required',()=>{
 assert.equal(validated({...base,entry_at:'2026-10-16T10:05:00'}).rows.length,0);
 assert.equal(validated({...base,entry_at:'2026-10-16T09:35:00+10:30'}).rows.length,1);
 assert.equal(validated({...base,entry_at:'2026-10-16T10:05:00+10:30'}).rows.length,0);
});
test('duplicate dates, blank prices, mixed symbols and missing source do not enter results',()=>{
 assert.equal(s.validate([base,base],now).errors.length,1);
 assert.equal(validated({...base,entry_price:''}).rows.length,0);
 assert.equal(validated({...base,source:''}).rows.length,0);
 assert.equal(s.validate([base,{...base,symbol:'VAS.AX'}],now).errors.length,1);
});
test('CSV quoting, BOM, missing headers and malformed rows',()=>{
 const values=s.fields.map(k=>k==='source'?'"Provider, quoted"':base[k]);
 const parsed=s.csv('\uFEFF'+s.fields.join(',')+'\r\n'+values.join(','));assert.equal(parsed[0].source,'Provider, quoted');
 assert.throws(()=>s.csv('date,price\n2026-01-01,2'),/Missing column/);
 assert.throws(()=>s.csv(s.fields.join(',')+'\n1,2'),/incorrect number/);
 assert.throws(()=>s.csv('"bad'),/unclosed quote/);
});
test('signal threshold and comparator groups use the same entry and exit',()=>{
 const a=validated().rows[0];const rows=[a,{...a,session_date:'2026-10-15',spi_change_pct:0.49},{...a,session_date:'2026-10-14',us_return_pct:0}];
 const r=s.analyse(rows);assert.equal(r.future.signal.n,1);assert.equal(r.history.signal.n,0);assert.equal(r.history.other.n,2);assert.equal(r.history.all.n,2);
});
test('empty groups show no result and drawdown follows cumulative losses',()=>{
 assert.equal(s.stats([]).mean,null);const st=s.stats([{net:10},{net:-20},{net:5},{net:-2}]);assert.equal(st.drawdown,-20);assert.equal(st.averageWin,7.5);assert.equal(st.averageLoss,-11);assert.equal(st.sum,-7);
});
test('invalid costs rejected rather than converted to free trading',()=>{assert.throws(()=>s.analyse([],{capital:2000,brokerage:-1}));assert.throws(()=>s.analyse([],{capital:NaN}));});
