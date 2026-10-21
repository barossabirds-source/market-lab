const test=require('node:test');
const assert=require('node:assert/strict');
const gate=require('../web/research-gate.js');
const adapter=require('../web/research-gate-adapters.js');
test('ASX adapter uses only prospective signal sessions and counts costs once',()=>{
 const analysis={cost:12,trades:[
 {session_date:'2026-10-15',signal:true,gross:100,net:88},
 {session_date:'2026-10-19',signal:false,gross:50,net:38},
 {session_date:'2026-10-20',signal:true,gross:20,net:8}
 ]};
 const p=adapter.fromAsx(analysis,{capital:2000,provenance:'test source',pointInTime:false,noSignalSessions:true,oosCount:1});
 assert.deepEqual(p.returns,[0.01]);
 assert.equal(p.costBps,60);
 assert.equal(p.firstDate,'2026-10-20');
 assert.equal(gate.evaluate(p).status,'insufficient_evidence');
});
test('ASX adapter never certifies point-in-time integrity from source alone',()=>{
 const p=adapter.fromAsx({cost:0,trades:[]},{capital:1000,provenance:'CSV',oosCount:0});
 assert.equal(p.pointInTime,false);
 assert.equal(p.noSignalSessions,false);
});
