"""
Scanner page.

Build shortlisting rules that can mix timeframes (e.g. Monthly RSI above 60
AND Weekly RSI crossed above 60), scan the NIFTY 500 (or a smaller test
batch), review the shortlist, and save it as a named watchlist. Saved
watchlists show up automatically on the Chart page's watchlist dropdown.

Indicator periods (SMA/EMA/RSI lengths, MACD/Bollinger/Stochastic/ADX
parameters) are configurable in the sidebar and saved to
`indicator_settings.json`, shared with the Chart page.
"""

import time

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from common import (
    load_nifty500_list, fetch_daily_data, resample_ohlc, save_watchlist,
    compute_indicators, load_indicator_settings, save_indicator_settings,
    parse_periods, build_rule_options, passes_rules, apply_theme,
)

st.set_page_config(page_title="Scanner — NIFTY 500", layout="wide", page_icon="🔍")
apply_theme("Scanner")
st.title("🔍 NIFTY 500 Scanner")
st.caption(
    "Build rules that can mix Daily, Weekly, and Monthly indicators, scan "
    "all 500 stocks, then save the shortlist as a watchlist."
)

TIMEFRAMES = ["Daily", "Weekly", "Monthly"]

if "indicator_settings" not in st.session_state:
    st.session_state.indicator_settings = load_indicator_settings()
settings = st.session_state.indicator_settings

# ----------------------------------------------------------------------
# SIDEBAR: INDICATOR PARAMETERS (shared with the Chart page)
# ----------------------------------------------------------------------
st.sidebar.header("1. Indicator Parameters")
with st.sidebar.expander("⚙️ Customise periods / parameters", expanded=False):
    source_options = {"yahoo": "Yahoo Finance (fast, default)", "nse": "NSE Direct (official, slower)", "nse_then_yahoo": "NSE Direct, fall back to Yahoo"}
    data_source_label = st.selectbox(
        "Price data source", list(source_options.values()),
        index=list(source_options.keys()).index(settings.get("data_source", "yahoo")),
        help="NSE Direct is much slower per stock (multiple requests per stock) and often blocked from cloud hosting — Yahoo is strongly recommended for scanning all 500 stocks.",
    )
    data_source = [k for k, v in source_options.items() if v == data_source_label][0]

    sma_text = st.text_input("SMA periods (comma-separated)", value=",".join(str(p) for p in settings["sma_periods"]))
    ema_text = st.text_input("EMA periods (comma-separated)", value=",".join(str(p) for p in settings["ema_periods"]))
    rsi_text = st.text_input("RSI periods (comma-separated)", value=",".join(str(p) for p in settings["rsi_periods"]))
    c1, c2, c3 = st.columns(3)
    macd_fast = c1.number_input("MACD fast", value=settings["macd"]["fast"], min_value=1)
    macd_slow = c2.number_input("MACD slow", value=settings["macd"]["slow"], min_value=1)
    macd_signal = c3.number_input("MACD signal", value=settings["macd"]["signal"], min_value=1)
    c4, c5 = st.columns(2)
    bb_window = c4.number_input("Bollinger window", value=settings["bollinger"]["window"], min_value=1)
    bb_dev = c5.number_input("Bollinger std-dev", value=float(settings["bollinger"]["dev"]), min_value=0.1, step=0.1)
    c6, c7 = st.columns(2)
    stoch_k = c6.number_input("Stochastic %K", value=settings["stochastic"]["k"], min_value=1)
    stoch_d = c7.number_input("Stochastic %D smoothing", value=settings["stochastic"]["d"], min_value=1)
    adx_period = st.number_input("ADX period", value=settings["adx_period"], min_value=1)

    if st.button("💾 Save indicator parameters"):
        settings["data_source"] = data_source
        settings["sma_periods"] = parse_periods(sma_text, settings["sma_periods"])
        settings["ema_periods"] = parse_periods(ema_text, settings["ema_periods"])
        settings["rsi_periods"] = parse_periods(rsi_text, settings["rsi_periods"])
        settings["macd"] = {"fast": int(macd_fast), "slow": int(macd_slow), "signal": int(macd_signal)}
        settings["bollinger"] = {"window": int(bb_window), "dev": float(bb_dev)}
        settings["stochastic"] = {"k": int(stoch_k), "d": int(stoch_d)}
        settings["adx_period"] = int(adx_period)
        save_indicator_settings(settings)
        st.session_state.indicator_settings = settings
        st.success("Saved. Periods now apply everywhere (this page and the Chart page).")
        st.rerun()

RULE_OPTIONS, NEEDS_VALUE = build_rule_options(settings)

# ----------------------------------------------------------------------
# SIDEBAR: STOCK UNIVERSE + RULES
# ----------------------------------------------------------------------
st.sidebar.header("2. Stock Universe")
nifty_list = load_nifty500_list(sidebar=True)
if nifty_list is not None:
    st.sidebar.success(f"{len(nifty_list)} NIFTY 500 stocks loaded.")

st.sidebar.header("3. History Depth")
years_history = st.sidebar.slider("Years of price history to fetch", 2, 10, 5)

st.sidebar.header("4. Build Your Shortlist Rules")
st.sidebar.caption(
    "Each rule picks its own timeframe. Example: Rule 1 = Monthly RSI(14) "
    "above 60, Rule 2 = Weekly RSI(14) crossed above 60. A stock must pass ALL rules."
)

if "rule_rows" not in st.session_state:
    st.session_state.rule_rows = [0]


def add_rule_row():
    st.session_state.rule_rows.append(max(st.session_state.rule_rows, default=-1) + 1)


def remove_rule_row(i):
    if i in st.session_state.rule_rows:
        st.session_state.rule_rows.remove(i)


st.sidebar.button("➕ Add another rule", on_click=add_rule_row)

active_rules = []
for i in list(st.session_state.rule_rows):
    with st.sidebar.container():
        cols = st.columns([1, 2])
        tf = cols[0].selectbox("Timeframe", TIMEFRAMES, index=1, key=f"rule_tf_{i}")
        rule_name = cols[1].selectbox(f"Rule {i+1}", list(RULE_OPTIONS.keys()), key=f"rule_name_{i}")
        val = None
        if rule_name in NEEDS_VALUE:
            if "RSI" in rule_name or "Stoch" in rule_name:
                default_val = 60.0
            elif "rising" in rule_name or "falling" in rule_name:
                default_val = 5.0
            else:
                default_val = 3.0
            val = st.sidebar.number_input(f"Value for Rule {i+1}", value=default_val, key=f"rule_val_{i}")
        if len(st.session_state.rule_rows) > 1:
            st.sidebar.button("Remove this rule", key=f"remove_{i}", on_click=remove_rule_row, args=(i,))
        st.sidebar.markdown("---")
        active_rules.append((tf, rule_name, val))

st.sidebar.header("5. Run")
if settings.get("data_source", "yahoo") != "yahoo":
    st.sidebar.warning(
        "Data source is set to NSE Direct — scanning many stocks will be "
        "considerably slower (and may fail on cloud hosting) than Yahoo Finance."
    )
max_stocks = st.sidebar.slider("Limit scan to first N stocks (lower = faster test run)", 10, 500, 500)
run_scan = st.sidebar.button("🔍 Scan NIFTY 500", type="primary")


# ----------------------------------------------------------------------
# RUN SCAN
# ----------------------------------------------------------------------
if "scan_results" not in st.session_state:
    st.session_state.scan_results = None
if "scan_cache" not in st.session_state:
    st.session_state.scan_cache = {}

if run_scan:
    if nifty_list is None:
        st.error("No stock list loaded yet. See sidebar to upload NIFTY 500 CSV.")
    elif not active_rules:
        st.error("Add at least one rule before scanning.")
    else:
        needed_timeframes = sorted(set(tf for tf, _, _ in active_rules), key=TIMEFRAMES.index)
        tickers = nifty_list.head(max_stocks)
        progress = st.progress(0, text="Starting scan...")
        results = []
        cache = {}
        failed = []
        total = len(tickers)
        primary_rsi_col = f"RSI{settings['rsi_periods'][0]}"

        for idx, row in enumerate(tickers.itertuples()):
            progress.progress((idx + 1) / total, text=f"Scanning {row.Symbol} ({idx+1}/{total})")
            try:
                daily = fetch_daily_data(row.YF_Ticker, years=years_history, data_source=settings.get("data_source", "yahoo"))
                if daily is None or daily.empty:
                    failed.append(row.Symbol)
                    continue

                tf_dfs = {}
                for tf in needed_timeframes:
                    tf_df = resample_ohlc(daily, tf)
                    tf_dfs[tf] = compute_indicators(tf_df, settings)
                cache[row.Symbol] = tf_dfs

                if passes_rules(tf_dfs, active_rules, RULE_OPTIONS):
                    primary_tf = needed_timeframes[-1]
                    last = tf_dfs[primary_tf].iloc[-1]
                    row_result = {
                        "Symbol": row.Symbol,
                        "Company": row.Company,
                        "Close": round(last["Close"], 2),
                    }
                    for tf in needed_timeframes:
                        l = tf_dfs[tf].iloc[-1]
                        if primary_rsi_col in l:
                            row_result[f"{tf} {primary_rsi_col}"] = round(l[primary_rsi_col], 1) if pd.notna(l[primary_rsi_col]) else None
                    results.append(row_result)
            except Exception:
                failed.append(row.Symbol)
                continue
            time.sleep(0.15)  # small pause between requests — reduces Yahoo Finance rate-limiting

        progress.empty()
        st.session_state.scan_results = pd.DataFrame(results)
        st.session_state.scan_cache = cache
        st.session_state.scan_timeframes = needed_timeframes
        st.success(f"Scan complete. {len(results)} of {total} stocks matched your rules.")
        if failed:
            with st.expander(f"⚠️ {len(failed)} stock(s) had no price data available (click to see which)"):
                st.write(", ".join(failed))
                st.caption(
                    "Usually a temporary Yahoo Finance rate-limit, not a permanent problem — "
                    "try scanning again in a minute or two."
                )


# ----------------------------------------------------------------------
# SHOW RESULTS + SAVE TO WATCHLIST
# ----------------------------------------------------------------------
if st.session_state.scan_results is not None:
    st.subheader("Shortlisted Stocks")
    results_df = st.session_state.scan_results
    if results_df.empty:
        st.info("No stocks matched your rules. Try loosening the conditions.")
    else:
        st.dataframe(results_df, use_container_width=True, hide_index=True)

        col1, col2 = st.columns([2, 1])
        with col1:
            watchlist_name = st.text_input("Save this shortlist as a watchlist named:", value="My Watchlist")
        with col2:
            st.write("")
            st.write("")
            if st.button("💾 Save to watchlist"):
                path = save_watchlist(watchlist_name, results_df)
                if path:
                    st.success(f"Saved {len(results_df)} stocks to '{watchlist_name}'. It now appears on the Chart page too.")
                else:
                    st.error("Enter a valid watchlist name.")

        st.subheader("Inspect a Stock Chart")
        chosen = st.selectbox("Choose a shortlisted stock", results_df["Symbol"].tolist())
        available_tfs = st.session_state.get("scan_timeframes", ["Weekly"])
        chart_tf = st.radio("Chart timeframe", available_tfs, horizontal=True)

        # ---- Indicator picker for this chart (persisted) ----
        overlay_choices = (
            [f"SMA {p}" for p in settings["sma_periods"]]
            + [f"EMA {p}" for p in settings["ema_periods"]]
            + ["Bollinger Bands"]
        )
        oscillator_choices = [f"RSI {p}" for p in settings["rsi_periods"]] + ["MACD", "Stochastic", "ADX"]

        pick_col1, pick_col2, pick_col3 = st.columns([2, 2, 1])
        with pick_col1:
            chosen_overlays = st.multiselect(
                "Overlays", overlay_choices,
                default=[o for o in settings.get("scanner_overlays", []) if o in overlay_choices],
            )
        with pick_col2:
            chosen_oscillators = st.multiselect(
                "Oscillator panes", oscillator_choices,
                default=[o for o in settings.get("scanner_oscillators", []) if o in oscillator_choices],
            )
        with pick_col3:
            st.write("")
            st.write("")
            if st.button("💾 Save as default"):
                settings["scanner_overlays"] = chosen_overlays
                settings["scanner_oscillators"] = chosen_oscillators
                save_indicator_settings(settings)
                st.session_state.indicator_settings = settings
                st.success("Saved.")

        if chosen and chosen in st.session_state.scan_cache:
            df = st.session_state.scan_cache[chosen].get(chart_tf)
            if df is not None:
                df = df.tail(150)

                n_osc_rows = len(chosen_oscillators)
                row_heights = [0.55] + [0.45 / max(n_osc_rows, 1)] * n_osc_rows if n_osc_rows else [1.0]
                titles = [f"{chosen} — {chart_tf} Price"] + chosen_oscillators
                fig = make_subplots(
                    rows=1 + n_osc_rows, cols=1, shared_xaxes=True,
                    row_heights=row_heights, vertical_spacing=0.03,
                    subplot_titles=titles,
                )
                fig.add_trace(go.Candlestick(
                    x=df.index, open=df["Open"], high=df["High"],
                    low=df["Low"], close=df["Close"], name="Price"
                ), row=1, col=1)

                for name in chosen_overlays:
                    if name == "Bollinger Bands":
                        fig.add_trace(go.Scatter(x=df.index, y=df["BB_High"], name="BB High", line=dict(width=1, dash="dot")), row=1, col=1)
                        fig.add_trace(go.Scatter(x=df.index, y=df["BB_Low"], name="BB Low", line=dict(width=1, dash="dot")), row=1, col=1)
                    else:
                        col = name.replace(" ", "")
                        if col in df.columns:
                            fig.add_trace(go.Scatter(x=df.index, y=df[col], name=name, line=dict(width=1)), row=1, col=1)

                for r_idx, osc in enumerate(chosen_oscillators, start=2):
                    if osc.startswith("RSI"):
                        col = osc.replace(" ", "")
                        fig.add_trace(go.Scatter(x=df.index, y=df[col], name=osc), row=r_idx, col=1)
                        fig.add_hline(y=70, line_dash="dash", line_color="red", row=r_idx, col=1)
                        fig.add_hline(y=30, line_dash="dash", line_color="green", row=r_idx, col=1)
                    elif osc == "MACD":
                        fig.add_trace(go.Bar(x=df.index, y=df["MACD_Hist"], name="MACD Hist"), row=r_idx, col=1)
                        fig.add_trace(go.Scatter(x=df.index, y=df["MACD"], name="MACD"), row=r_idx, col=1)
                        fig.add_trace(go.Scatter(x=df.index, y=df["MACD_Signal"], name="Signal"), row=r_idx, col=1)
                    elif osc == "Stochastic":
                        fig.add_trace(go.Scatter(x=df.index, y=df["Stoch_%K"], name="%K"), row=r_idx, col=1)
                        fig.add_trace(go.Scatter(x=df.index, y=df["Stoch_%D"], name="%D"), row=r_idx, col=1)
                        fig.add_hline(y=80, line_dash="dash", line_color="red", row=r_idx, col=1)
                        fig.add_hline(y=20, line_dash="dash", line_color="green", row=r_idx, col=1)
                    elif osc == "ADX":
                        fig.add_trace(go.Scatter(x=df.index, y=df["ADX"], name="ADX"), row=r_idx, col=1)
                        fig.add_hline(y=25, line_dash="dash", line_color="gray", row=r_idx, col=1)

                fig.update_layout(height=550 + n_osc_rows * 200, xaxis_rangeslider_visible=False, showlegend=True)
                st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Set your rules in the sidebar and click **Scan NIFTY 500** to begin.")
