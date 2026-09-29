from __future__ import annotations
import numpy as np, pandas as pd, yfinance as yf
from itertools import combinations
from statsmodels.tsa.stattools import adfuller
from config import *

def load_prices(tickers=ETF_UNIVERSE,period="10y"):
    d=yf.download(tickers,period=period,auto_adjust=True,progress=False,threads=True)["Close"]
    if isinstance(d,pd.Series): d=d.to_frame()
    return d.dropna(axis=1,thresh=int(len(d)*.80)).ffill().dropna()

def discover_pairs(prices,min_corr=PAIR_CORRELATION_MIN):
    r=np.log(prices/prices.shift(1)).dropna(); c=r.corr(); out=[]
    for a,b in combinations(prices.columns,2):
        v=float(c.loc[a,b])
        if v>=min_corr: out.append((a,b,v))
    return sorted(out,key=lambda x:x[2],reverse=True)

def pair_frame(prices,a,b,window=ROLLING_WINDOW):
    x=np.log(prices[a]); y=np.log(prices[b]); beta=x.rolling(window).cov(y)/y.rolling(window).var()
    s=x-beta*y; mu=s.rolling(window).mean(); sd=s.rolling(window).std()
    return pd.DataFrame({"a":prices[a],"b":prices[b],"beta":beta,"spread":s,"z":(s-mu)/sd}).replace([np.inf,-np.inf],np.nan).dropna()

def adf_pvalue(s):
    try:return float(adfuller(s.dropna(),autolag="AIC")[1])
    except:return np.nan

def backtest(df,entry=2.0,exit=0.5,cost_bps=BASE_COST_BPS):
    pos=0; eq=INITIAL_CAPITAL; peak=eq; prev=None; ee=None; ed=None; daily=[]; tr=[]
    alloc=INITIAL_CAPITAL*POSITION_FRACTION; half=alloc*(cost_bps/10000)/2
    for dt,row in df.iterrows():
        z=float(row.z)
        if prev is not None and pos:
            eq+=alloc*(pos*(row.a/prev.a-1)-pos*float(row.beta)*(row.b/prev.b-1))
        if pos==0 and abs(z)>=entry:
            pos=-1 if z>0 else 1; eq-=half; ee=eq; ed=dt
        elif pos and abs(z)<=exit:
            eq-=half; tr.append({"entry":ed,"exit":dt,"pnl":eq-ee,"days":(dt-ed).days}); pos=0; ee=None; ed=None
        peak=max(peak,eq); daily.append((dt,eq,eq/peak-1)); prev=row
    q=pd.DataFrame(daily,columns=["date","equity","drawdown"]).set_index("date"); t=pd.DataFrame(tr); dr=q.equity.pct_change().dropna()
    sh=float(np.sqrt(252)*dr.mean()/dr.std()) if len(dr)>2 and dr.std()>0 else 0
    gp=float(t.loc[t.pnl>0,"pnl"].sum()) if len(t) else 0; gl=abs(float(t.loc[t.pnl<0,"pnl"].sum())) if len(t) else 0
    return {"return":eq/INITIAL_CAPITAL-1,"trades":len(t),"win_rate":float((t.pnl>0).mean()) if len(t) else 0,
      "sharpe":sh,"max_dd":float(q.drawdown.min()) if len(q) else 0,"profit_factor":gp/gl if gl else (np.inf if gp else 0)}

def walk_forward(prices,a,b,entry=2.0,exit=.5,cost=BASE_COST_BPS):
    n=len(prices); min_train=max(ROLLING_WINDOW*4,int(n*.40)); usable=n-min_train; step=max(80,usable//WALK_FORWARD_WINDOWS); rows=[]
    for i in range(WALK_FORWARD_WINDOWS):
        te=min_train+i*step; end=min(n,te+step)
        if end-te<40: break
        train=prices.iloc[:te]; test=prices.iloc[max(0,te-ROLLING_WINDOW*2):end]
        pf0=pair_frame(train,a,b); pf=pair_frame(test,a,b)
        if len(pf0)<100 or len(pf)<30: continue
        bt=backtest(pf,entry,exit,cost); rows.append({"window":i+1,"adf_p":adf_pvalue(pf0.spread),"stationary":adf_pvalue(pf0.spread)<.05,**bt})
    return pd.DataFrame(rows)

def evaluate_pair(prices,a,b,corr):
    cut=int(len(prices)*(1-HOLDOUT_FRACTION)); dev=prices.iloc[:cut]; hold=prices.iloc[max(0,cut-ROLLING_WINDOW*2):]
    base=walk_forward(dev,a,b)
    if len(base)<3: raise ValueError()
    base_comp=float(np.prod(1+base["return"])-1); consistency=float((base["return"]>0).mean()); stat=float(base.stationary.mean())
    trades=int(base.trades.sum()); avg_sh=float(base.sharpe.mean()); worst=float(base.max_dd.min())
    sensitivity=[]
    for en,ex in PARAMETER_GRID:
        w=walk_forward(dev,a,b,en,ex,BASE_COST_BPS)
        if len(w): sensitivity.append(float(np.prod(1+w["return"])-1))
    parameter_pass=float(np.mean(np.array(sensitivity)>0)) if sensitivity else 0
    costs={}
    for cb in COST_STRESS_BPS:
        w=walk_forward(dev,a,b,2.0,.5,cb); costs[cb]=float(np.prod(1+w["return"])-1) if len(w) else -1
    cost_pass=costs[max(COST_STRESS_BPS)]>0
    status="RESEARCH"
    if stat>=.60 and trades>=MIN_TEST_TRADES and base_comp>0 and consistency>=.60 and avg_sh>0 and parameter_pass>=.60 and cost_pass: status="HOLDOUT READY"
    if base_comp<-.02 or consistency<.40 or stat<.40: status="REJECTED"
    # Holdout is calculated but visually gated so selection criteria remain explicit.
    hpf=pair_frame(hold,a,b); h=backtest(hpf,2.0,.5,BASE_COST_BPS)
    return {"pair":f"{a} / {b}","correlation":corr,"dev_return":base_comp,"trades":trades,"consistency":consistency,
      "stationary_rate":stat,"sharpe":avg_sh,"max_dd":worst,"parameter_pass":parameter_pass,
      "cost8":costs.get(8.0,np.nan),"cost15":costs.get(15.0,np.nan),"cost25":costs.get(25.0,np.nan),
      "status":status,"windows":base,"holdout":h}

def strategy_leaderboard(prices,max_pairs=80):
    rows=[]
    for a,b,c in discover_pairs(prices)[:max_pairs]:
        try: rows.append(evaluate_pair(prices,a,b,c))
        except: pass
    rank={"HOLDOUT READY":2,"RESEARCH":1,"REJECTED":0}
    return sorted(rows,key=lambda r:(rank[r["status"]],r["parameter_pass"],r["consistency"],r["dev_return"]),reverse=True)
