from __future__ import annotations
import numpy as np
import pandas as pd
import yfinance as yf
from itertools import combinations
from scipy.stats import linregress
from statsmodels.tsa.stattools import adfuller
from config import *

def load_prices(tickers=ETF_UNIVERSE, period="3y") -> pd.DataFrame:
    data=yf.download(tickers,period=period,auto_adjust=True,progress=False)["Close"]
    if isinstance(data,pd.Series): data=data.to_frame()
    return data.dropna(how="all").ffill().dropna()

def discover_pairs(prices,min_corr=PAIR_CORRELATION_MIN):
    rets=np.log(prices/prices.shift(1)).dropna(); corr=rets.corr(); rows=[]
    for a,b in combinations(prices.columns,2):
        c=float(corr.loc[a,b])
        if c>=min_corr: rows.append((a,b,c))
    return sorted(rows,key=lambda x:x[2],reverse=True)

def pair_frame(prices,a,b,window=ROLLING_WINDOW):
    x=np.log(prices[a]); y=np.log(prices[b])
    beta=x.rolling(window).cov(y)/y.rolling(window).var()
    spread=x-beta*y; mean=spread.rolling(window).mean(); std=spread.rolling(window).std()
    return pd.DataFrame({"a":prices[a],"b":prices[b],"beta":beta,"spread":spread,"z":(spread-mean)/std}).dropna()

def adf_pvalue(spread):
    try: return float(adfuller(spread.dropna(),autolag="AIC")[1])
    except Exception: return np.nan

def backtest_pair(df,initial_capital=INITIAL_CAPITAL):
    position=0; equity=initial_capital; peak=equity; prev=None
    events=[]; daily=[]; completed=[]; entry_equity=None; entry_date=None
    cost_rate=ROUND_TRIP_COST_BPS/10000; alloc=initial_capital*POSITION_FRACTION
    for dt,row in df.iterrows():
        z=float(row.z)
        if prev is not None and position:
            ra=row.a/prev.a-1; rb=row.b/prev.b-1
            equity += alloc*(position*ra-position*float(row.beta)*rb)
        if position==0 and abs(z)>=Z_ENTRY:
            position=-1 if z>0 else 1
            equity-=alloc*cost_rate/2; entry_equity=equity; entry_date=dt
            events.append({"date":dt,"event":"ENTRY","side":"short spread" if position<0 else "long spread","z":z,"equity":equity})
        elif position and abs(z)<=Z_EXIT:
            equity-=alloc*cost_rate/2
            pnl=equity-entry_equity
            completed.append({"entry":entry_date,"exit":dt,"pnl":pnl,"holding_days":(dt-entry_date).days})
            events.append({"date":dt,"event":"EXIT","side":"close","z":z,"equity":equity})
            position=0; entry_equity=None; entry_date=None
        peak=max(peak,equity); daily.append({"date":dt,"equity":equity,"drawdown":equity/peak-1}); prev=row
    eq=pd.DataFrame(daily).set_index("date"); trades=pd.DataFrame(completed)
    daily_ret=eq.equity.pct_change().dropna()
    sharpe=float(np.sqrt(252)*daily_ret.mean()/daily_ret.std()) if len(daily_ret)>2 and daily_ret.std()>0 else 0.0
    wins=int((trades.pnl>0).sum()) if not trades.empty else 0
    return {"equity":eq,"events":pd.DataFrame(events),"trades":trades,
      "total_return":equity/initial_capital-1,
      "max_drawdown":float(eq.drawdown.min()) if not eq.empty else 0.0,
      "sharpe":sharpe,"completed_trades":len(trades),
      "win_rate":wins/len(trades) if len(trades) else 0.0,
      "avg_holding_days":float(trades.holding_days.mean()) if len(trades) else 0.0,
      "open_position":position}

def evaluate_pair(prices,a,b,correlation,train_fraction=0.70):
    split=max(ROLLING_WINDOW+5,int(len(prices)*train_fraction))
    train_prices=prices.iloc[:split]; test_start=max(0,split-ROLLING_WINDOW*2); test_prices=prices.iloc[test_start:]
    train_pf=pair_frame(train_prices,a,b); test_pf=pair_frame(test_prices,a,b)
    train=backtest_pair(train_pf); test=backtest_pair(test_pf)
    p=adf_pvalue(train_pf.spread)
    stationary=bool(p<0.05) if not np.isnan(p) else False
    status="PAPER TEST" if stationary and test["completed_trades"]>=3 and test["total_return"]>0 and test["sharpe"]>0 else "RESEARCH"
    if test["total_return"]<-0.02 or (not stationary and test["completed_trades"]>=3): status="REJECTED"
    return {"pair":f"{a} / {b}","ETF A":a,"ETF B":b,"correlation":correlation,
      "adf_p":p,"stationary":stationary,"train_return":train["total_return"],
      "test_return":test["total_return"],"trades":test["completed_trades"],
      "win_rate":test["win_rate"],"sharpe":test["sharpe"],"max_dd":test["max_drawdown"],
      "avg_days":test["avg_holding_days"],"status":status,"test_frame":test_pf,"test_result":test}

def strategy_leaderboard(prices):
    rows=[]
    for a,b,c in discover_pairs(prices):
        try: rows.append(evaluate_pair(prices,a,b,c))
        except Exception: continue
    return sorted(rows,key=lambda x:(x["status"]=="PAPER TEST",x["test_return"],x["sharpe"]),reverse=True)
