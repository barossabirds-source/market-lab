import streamlit as st
import pandas as pd
import plotly.express as px
from engine import load_prices, discover_pairs, pair_frame, backtest_pair

st.set_page_config(page_title="Market Lab", page_icon="📈", layout="wide")
st.title("Market Lab")
st.caption("US ETF pairs research and paper-trading lab")

@st.cache_data(ttl=3600)
def get_prices():
    return load_prices()

with st.spinner("Loading market data..."):
    prices=get_prices()

pairs=discover_pairs(prices)
pair_df=pd.DataFrame(pairs,columns=["ETF A","ETF B","Correlation"])

c1,c2,c3=st.columns(3)
c1.metric("ETFs", len(prices.columns))
c2.metric("Candidate pairs", len(pair_df))
c3.metric("Latest data", str(prices.index.max().date()))

st.subheader("Candidate pairs")
st.dataframe(pair_df, use_container_width=True, hide_index=True)

if not pair_df.empty:
    labels=[f"{r['ETF A']} / {r['ETF B']}" for _,r in pair_df.iterrows()]
    pick=st.selectbox("Analyse pair", labels)
    a,b=[x.strip() for x in pick.split("/")]

    pf=pair_frame(prices,a,b)
    result=backtest_pair(pf)

    m1,m2,m3=st.columns(3)
    m1.metric("Backtest return", f"{result['total_return']*100:.2f}%")
    m2.metric("Max drawdown", f"{result['max_drawdown']*100:.2f}%")
    m3.metric("Open position", result["open_position"])

    st.subheader("Spread z-score")
    zchart=px.line(pf.reset_index(),x=pf.index.name or "Date",y="z")
    st.plotly_chart(zchart,use_container_width=True)

    st.subheader("Simulated equity")
    eq=result["equity"].reset_index()
    echart=px.line(eq,x="date",y="equity")
    st.plotly_chart(echart,use_container_width=True)

    st.subheader("Trade events")
    st.dataframe(result["events"],use_container_width=True,hide_index=True)
else:
    st.warning("No candidate pairs met the correlation threshold.")

st.info("Research mode only. No live brokerage connection and no live order placement.")
