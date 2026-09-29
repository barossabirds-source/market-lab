from __future__ import annotations
import numpy as np
import pandas as pd
import yfinance as yf
from itertools import combinations
from config import *

def load_prices(tickers=ETF_UNIVERSE, period="3y") -> pd.DataFrame:
    data = yf.download(tickers, period=period, auto_adjust=True, progress=False)["Close"]
    if isinstance(data, pd.Series):
        data = data.to_frame()
    return data.dropna(how="all").ffill().dropna()

def discover_pairs(prices: pd.DataFrame, min_corr=PAIR_CORRELATION_MIN):
    rets = np.log(prices / prices.shift(1)).dropna()
    corr = rets.corr()
    rows=[]
    for a,b in combinations(prices.columns,2):
        c=float(corr.loc[a,b])
        if c>=min_corr:
            rows.append((a,b,c))
    return sorted(rows,key=lambda x:x[2],reverse=True)

def pair_frame(prices: pd.DataFrame, a: str, b: str, window=ROLLING_WINDOW):
    x=np.log(prices[a])
    y=np.log(prices[b])
    beta = x.rolling(window).cov(y) / y.rolling(window).var()
    spread = x - beta*y
    mean = spread.rolling(window).mean()
    std = spread.rolling(window).std()
    z=(spread-mean)/std
    return pd.DataFrame({"a":prices[a],"b":prices[b],"beta":beta,"spread":spread,"z":z}).dropna()

def backtest_pair(df: pd.DataFrame):
    position=0
    equity=INITIAL_CAPITAL
    peak=equity
    records=[]
    daily=[]
    prev=None
    cost_rate=ROUND_TRIP_COST_BPS/10000.0
    alloc=INITIAL_CAPITAL*POSITION_FRACTION

    for dt,row in df.iterrows():
        z=float(row.z)
        if prev is not None and position:
            ra=(row.a/prev.a)-1
            rb=(row.b/prev.b)-1
            pnl=alloc*(position*ra - position*float(row.beta)*rb)
            equity += pnl

        if position==0:
            if z>=Z_ENTRY:
                position=-1
                equity-=alloc*cost_rate/2
                records.append({"date":dt,"event":"ENTRY","side":"short spread","z":z,"equity":equity})
            elif z<=-Z_ENTRY:
                position=1
                equity-=alloc*cost_rate/2
                records.append({"date":dt,"event":"ENTRY","side":"long spread","z":z,"equity":equity})
        elif abs(z)<=Z_EXIT:
            equity-=alloc*cost_rate/2
            records.append({"date":dt,"event":"EXIT","side":"close","z":z,"equity":equity})
            position=0

        peak=max(peak,equity)
        daily.append({"date":dt,"equity":equity,"drawdown":equity/peak-1})
        prev=row

    eq=pd.DataFrame(daily).set_index("date")
    trades=pd.DataFrame(records)
    total_return=equity/INITIAL_CAPITAL-1
    max_dd=float(eq.drawdown.min()) if not eq.empty else 0.0
    return {"equity":eq,"events":trades,"total_return":total_return,"max_drawdown":max_dd,"open_position":position}
