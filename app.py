import streamlit as st, pandas as pd, plotly.express as px
from engine import load_prices,strategy_leaderboard

st.set_page_config(page_title="Market Lab V4",page_icon="🧪",layout="wide")
st.title("Market Lab V4")
st.caption("Adversarial validation • longer history • cost stress • parameter sensitivity • untouched holdout")

@st.cache_data(ttl=3600)
def research():
    p=load_prices(); return p,strategy_leaderboard(p)

with st.spinner("Trying to break the strategies... this version does substantially more work."):
    prices,results=research()

c1,c2,c3,c4=st.columns(4)
c1.metric("ETFs loaded",len(prices.columns)); c2.metric("Pairs stress-tested",len(results))
c3.metric("Holdout-ready",sum(r["status"]=="HOLDOUT READY" for r in results)); c4.metric("History start",str(prices.index.min().date()))

st.subheader("Development leaderboard")
rows=[]
for r in results:
    rows.append({"Pair":r["pair"],"Dev WF return":f'{r["dev_return"]:.2%}',"Trades":r["trades"],
      "Positive windows":f'{r["consistency"]:.0%}',"Stationary":f'{r["stationary_rate"]:.0%}',
      "Avg Sharpe":f'{r["sharpe"]:.2f}',"Worst DD":f'{r["max_dd"]:.2%}',"Parameter pass":f'{r["parameter_pass"]:.0%}',
      "8 bps":f'{r["cost8"]:.2%}',"15 bps":f'{r["cost15"]:.2%}',"25 bps":f'{r["cost25"]:.2%}',"Status":r["status"]})
st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
st.caption("The final 15% of history is excluded from these selection metrics. HOLDOUT READY means the strategy survived walk-forward, stationarity, parameter and 25-bps cost stress gates.")

ready=[r for r in results if r["status"]=="HOLDOUT READY"]
st.subheader("Final holdout")
if not ready:
    st.info("No strategy earned access to the final holdout. That is a valid research result.")
else:
    st.warning("These results are from the final untouched historical period. Do not tune the model to improve them after viewing.")
    hrows=[]
    for r in ready:
        h=r["holdout"]; hrows.append({"Pair":r["pair"],"Holdout return":f'{h["return"]:.2%}',"Trades":h["trades"],
          "Win rate":f'{h["win_rate"]:.0%}',"Sharpe":f'{h["sharpe"]:.2f}',"Max DD":f'{h["max_dd"]:.2%}',"Profit factor":f'{h["profit_factor"]:.2f}'})
    st.dataframe(pd.DataFrame(hrows),use_container_width=True,hide_index=True)

pick=st.selectbox("Inspect development windows",[r["pair"] for r in results])
r=next(x for x in results if x["pair"]==pick); w=r["windows"].copy(); w["return_pct"]=w["return"]*100
st.plotly_chart(px.bar(w,x="window",y="return_pct",labels={"window":"Walk-forward window","return_pct":"Return (%)"}),use_container_width=True)

with st.expander("V4 methodology"):
    st.markdown("""
**Longer history:** up to ten years where ETF history permits.

**Cost stress:** every candidate is retested at 8, 15 and 25 basis points round-trip.

**Parameter sensitivity:** the same idea must remain positive across several entry/exit z-score settings. This reduces dependence on one lucky parameter choice.

**Final holdout:** the last 15% of history is withheld from the development leaderboard. Only strategies passing all development gates are shown against it.

The next step for a strategy that survives is forward paper trading on genuinely new market data, not further optimisation against the holdout.
""")
st.info("Research software only. No brokerage connection or live orders. Historical performance does not establish future profitability.")
