import streamlit as st
import pandas as pd
import plotly.express as px
from engine import load_prices, strategy_leaderboard, forward_dashboard

st.set_page_config(page_title="Market Lab V4", page_icon="🧪", layout="wide")
st.title("Market Lab V4")
st.caption("Adversarial validation • longer history • cost stress • parameter sensitivity • untouched holdout")

CACHE_SCHEMA = "v4.2"

@st.cache_data(ttl=3600, show_spinner=False)
def research(schema_version):
    prices = load_prices()
    return prices, strategy_leaderboard(prices)

with st.spinner("Trying to break the strategies... this version does substantially more work."):
    prices, results = research(CACHE_SCHEMA)

c1, c2, c3, c4 = st.columns(4)
c1.metric("ETFs loaded", len(prices.columns))
c2.metric("Pairs stress-tested", len(results))
c3.metric("Holdout-ready", sum(r["status"] == "HOLDOUT READY" for r in results))
c4.metric("History start", str(prices.index.min().date()))

st.subheader("Development leaderboard")
rows = []
for r in results:
    rows.append({
        "Pair": r["pair"],
        "Dev WF return": f'{r.get("dev_return", r.get("wf_return", 0.0)):.2%}',
        "Trades": r["trades"],
        "Positive windows": f'{r["consistency"]:.0%}',
        "Stationary": f'{r["stationary_rate"]:.0%}',
        "Avg Sharpe": f'{r["sharpe"]:.2f}',
        "Worst DD": f'{r["max_dd"]:.2%}',
        "Parameter pass": f'{r.get("parameter_pass", 0.0):.0%}',
        "8 bps": f'{r.get("cost8", 0.0):.2%}',
        "15 bps": f'{r.get("cost15", 0.0):.2%}',
        "25 bps": f'{r.get("cost25", 0.0):.2%}',
        "Status": r["status"],
    })

st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
st.caption("The final 15% of history is excluded from these selection metrics. HOLDOUT READY means the strategy survived walk-forward, stationarity, parameter and 25-bps cost stress gates.")

ready = [r for r in results if r["status"] == "HOLDOUT READY"]
st.subheader("Final holdout")
if not ready:
    st.info("No strategy earned access to the final holdout. That is a valid research result.")
else:
    st.warning("These results are from the final untouched historical period. Do not tune the model to improve them after viewing.")
    hrows = []
    for r in ready:
        h = r["holdout"]
        pf = h["profit_factor"]
        pf_text = "∞" if pf == float("inf") else f"{pf:.2f}"
        hrows.append({
            "Pair": r["pair"],
            "Holdout return": f'{h["return"]:.2%}',
            "Trades": h["trades"],
            "Win rate": f'{h["win_rate"]:.0%}',
            "Sharpe": f'{h["sharpe"]:.2f}',
            "Max DD": f'{h["max_dd"]:.2%}',
            "Profit factor": pf_text,
        })
    st.dataframe(pd.DataFrame(hrows), use_container_width=True, hide_index=True)

if results:
    pick = st.selectbox("Inspect development windows", [r["pair"] for r in results])
    r = next(x for x in results if x["pair"] == pick)
    w = r["windows"].copy()
    w["return_pct"] = w["return"] * 100
    st.plotly_chart(
        px.bar(w, x="window", y="return_pct",
               labels={"window": "Walk-forward window", "return_pct": "Return (%)"}),
        use_container_width=True,
    )

with st.expander("V4 methodology"):
    st.markdown("""
**Longer history:** up to ten years where ETF history permits.

**Cost stress:** every candidate is retested at 8, 15 and 25 basis points round-trip.

**Parameter sensitivity:** the same idea must remain positive across several entry/exit z-score settings.

**Final holdout:** the last 15% of history is withheld from the development leaderboard. Only strategies passing all development gates are shown against it.

The next step for a strategy that survives is forward paper trading on genuinely new market data, not further optimisation against the holdout.
""")

st.info("Research software only. No brokerage connection or live orders. Historical performance does not establish future profitability.")


st.divider()
st.subheader("Forward paper trading")
st.caption("Rules frozen on 29 Sep 2026. This section only counts market data from that date onward.")

forward = forward_dashboard(prices)
frows=[]
for x in forward:
    frows.append({
        "Pair":x["pair"],
        "Latest date":str(pd.Timestamp(x["latest_date"]).date()),
        "Latest z":f'{x["latest_z"]:.2f}',
        "Position":x["position"],
        "Signal":x["signal"],
        "Forward return":f'{x["return"]:.2%}',
        "Completed trades":x["trades"],
        "Win rate":f'{x["win_rate"]:.0%}' if x["trades"] else "—",
        "Max DD":f'{x["max_dd"]:.2%}',
    })
st.dataframe(pd.DataFrame(frows),use_container_width=True,hide_index=True)

st.caption("Until US market data exists after 29 Sep 2026, the tracker will mostly show WAIT/FLAT. That is expected.")

fpick=st.selectbox("Inspect forward strategy",[x["pair"] for x in forward],key="forward_pair")
fx=next(x for x in forward if x["pair"]==fpick)

fc1,fc2,fc3,fc4=st.columns(4)
fc1.metric("Current z-score",f'{fx["latest_z"]:.2f}')
fc2.metric("Current position",fx["position"])
fc3.metric("Forward return",f'{fx["return"]:.2%}')
fc4.metric("Completed trades",fx["trades"])

if len(fx["equity_curve"]):
    e=fx["equity_curve"].reset_index()
    st.plotly_chart(px.line(e,x="date",y="equity",title="Forward paper equity"),use_container_width=True)
else:
    st.info("No forward market days have been recorded yet.")

if len(fx["trade_log"]):
    st.subheader("Forward trade log")
    st.dataframe(fx["trade_log"],use_container_width=True,hide_index=True)

with st.expander("What happens from here"):
    st.markdown("""
The three strategies are frozen at the existing rules: entry at |z| ≥ 2.0, exit at |z| ≤ 0.5, 8 bps assumed round-trip cost, and the same position sizing used in the research engine.

Each time fresh daily market data becomes available, this section updates what the strategy *would* have done. We do not change the parameters in response to these forward results.
""")
