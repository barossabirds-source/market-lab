import streamlit as st
import pandas as pd
import plotly.express as px
from engine import load_prices, strategy_leaderboard

st.set_page_config(page_title="Market Lab",page_icon="📈",layout="wide")
st.title("Market Lab")
st.caption("Systematic ETF research lab • paper trading only")

@st.cache_data(ttl=3600)
def research():
    prices=load_prices()
    return prices,strategy_leaderboard(prices)

with st.spinner("Downloading prices and testing every candidate pair..."):
    prices,results=research()

c1,c2,c3,c4=st.columns(4)
c1.metric("ETFs",len(prices.columns))
c2.metric("Pairs tested",len(results))
c3.metric("Paper-test candidates",sum(r["status"]=="PAPER TEST" for r in results))
c4.metric("Latest data",str(prices.index.max().date()))

st.subheader("Strategy leaderboard")
if not results:
    st.warning("No candidate pairs met the correlation threshold.")
    st.stop()

table=pd.DataFrame([{k:r[k] for k in ["pair","correlation","adf_p","stationary","test_return","trades","win_rate","sharpe","max_dd","avg_days","status"]} for r in results])
show=table.copy()
for col in ["correlation","adf_p","sharpe"]: show[col]=show[col].map(lambda x:f"{x:.3f}")
for col in ["test_return","win_rate","max_dd"]: show[col]=show[col].map(lambda x:f"{x:.2%}")
show["avg_days"]=show["avg_days"].map(lambda x:f"{x:.1f}")
show.columns=["Pair","Correlation","ADF p","Stationary?","Test return","Trades","Win rate","Sharpe","Max DD","Avg days","Status"]
st.dataframe(show,use_container_width=True,hide_index=True)

st.caption("ADF p < 0.05 is evidence the training-period spread was stationary. Results are ranked from unseen out-of-sample data, not the training period.")

pick=st.selectbox("Inspect strategy",[r["pair"] for r in results])
r=next(x for x in results if x["pair"]==pick)
pf=r["test_frame"]; bt=r["test_result"]

m1,m2,m3,m4,m5=st.columns(5)
m1.metric("Out-of-sample return",f"{r['test_return']:.2%}")
m2.metric("Completed trades",r["trades"])
m3.metric("Win rate",f"{r['win_rate']:.1%}")
m4.metric("Sharpe",f"{r['sharpe']:.2f}")
m5.metric("Max drawdown",f"{r['max_dd']:.2%}")

st.subheader("Out-of-sample z-score")
fig=px.line(pf.reset_index(),x=pf.index.name or "Date",y="z")
fig.add_hline(y=2,line_dash="dash"); fig.add_hline(y=-2,line_dash="dash"); fig.add_hline(y=0,line_dash="dot")
st.plotly_chart(fig,use_container_width=True)

st.subheader("Out-of-sample simulated equity")
eq=bt["equity"].reset_index()
st.plotly_chart(px.line(eq,x="date",y="equity"),use_container_width=True)

st.subheader("Completed trades")
if bt["trades"].empty: st.info("No completed trades in the test period.")
else: st.dataframe(bt["trades"],use_container_width=True,hide_index=True)

with st.expander("How to read the status"):
    st.markdown("""
**PAPER TEST** means the training spread passed the stationarity test and the unseen test period had at least 3 completed trades, positive return and positive Sharpe. It is a research filter, not a recommendation.

**RESEARCH** means there is not enough evidence yet.

**REJECTED** means the simple version failed a basic research rule. Rejected strategies can still behave differently under other specifications.
""")

st.info("Research mode only. No brokerage connection and no live orders. Backtests can overstate real-world performance.")
