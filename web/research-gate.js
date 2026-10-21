(function(root) {
  function evaluate(p) {
    const reasons = [];
    if (!Array.isArray(p.returns) || !p.returns.length || p.returns.some(v => !Number.isFinite(v))) reasons.push('Invalid returns');
    if (!Number.isFinite(p.costBps) || p.costBps < 0) reasons.push('Invalid costs');
    if (!p.freezeDate || !p.firstDate || p.firstDate <= p.freezeDate) reasons.push('Rule must be frozen first');
    if (!p.provenance || !String(p.provenance).trim()) reasons.push('Missing provenance');
    if (p.pointInTime !== true) reasons.push('Timing not verified');
    if (p.noSignalSessions !== true) reasons.push('Comparator missing');
    if (!Number.isInteger(p.oosCount) || p.oosCount < 30 || p.oosCount > p.returns.length) reasons.push('Insufficient out-of-sample evidence');
    if (reasons.length) return {status:'insufficient_evidence',reasons};
    const net = p.returns.map(v => v - p.costBps / 10000);
    const meanNet = net.reduce((a,b)=>a+b,0)/net.length;
    return {status:meanNet>0?'research_candidate':'not_promising',reasons:[meanNet>0?'Forward validation required':'Non-positive mean net return'],meanNet,winRate:net.filter(v=>v>0).length/net.length};
  }
  root.MarketLabResearchGate = {evaluate};
})(typeof window !== 'undefined' ? window : module.exports);
