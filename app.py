import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
from engine import load_prices,strategy_leaderboard

st.set_page_config(page_title="Market Lab V3",page_icon="📈",layout="wide")
st.title("Market Lab V3")
st.caption("Walk-forward ETF strategy validation • paper research only")

@st.cache_data(ttl=3600)
def research():
    p=load_prices(); return p,strategy_leaderboard(p)

with st.spinner("Testing a larger ETF universe across multiple unseen windows..."):
    prices,results=research()

c1,c2,c3,c4=st.columns(4)
c1.metric("ETFs loaded",len(prices.columns)); c2.metric("Pairs validated",len(results))
c3.metric("Paper-test candidates",sum(r["status"]=="PAPER TEST" for r in results)); c4.metric("Latest data",str(prices.index.max().date()))

st.subheader("Walk-forward leaderboard")
if not results: st.warning("No strategies could be validated."); st.stop()
rows=[]
for r in results:
    rows.append({"Pair":r["pair"],"Correlation":f'{r["correlation"]:.3f}',"WF return":f'{r["wf_return"]:.2%}',
      "Trades":r["trades"],"Positive windows":f'{r["consistency"]:.0%}',"Stationary windows":f'{r["stationary_rate"]:.0%}',
      "Avg Sharpe":f'{r["sharpe"]:.2f}',"Worst DD":f'{r["max_dd"]:.2%}',
      "Profit factor":"∞" if np.isinf(r["profit_factor"]) else f'{r["profit_factor"]:.2f}',"Status":r["status"]})
st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
st.caption("Walk-forward return compounds separate unseen test windows. Positive windows shows how often the strategy made money rather than relying on one lucky period.")

pick=st.selectbox("Inspect strategy",[r["pair"] for r in results]); r=next(x for x in results if x["pair"]==pick); w=r["windows"].copy()
m1,m2,m3,m4,m5=st.columns(5)
m1.metric("Walk-forward return",f'{r["wf_return"]:.2%}'); m2.metric("Trades",r["trades"])
m3.metric("Positive windows",f'{r["consistency"]:.0%}'); m4.metric("Stationary windows",f'{r["stationary_rate"]:.0%}'); m5.metric("Worst DD",f'{r["max_dd"]:.2%}')

st.subheader("Performance by unseen window")
chart=w[["window","return"]].copy(); chart["return_pct"]=chart["return"]*100
st.plotly_chart(px.bar(chart,x="window",y="return_pct",labels={"window":"Validation window","return_pct":"Return (%)"}),use_container_width=True)

display=w.copy()
for col in ["return","win_rate","max_dd"]: display[col]=display[col].map(lambda x:f"{x:.2%}")
display["adf_p"]=display["adf_p"].map(lambda x:f"{x:.3f}")
display["sharpe"]=display["sharpe"].map(lambda x:f"{x:.2f}")
display["profit_factor"]=display["profit_factor"].map(lambda x:"∞" if np.isinf(x) else f"{x:.2f}")
st.dataframe(display,use_container_width=True,hide_index=True)

with st.expander("What V3 is doing"):
    st.markdown("""
Market Lab now downloads about five years of data for a broader liquid ETF universe. Candidate pairs first need sufficiently correlated daily returns. Each pair is then tested repeatedly using expanding historical training data followed by a genuinely later test window.

A **PAPER TEST** label requires the relationship to be stationary in most training windows, enough completed trades, positive compounded walk-forward performance, positive performance in most unseen windows and a positive average Sharpe. This is a research gate, not a trading recommendation.
""")
st.info("No brokerage connection. No live orders. Historical and paper results do not establish future profitability.")
