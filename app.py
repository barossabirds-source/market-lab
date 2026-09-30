import streamlit as st
import pandas as pd
import plotly.express as px
from engine import load_prices, strategy_leaderboard, forward_dashboard, model_comparison_dashboard, forward_long_only_dashboard
from event_study import trump_event_study, trump_theme_summary, source_direction_summary, surprise_summary, timing_summary

FUND_NAMES = {
    "SPY":"Broad US Market (SPY)","QQQ":"Large US Technology (QQQ)","IWF":"US Growth Shares (IWF)",
    "IWD":"US Value Shares (IWD)","MDY":"Mid-sized US Companies (MDY)","IJH":"Mid-sized US Companies (IJH)",
    "IWM":"Smaller US Companies (IWM)","XLE":"US Energy (XLE)","XLI":"US Industrials (XLI)",
    "XLB":"US Materials (XLB)","XLY":"US Consumer Discretionary (XLY)","XLV":"US Health Care (XLV)",
    "SMH":"Semiconductor Companies (SMH)","SOXX":"Semiconductor Companies (SOXX)","ITA":"US Aerospace & Defence (ITA)",
    "IBB":"Biotechnology (IBB)","XBI":"Biotechnology (XBI)"
}

def fund_name(ticker):
    return FUND_NAMES.get(ticker, ticker)

def plain_pair(pair_text):
    parts=[x.strip() for x in pair_text.split("/")]
    return " / ".join(fund_name(x) for x in parts)

def plain_status(status):
    return {"HOLDOUT READY":"Ready for final hidden test","RESEARCH":"Still being tested","REJECTED":"Did not pass"}.get(status,status)

def plain_position(text):
    return {"FLAT":"No position","LONG SPREAD":"Bought cheaper side / sold expensive side","SHORT SPREAD":"Bought cheaper side / sold expensive side"}.get(text,text.replace("LONG ","Holding ").replace("SHORT ","Holding "))

def plain_signal(text):
    mapping={
        "WAIT":"Wait","FLAT / EXIT ZONE":"No trade / close if open","HOLD":"Keep current simulated trade",
        "EXIT":"Close simulated trade","SELL / EXIT":"Sell and close simulated trade",
        "ENTER LONG SPREAD":"Start simulated two-fund trade","ENTER SHORT SPREAD":"Start simulated two-fund trade",
        "LONG SPREAD":"Would start simulated two-fund trade","SHORT SPREAD":"Would start simulated two-fund trade"
    }
    if text.startswith("BUY "): return "Simulated buy " + fund_name(text[4:])
    return mapping.get(text,text)

st.set_page_config(page_title="Market Lab V6", page_icon="🧪", layout="wide")
st.title("Market Lab V6")
st.caption("Researching share-market strategies, simulated trading on new data, and market reactions to public events")

CACHE_SCHEMA = "v6.4"

@st.cache_data(ttl=3600, show_spinner=False)
def research(schema_version):
    prices = load_prices()
    return prices, strategy_leaderboard(prices)

with st.spinner("Trying to break the strategies... this version does substantially more work."):
    prices, results = research(CACHE_SCHEMA)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Share-market funds loaded", len(prices.columns))
c2.metric("Two-fund strategies tested", len(results))
c3.metric("Ready for final hidden test", sum(r["status"] == "HOLDOUT READY" for r in results))
c4.metric("History start", str(prices.index.min().date()))

st.subheader("Historical testing results")
rows = []
for r in results:
    rows.append({
        "Two funds": plain_pair(r["pair"]),
        "Return during repeated tests": f'{r.get("dev_return", r.get("wf_return", 0.0)):.2%}',
        "Completed simulated trades": r["trades"],
        "Profitable test periods": f'{r["consistency"]:.0%}',
        "Relationship stayed stable": f'{r["stationary_rate"]:.0%}',
        "Return compared with movement": f'{r["sharpe"]:.2f}',
        "Worst fall from previous high": f'{r["max_dd"]:.2%}',
        "Small rule-change pass rate": f'{r.get("parameter_pass", 0.0):.0%}',
        "Return with 0.08% trading cost": f'{r.get("cost8", 0.0):.2%}',
        "Return with 0.15% trading cost": f'{r.get("cost15", 0.0):.2%}',
        "Return with 0.25% trading cost": f'{r.get("cost25", 0.0):.2%}',
        "Status": plain_status(r["status"]),
    })

st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
st.caption("The final 15% of the historical data is kept hidden while strategies are selected. A strategy is shown as ready only if it stays reasonably consistent across different periods, survives small rule changes and still works after higher assumed trading costs.")

ready = [r for r in results if r["status"] == "HOLDOUT READY"]
st.subheader("Final hidden historical test")
if not ready:
    st.info("No strategy passed the earlier checks strongly enough to reach the final hidden historical test. That is still a useful result.")
else:
    st.warning("These results come from the final part of the historical data that was kept aside. The rules should not now be changed just to improve these numbers.")
    hrows = []
    for r in ready:
        h = r["holdout"]
        pf = h["profit_factor"]
        pf_text = "∞" if pf == float("inf") else f"{pf:.2f}"
        hrows.append({
            "Two funds": plain_pair(r["pair"]),
            "Return in final hidden test": f'{h["return"]:.2%}',
            "Completed simulated trades": h["trades"],
            "Winning trades": f'{h["win_rate"]:.0%}',
            "Return compared with movement": f'{h["sharpe"]:.2f}',
            "Worst fall from previous high": f'{h["max_dd"]:.2%}',
            "Profit compared with losses": pf_text,
        })
    st.dataframe(pd.DataFrame(hrows), use_container_width=True, hide_index=True)

if results:
    pick = st.selectbox("Choose a two-fund strategy to inspect", [r["pair"] for r in results], format_func=plain_pair)
    r = next(x for x in results if x["pair"] == pick)
    w = r["windows"].copy()
    w["return_pct"] = w["return"] * 100
    st.plotly_chart(
        px.bar(w, x="window", y="return_pct",
               labels={"window": "Historical test period", "return_pct": "Return (%)"}),
        use_container_width=True,
    )

with st.expander("How the historical testing works"):
    st.markdown("""
**Longer history:** up to ten years of share-market price history where available.

**Higher trading-cost checks:** every strategy is retested using total buying-and-selling costs of 0.08%, 0.15% and 0.25%.

**Small rule changes:** the entry and exit points are changed slightly to check that the result does not depend on one very precise setting.

**Final hidden historical test:** the last 15% of the old market data is kept aside while the rules are chosen. Only strategies that pass the earlier checks are shown against it.

The next step for a strategy that survives is simulated trading on genuinely new market data. The rules stay fixed rather than being changed to fit the new results.
""")

st.info("Research software only. No brokerage connection or live orders. Historical performance does not establish future profitability.")


st.divider()
st.subheader("Simulated trading on new market data")
st.caption("Rules frozen on 29 Sep 2026. This section only counts market data from that date onward.")

forward = forward_dashboard(prices)
frows=[]
for x in forward:
    frows.append({
        "Two funds":plain_pair(x["pair"]),
        "Latest date":str(pd.Timestamp(x["latest_date"]).date()),
        "Current distance from normal":f'{x["latest_z"]:.2f}',
        "Current position":plain_position(x["position"]),
        "Current instruction":plain_signal(x["signal"]),
        "Return since new-data test began":f'{x["return"]:.2%}',
        "Completed trades":x["trades"],
        "Winning trades":f'{x["win_rate"]:.0%}' if x["trades"] else "—",
        "Worst fall from previous high":f'{x["max_dd"]:.2%}',
    })
st.dataframe(pd.DataFrame(frows),use_container_width=True,hide_index=True)

st.caption("This section uses only market data from 29 September 2026 onward. When no entry rule is met, the instruction will simply say to wait.")

fpick=st.selectbox("Choose a new-data strategy to inspect",[x["pair"] for x in forward],key="forward_pair",format_func=plain_pair)
fx=next(x for x in forward if x["pair"]==fpick)

fc1,fc2,fc3,fc4=st.columns(4)
fc1.metric("Current distance from normal",f'{fx["latest_z"]:.2f}')
fc2.metric("Current position",plain_position(fx["position"]))
fc3.metric("Return since test began",f'{fx["return"]:.2%}')
fc4.metric("Completed trades",fx["trades"])

if len(fx["equity_curve"]):
    e=fx["equity_curve"].reset_index()
    st.plotly_chart(px.line(e,x="date",y="equity",title="Simulated account value since the new-data test began"),use_container_width=True)
else:
    st.info("No forward market days have been recorded yet.")

if len(fx["trade_log"]):
    st.subheader("Simulated trade history")
    st.dataframe(fx["trade_log"],use_container_width=True,hide_index=True)

with st.expander("What happens from here"):
    st.markdown("""
The three strategies use fixed rules. A simulated trade starts when the two funds move unusually far apart, closes when they move back near their normal relationship, assumes total trading costs of 0.08%, and uses the same trade size throughout the test.

Each time new daily market prices become available, this section records what the strategy *would* have done. The rules are not changed in response to the results.
""")


st.divider()
st.subheader("Two-fund strategy compared with buy-only strategy")
st.caption("Both versions use the same funds, the same historical periods and the same entry signals. One buys the cheaper fund and sells the more expensive one short; the simpler version buys only the cheaper fund.")

comparisons=model_comparison_dashboard(prices)
comparison_rows=[]
for c in comparisons:
    comparison_rows.extend([
        {"Two funds":plain_pair(c["pair"]),"Model":"Two-fund strategy","Development return":f'{c["pairs_dev"]["return"]:.2%}',
         "Development simulated trades":c["pairs_dev"]["trades"],"Return in final hidden test":f'{c["pairs_hold"]["return"]:.2%}',
         "Final hidden test trades":c["pairs_hold"]["trades"],"Return compared with movement":f'{c["pairs_hold"]["sharpe"]:.2f}',
         "Worst fall from previous high":f'{c["pairs_hold"]["max_dd"]:.2%}'},
        {"Two funds":plain_pair(c["pair"]),"Model":"Buy-only strategy","Development return":f'{c["long_dev"]["return"]:.2%}',
         "Development simulated trades":c["long_dev"]["trades"],"Return in final hidden test":f'{c["long_hold"]["return"]:.2%}',
         "Final hidden test trades":c["long_hold"]["trades"],"Return compared with movement":f'{c["long_hold"]["sharpe"]:.2f}',
         "Worst fall from previous high":f'{c["long_hold"]["max_dd"]:.2%}'},
    ])
st.dataframe(pd.DataFrame(comparison_rows),use_container_width=True,hide_index=True)
st.caption("The buy-only version was added after the original two-fund historical results had already been viewed, so its old-data comparison is only exploratory. The cleaner comparison is the simulated trading on new data from 29 September 2026 onward.")

st.subheader("Buy-only simulated trading on new market data")
st.caption("When one fund becomes unusually cheap compared with the other, the model simulates buying only the cheaper fund. It sells when the relationship moves back close to normal.")

long_forward=forward_long_only_dashboard(prices)
lfrows=[]
for x in long_forward:
    lfrows.append({
        "Two funds":plain_pair(x["pair"]),
        "Latest date":str(pd.Timestamp(x["latest_date"]).date()),
        "Current distance from normal":f'{x["latest_z"]:.2f}',
        "Current position":plain_position(x["position"]),
        "Current instruction":plain_signal(x["signal"]),
        "Return since new-data test began":f'{x["return"]:.2%}',
        "Completed trades":x["trades"],
        "Winning trades":f'{x["win_rate"]:.0%}' if x["trades"] else "—",
        "Worst fall from previous high":f'{x["max_dd"]:.2%}',
    })
st.dataframe(pd.DataFrame(lfrows),use_container_width=True,hide_index=True)

lpick=st.selectbox("Choose a buy-only strategy to inspect",[x["pair"] for x in long_forward],key="long_forward_pair",format_func=plain_pair)
lx=next(x for x in long_forward if x["pair"]==lpick)
lc1,lc2,lc3,lc4=st.columns(4)
lc1.metric("Current distance from normal",f'{lx["latest_z"]:.2f}')
lc2.metric("Current position",plain_position(lx["position"]))
lc3.metric("Return since test began",f'{lx["return"]:.2%}')
lc4.metric("Completed trades",lx["trades"])

if len(lx["equity_curve"]):
    le=lx["equity_curve"].reset_index()
    st.plotly_chart(px.line(le,x="date",y="equity",title="Buy-only simulated account value"),use_container_width=True)

if len(lx["trade_log"]):
    st.subheader("Buy-only simulated trade history")
    st.dataframe(lx["trade_log"],use_container_width=True,hide_index=True)

with st.expander("How the buy-only strategy works"):
    st.markdown("""
If one share-market fund becomes unusually cheap compared with the other, Market Lab simulates buying only that cheaper fund. It does **not** borrow and sell the more expensive fund.

Example: if US Growth Shares (IWF) look unusually cheap compared with the Broad US Market (SPY), the model records a simulated purchase of IWF. When the relationship moves back near normal, it records a simulated sale.

This is simpler to understand and execute, but it is more affected by whether the overall share market rises or falls.
""")


st.divider()
st.subheader("Trump public-event study")
st.caption("Researching whether different kinds of public events are followed by unusual market moves, while checking what happened before the event as well.")

study=trump_event_study(prices)
if not study.empty:
    ec1,ec2,ec3,ec4=st.columns(4)
    ec1.metric("Events in the collection",study["date"].nunique())
    ec2.metric("Subject areas",study["theme"].nunique())
    ec3.metric("Public comments/interviews",study.loc[study["source_type"]!="formal_action","date"].nunique())
    ec4.metric("Fund-event observations",len(study))

if study.empty:
    st.info("No event-study results are available yet.")
else:
    h=st.selectbox("How many trading days after the event?",[1,3,5],index=0,format_func=lambda x:f"{x} trading day{'s' if x>1 else ''}",key="trump_horizon")

    f1,f2,f3,f4=st.columns(4)
    source_filter=f1.multiselect("Type of event",sorted(study["source_type"].unique()),default=sorted(study["source_type"].unique()))
    direction_filter=f2.multiselect("Policy direction",sorted(study["direction"].unique()),default=sorted(study["direction"].unique()))
    surprise_filter=f3.multiselect("How new was the event?",sorted(study["surprise_proxy"].unique()),default=sorted(study["surprise_proxy"].unique()))
    timing_filter=f4.multiselect("When did it happen?",sorted(study["market_session"].unique()),default=sorted(study["market_session"].unique()))

    filtered=study[
        study["source_type"].isin(source_filter) &
        study["direction"].isin(direction_filter) &
        study["surprise_proxy"].isin(surprise_filter) &
        study["market_session"].isin(timing_filter)
    ].copy()

    st.subheader("Market reaction by subject and share-market fund")
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
        show["ticker"]=show["ticker"].map(fund_name)
        show=show[["theme","ticker","events","observations","Avg abnormal return","Median abnormal return","Positive rate","Avg pre-event 1d","Avg pre-event 3d"]]
        show.columns=["Subject","Share-market fund","Events","Observations","Average result vs broad market","Middle result vs broad market","Percentage positive","1 day before event","3 days before event"]
        st.dataframe(show,use_container_width=True,hide_index=True)

    st.caption("Results show how much better or worse each share-market fund performed than the broad US market over the same period. The before-event columns show whether the move had already started.")

    st.subheader("Does the type of event, its direction, or how new it was matter?")
    tab1,tab2,tab3=st.tabs(["Type of event + direction","How new was it?","When did it happen?"])
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
        st.caption("How new was it? High = a major new action; medium = a change, extension or industry-support action; low = mainly remarks or repetition without a separately verified new action.")
    with tab3:
        s=timing_summary(filtered,h)
        if len(s):
            sv=s.copy()
            sv["Avg abnormal return"]=sv["avg_abnormal"].map(lambda x:f"{x:.2%}")
            sv["Positive rate"]=sv["positive_rate"].map(lambda x:f"{x:.0%}")
            st.dataframe(sv[["market_session","events","observations","Avg abnormal return","Positive rate"]],use_container_width=True,hide_index=True)
        st.caption("Many older sources give a date but not a reliable time. Those events stay marked as unknown rather than being guessed.")

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
        d["fund_display"]=d["ticker"].map(fund_name)
        d[f"abn_{h}d_pct"]=d[f"abn_{h}d"]*100
        st.plotly_chart(
            px.bar(d.sort_values(f"abn_{h}d"),x="fund_display",y=f"abn_{h}d_pct",
                   labels={"fund_display":"Share-market fund",f"abn_{h}d_pct":"Better or worse than the broad market (%)"},
                   title=f"How the selected share-market funds performed compared with the broad US market after {h} trading day{'s' if h>1 else ''}"),
            use_container_width=True
        )

    with st.expander("How to read these results"):
        st.markdown("""
**Policy direction** describes whether the event made policy tougher, made it softer, supported an industry, or had mixed effects.

**How new was it?** is a simple rule-based label. A major new action is marked high; a change, extension or industry-support action is medium; remarks without a separately verified new action are low.

**When did it happen?** is only recorded when the source gives enough information. Unknown events stay unknown. Because the app currently uses daily closing prices, a comment made during the trading day cannot be separated precisely from everything else that happened that day.

**Movement before the event** compares the selected share-market fund with the broad US market before the event. If it was already moving strongly beforehand, we should be more cautious about linking the later move to the event itself.

This remains descriptive research. It does not establish causation or a reliable trading rule.
""")

