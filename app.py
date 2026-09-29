import streamlit as st
import pandas as pd
import plotly.express as px
from engine import load_prices, strategy_leaderboard, forward_dashboard, model_comparison_dashboard, forward_long_only_dashboard
from event_study import trump_event_study, trump_theme_summary, source_direction_summary, surprise_summary, timing_summary

st.set_page_config(page_title="Market Lab V6", page_icon="🧪", layout="wide")
st.title("Market Lab V6")
st.caption("Systematic ETF research + forward paper trading + public-event studies")

CACHE_SCHEMA = "v6.3"

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

with st.expander("Historical validation methodology"):
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


st.divider()
st.subheader("Pairs vs long-only")
st.caption("Same signals, same ETFs, same historical periods. The only difference is execution: hedge both legs, or buy only the relatively cheaper ETF.")

comparisons=model_comparison_dashboard(prices)
comparison_rows=[]
for c in comparisons:
    comparison_rows.extend([
        {"Pair":c["pair"],"Model":"Pairs trade","Development return":f'{c["pairs_dev"]["return"]:.2%}',
         "Dev trades":c["pairs_dev"]["trades"],"Holdout return":f'{c["pairs_hold"]["return"]:.2%}',
         "Holdout trades":c["pairs_hold"]["trades"],"Holdout Sharpe":f'{c["pairs_hold"]["sharpe"]:.2f}',
         "Holdout max DD":f'{c["pairs_hold"]["max_dd"]:.2%}'},
        {"Pair":c["pair"],"Model":"Long-only","Development return":f'{c["long_dev"]["return"]:.2%}',
         "Dev trades":c["long_dev"]["trades"],"Holdout return":f'{c["long_hold"]["return"]:.2%}',
         "Holdout trades":c["long_hold"]["trades"],"Holdout Sharpe":f'{c["long_hold"]["sharpe"]:.2f}',
         "Holdout max DD":f'{c["long_hold"]["max_dd"]:.2%}'},
    ])
st.dataframe(pd.DataFrame(comparison_rows),use_container_width=True,hide_index=True)
st.caption("The long-only model was introduced after the original pairs holdout had already been viewed, so treat its historical comparison as exploratory. The clean test is forward performance from 29 Sep 2026 onward.")

st.subheader("Forward long-only paper trading")
st.caption("When z ≤ -2, buy ETF A. When z ≥ +2, buy ETF B. Sell when the relationship returns inside ±0.5.")

long_forward=forward_long_only_dashboard(prices)
lfrows=[]
for x in long_forward:
    lfrows.append({
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
st.dataframe(pd.DataFrame(lfrows),use_container_width=True,hide_index=True)

lpick=st.selectbox("Inspect long-only forward strategy",[x["pair"] for x in long_forward],key="long_forward_pair")
lx=next(x for x in long_forward if x["pair"]==lpick)
lc1,lc2,lc3,lc4=st.columns(4)
lc1.metric("Current z-score",f'{lx["latest_z"]:.2f}')
lc2.metric("Current position",lx["position"])
lc3.metric("Forward return",f'{lx["return"]:.2%}')
lc4.metric("Completed trades",lx["trades"])

if len(lx["equity_curve"]):
    le=lx["equity_curve"].reset_index()
    st.plotly_chart(px.line(le,x="date",y="equity",title="Long-only forward paper equity"),use_container_width=True)

if len(lx["trade_log"]):
    st.subheader("Long-only trade log")
    st.dataframe(lx["trade_log"],use_container_width=True,hide_index=True)

with st.expander("Long-only model in plain English"):
    st.markdown("""
If one ETF becomes unusually cheap relative to its partner, Market Lab buys only that ETF. It does **not** short the expensive ETF.

Example: if IWF looks unusually cheap relative to SPY, the model paper-buys IWF. When the relationship moves back near normal, it paper-sells IWF.

This is simpler to execute, but unlike the pairs trade it remains exposed to the direction of the overall stock market.
""")


st.divider()
st.subheader("Trump public-event study")
st.caption("Exploratory event research using source type, direction, timing, a transparent surprise proxy and pre-event price drift.")

study=trump_event_study(prices)
if not study.empty:
    ec1,ec2,ec3,ec4=st.columns(4)
    ec1.metric("Events in corpus",study["date"].nunique())
    ec2.metric("Themes",study["theme"].nunique())
    ec3.metric("Public comments/interviews",study.loc[study["source_type"]!="formal_action","date"].nunique())
    ec4.metric("ETF-event observations",len(study))

if study.empty:
    st.info("No event-study results are available yet.")
else:
    h=st.selectbox("Event-study horizon",[1,3,5],index=0,format_func=lambda x:f"{x} trading day{'s' if x>1 else ''}",key="trump_horizon")

    f1,f2,f3,f4=st.columns(4)
    source_filter=f1.multiselect("Source type",sorted(study["source_type"].unique()),default=sorted(study["source_type"].unique()))
    direction_filter=f2.multiselect("Direction",sorted(study["direction"].unique()),default=sorted(study["direction"].unique()))
    surprise_filter=f3.multiselect("Surprise proxy",sorted(study["surprise_proxy"].unique()),default=sorted(study["surprise_proxy"].unique()))
    timing_filter=f4.multiselect("Market timing",sorted(study["market_session"].unique()),default=sorted(study["market_session"].unique()))

    filtered=study[
        study["source_type"].isin(source_filter) &
        study["direction"].isin(direction_filter) &
        study["surprise_proxy"].isin(surprise_filter) &
        study["market_session"].isin(timing_filter)
    ].copy()

    st.subheader("Theme / ETF reaction")
    summary=trump_theme_summary(filtered,h)
    if summary.empty:
        st.info("No observations match the current filters.")
    else:
        show=summary.copy()
        for src,dst in [
            ("avg_abnormal","Avg abnormal return"),
            ("median_abnormal","Median abnormal return"),
            ("positive_rate","Positive rate"),
            ("avg_pre_1d","Avg pre-event 1d"),
            ("avg_pre_3d","Avg pre-event 3d"),
        ]:
            show[dst]=show[src].map(lambda x:"—" if pd.isna(x) else f"{x:.2%}")
        show=show[["theme","ticker","events","observations","Avg abnormal return","Median abnormal return","Positive rate","Avg pre-event 1d","Avg pre-event 3d"]]
        show.columns=["Theme","ETF","Events","Obs","Avg abnormal return","Median abnormal return","Positive rate","Pre-event 1d","Pre-event 3d"]
        st.dataframe(show,use_container_width=True,hide_index=True)

    st.caption("Abnormal return means ETF return minus SPY over the same period. Pre-event columns help show whether the move had already begun before the event.")

    st.subheader("Does source, direction or surprise matter?")
    tab1,tab2,tab3=st.tabs(["Source + direction","Surprise proxy","Market timing"])
    with tab1:
        s=source_direction_summary(filtered,h)
        if len(s):
            sv=s.copy()
            sv["Avg abnormal return"]=sv["avg_abnormal"].map(lambda x:f"{x:.2%}")
            sv["Positive rate"]=sv["positive_rate"].map(lambda x:f"{x:.0%}")
            st.dataframe(sv[["source_type","direction","events","observations","Avg abnormal return","Positive rate"]],use_container_width=True,hide_index=True)
    with tab2:
        s=surprise_summary(filtered,h)
        if len(s):
            sv=s.copy()
            sv["Avg abnormal return"]=sv["avg_abnormal"].map(lambda x:f"{x:.2%}")
            sv["Positive rate"]=sv["positive_rate"].map(lambda x:f"{x:.0%}")
            st.dataframe(sv[["surprise_proxy","events","observations","Avg abnormal return","Positive rate"]],use_container_width=True,hide_index=True)
        st.caption("Surprise is a transparent research proxy: high = materially new action; medium = modification/extension/sector support; low = remarks or reiteration without a separately verified new action.")
    with tab3:
        s=timing_summary(filtered,h)
        if len(s):
            sv=s.copy()
            sv["Avg abnormal return"]=sv["avg_abnormal"].map(lambda x:f"{x:.2%}")
            sv["Positive rate"]=sv["positive_rate"].map(lambda x:f"{x:.0%}")
            st.dataframe(sv[["market_session","events","observations","Avg abnormal return","Positive rate"]],use_container_width=True,hide_index=True)
        st.caption("Most older sources provide a date but not a verified time, so they remain tagged 'unknown' rather than being guessed.")

    st.subheader("Individual events")
    events_view=filtered[["date","source_type","theme","direction","surprise_proxy","market_session","timing_confidence","summary"]].drop_duplicates().sort_values("date",ascending=False)
    st.dataframe(events_view,use_container_width=True,hide_index=True)

    if len(events_view):
        choices=[f"{row.date.date()} | {row.theme} | {row.source_type}" for _,row in events_view.iterrows()]
        chosen=st.selectbox("Inspect event",choices,key="trump_event_choice_smart")
        chosen_idx=choices.index(chosen)
        chosen_date=events_view.iloc[chosen_idx]["date"]
        chosen_theme=events_view.iloc[chosen_idx]["theme"]
        d=filtered[(filtered["date"]==chosen_date)&(filtered["theme"]==chosen_theme)].copy()
        d[f"abn_{h}d_pct"]=d[f"abn_{h}d"]*100
        st.plotly_chart(
            px.bar(d.sort_values(f"abn_{h}d"),x="ticker",y=f"abn_{h}d_pct",
                   labels={"ticker":"ETF",f"abn_{h}d_pct":"Abnormal return (%)"},
                   title=f"ETF reaction vs SPY after {h} trading day{'s' if h>1 else ''}"),
            use_container_width=True
        )

    with st.expander("Methodology and limitations"):
        st.markdown("""
**Direction** describes the event content, such as escalation, de-escalation, sector support or mixed.

**Surprise proxy** is deliberately rule-based rather than a claim about investor psychology. A materially new action is tagged high; a modification, extension or sector-support action is medium; remarks without a separately verified new action are low.

**Timing** is only assigned when the source gives enough information. Unknown events stay unknown. Daily ETF data cannot cleanly isolate a comment made halfway through the trading session, so timing-based results should be treated cautiously.

**Pre-event drift** compares the ETF with SPY before the event. If the ETF was already moving strongly beforehand, that weakens the case that the event itself explains the subsequent move.

This remains descriptive research. It does not establish causation or a reliable trading rule.
""")

