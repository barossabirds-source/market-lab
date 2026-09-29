from __future__ import annotations
import numpy as np
import pandas as pd
import yfinance as yf
from itertools import combinations
from statsmodels.tsa.stattools import adfuller
from config import *

def load_prices(tickers=ETF_UNIVERSE, period="5y"):
    data=yf.download(tickers,period=period,auto_adjust=True,progress=False,threads=True)["Close"]
    if isinstance(data,pd.Series): data=data.to_frame()
    return data.dropna(axis=1,thresh=int(len(data)*0.90)).ffill().dropna()

def discover_pairs(prices,min_corr=PAIR_CORRELATION_MIN):
    rets=np.log(prices/prices.shift(1)).dropna(); corr=rets.corr(); rows=[]
    for a,b in combinations(prices.columns,2):
        c=float(corr.loc[a,b])
        if c>=min_corr: rows.append((a,b,c))
    return sorted(rows,key=lambda x:x[2],reverse=True)

def pair_frame(prices,a,b,window=ROLLING_WINDOW):
    x=np.log(prices[a]); y=np.log(prices[b])
    beta=x.rolling(window).cov(y)/y.rolling(window).var()
    spread=x-beta*y; mu=spread.rolling(window).mean(); sd=spread.rolling(window).std()
    return pd.DataFrame({"a":prices[a],"b":prices[b],"beta":beta,"spread":spread,"z":(spread-mu)/sd}).replace([np.inf,-np.inf],np.nan).dropna()

def adf_pvalue(s):
    try: return float(adfuller(s.dropna(),autolag="AIC")[1])
    except Exception: return np.nan

def backtest_pair(df,initial_capital=INITIAL_CAPITAL):
    pos=0; equity=initial_capital; peak=equity; prev=None; entry_eq=None; entry_dt=None
    events=[]; completed=[]; daily=[]; alloc=initial_capital*POSITION_FRACTION; half_cost=alloc*(ROUND_TRIP_COST_BPS/10000)/2
    for dt,row in df.iterrows():
        z=float(row.z)
        if prev is not None and pos:
            equity+=alloc*(pos*(row.a/prev.a-1)-pos*float(row.beta)*(row.b/prev.b-1))
        if pos==0 and abs(z)>=Z_ENTRY:
            pos=-1 if z>0 else 1; equity-=half_cost; entry_eq=equity; entry_dt=dt
            events.append({"date":dt,"event":"ENTRY","side":"short spread" if pos<0 else "long spread","z":z,"equity":equity})
        elif pos and abs(z)<=Z_EXIT:
            equity-=half_cost; pnl=equity-entry_eq
            completed.append({"entry":entry_dt,"exit":dt,"pnl":pnl,"holding_days":(dt-entry_dt).days})
            events.append({"date":dt,"event":"EXIT","side":"close","z":z,"equity":equity})
            pos=0; entry_eq=None; entry_dt=None
        peak=max(peak,equity); daily.append({"date":dt,"equity":equity,"drawdown":equity/peak-1}); prev=row
    eq=pd.DataFrame(daily).set_index("date"); tr=pd.DataFrame(completed); dr=eq.equity.pct_change().dropna()
    sharpe=float(np.sqrt(252)*dr.mean()/dr.std()) if len(dr)>2 and dr.std()>0 else 0.0
    gross_profit=float(tr.loc[tr.pnl>0,"pnl"].sum()) if not tr.empty else 0
    gross_loss=abs(float(tr.loc[tr.pnl<0,"pnl"].sum())) if not tr.empty else 0
    pf=gross_profit/gross_loss if gross_loss>0 else (np.inf if gross_profit>0 else 0)
    return {"equity":eq,"events":pd.DataFrame(events),"trades":tr,"total_return":equity/initial_capital-1,
      "max_drawdown":float(eq.drawdown.min()) if len(eq) else 0,"sharpe":sharpe,"completed_trades":len(tr),
      "win_rate":float((tr.pnl>0).mean()) if len(tr) else 0,"profit_factor":pf,
      "avg_holding_days":float(tr.holding_days.mean()) if len(tr) else 0}

def walk_forward(prices,a,b,n_windows=WALK_FORWARD_WINDOWS):
    n=len(prices); min_train=max(ROLLING_WINDOW*4,int(n*0.45)); remaining=n-min_train
    step=max(60,remaining//n_windows); windows=[]
    for i in range(n_windows):
        train_end=min_train+i*step; test_end=min(n,train_end+step)
        if test_end-train_end<30: break
        train=prices.iloc[:train_end]; test=prices.iloc[max(0,train_end-ROLLING_WINDOW*2):test_end]
        train_pf=pair_frame(train,a,b); test_pf=pair_frame(test,a,b)
        if len(train_pf)<60 or len(test_pf)<20: continue
        p=adf_pvalue(train_pf.spread); bt=backtest_pair(test_pf)
        windows.append({"window":i+1,"start":prices.index[train_end],"end":prices.index[test_end-1],
          "adf_p":p,"stationary":bool(p<.05),"return":bt["total_return"],"trades":bt["completed_trades"],
          "win_rate":bt["win_rate"],"sharpe":bt["sharpe"],"max_dd":bt["max_drawdown"],"profit_factor":bt["profit_factor"]})
    return windows

def evaluate_pair(prices,a,b,corr):
    wf=walk_forward(prices,a,b)
    if not wf: raise ValueError("No validation windows")
    w=pd.DataFrame(wf); total_trades=int(w.trades.sum()); positive=int((w["return"]>0).sum())
    stationary_rate=float(w.stationary.mean()); avg_return=float(w["return"].mean())
    compound=float(np.prod(1+w["return"])-1); avg_sharpe=float(w.sharpe.mean()); worst_dd=float(w.max_dd.min())
    finite_pf=w.profit_factor.replace([np.inf,-np.inf],np.nan).dropna()
    pf=float(finite_pf.mean()) if len(finite_pf) else np.inf
    consistency=positive/len(w)
    status="RESEARCH"
    if stationary_rate>=.60 and total_trades>=MIN_TEST_TRADES and compound>0 and consistency>=.60 and avg_sharpe>0: status="PAPER TEST"
    if compound<-.02 or consistency<.40 or stationary_rate<.40: status="REJECTED"
    return {"pair":f"{a} / {b}","correlation":corr,"wf_return":compound,"avg_window_return":avg_return,
      "trades":total_trades,"consistency":consistency,"stationary_rate":stationary_rate,"sharpe":avg_sharpe,
      "max_dd":worst_dd,"profit_factor":pf,"status":status,"windows":w}

def strategy_leaderboard(prices,max_pairs=80):
    rows=[]
    for a,b,c in discover_pairs(prices)[:max_pairs]:
        try: rows.append(evaluate_pair(prices,a,b,c))
        except Exception: pass
    order={"PAPER TEST":2,"RESEARCH":1,"REJECTED":0}
    return sorted(rows,key=lambda r:(order[r["status"]],r["consistency"],r["wf_return"],r["sharpe"]),reverse=True)
