/* Converts completed ASX study trades to evidence-gate input.
   Never asserts provenance, preregistration or point-in-time integrity. */
(function(root) {
  'use strict';
  function fromAsx(analysis, options) {
    const signalTrades = analysis.trades.filter(t => t.signal && t.session_date >= '2026-10-16');
    const capital = Number(options.capital);
    if (!(capital > 0)) throw Error('Capital must be positive');
    // ASXStudy already subtracts brokerage and friction from each trade.
    // Gate receives gross returns and the identical total round-trip cost once.
    const grossReturns = signalTrades.map(t => t.gross / capital);
    const costBps = analysis.cost / capital * 10000;
    return {
      returns:grossReturns, costBps,
      freezeDate:'2026-10-16',
      firstDate:signalTrades.length ? signalTrades[0].session_date : '',
      provenance:options.provenance || '',
      pointInTime:options.pointInTime === true,
      noSignalSessions:options.noSignalSessions === true,
      oosCount:options.oosCount || 0
    };
  }
  function assessAsx(analysis, options) {
    return root.MarketLabResearchGate.evaluate(fromAsx(analysis,options));
  }
  const api={fromAsx,assessAsx};
  if(typeof module!=='undefined' && module.exports) module.exports=api;
  else root.MarketLabGateAdapters=api;
})(typeof window!=='undefined'?window:globalThis);
