"""
Chart page — a TradingView-style workspace.

Left: a watchlist panel (defaults to all NIFTY 500 stocks, or any saved
      watchlist from the Scanner page). Click a symbol to load its chart.
Right: a candlestick chart (TradingView's own "lightweight-charts" library)
       with an indicator picker — toggle moving averages / Bollinger Bands
       as overlays on the price chart, and RSI / MACD / Stochastic / ADX as
       separate synced panes underneath. Indicator periods (SMA/EMA/RSI
       lengths, MACD/Bollinger/Stochastic/ADX parameters) are fully
       customisable in the sidebar, and both your parameters and your
       on/off selections are saved to disk so they're remembered next
       time you open the app.
"""

import json

import streamlit as st
import streamlit.components.v1 as components

from common import (
    load_nifty500_list, fetch_daily_data, resample_ohlc, compute_indicators,
    list_saved_watchlists, load_watchlist, delete_watchlist, load_indicator_settings,
    save_indicator_settings, parse_periods, apply_theme,
    fetch_fundamentals, format_market_cap, format_number, format_percent,
)

st.set_page_config(page_title="Chart — NIFTY 500", layout="wide", page_icon="📈")
apply_theme("Chart")

if "active_symbol" not in st.session_state:
    st.session_state.active_symbol = None
if "active_ticker" not in st.session_state:
    st.session_state.active_ticker = None
if "indicator_settings" not in st.session_state:
    st.session_state.indicator_settings = load_indicator_settings()
settings = st.session_state.indicator_settings

# ----------------------------------------------------------------------
# SIDEBAR: INDICATOR PARAMETERS (shared with the Scanner page)
# ----------------------------------------------------------------------
st.sidebar.header("Indicator Parameters")
with st.sidebar.expander("⚙️ Customise periods / parameters", expanded=False):
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
        settings["sma_periods"] = parse_periods(sma_text, settings["sma_periods"])
        settings["ema_periods"] = parse_periods(ema_text, settings["ema_periods"])
        settings["rsi_periods"] = parse_periods(rsi_text, settings["rsi_periods"])
        settings["macd"] = {"fast": int(macd_fast), "slow": int(macd_slow), "signal": int(macd_signal)}
        settings["bollinger"] = {"window": int(bb_window), "dev": float(bb_dev)}
        settings["stochastic"] = {"k": int(stoch_k), "d": int(stoch_d)}
        settings["adx_period"] = int(adx_period)
        save_indicator_settings(settings)
        st.session_state.indicator_settings = settings
        st.success("Saved. Periods now apply everywhere (this page and the Scanner).")
        st.rerun()

# ----------------------------------------------------------------------
# TOP BAR: watchlist source, timeframe, search
# ----------------------------------------------------------------------
top_col1, top_col2, top_col3, top_col4, top_col5 = st.columns([1.8, 1.8, 2.2, 1.2, 1])

with top_col1:
    saved = list_saved_watchlists()
    source = st.selectbox("Watchlist", ["NIFTY 500 (all)"] + saved)

with top_col2:
    timeframe = st.radio("Timeframe", ["Daily", "Weekly", "Monthly"], horizontal=True, index=1)

with top_col3:
    search = st.text_input("Search symbol or company", placeholder="e.g. RELIANCE or Reliance")

with top_col4:
    years_history = st.number_input("Years of history", min_value=1, max_value=25, value=5, step=1)

with top_col5:
    st.write("")
    if source != "NIFTY 500 (all)":
        if st.session_state.get("confirm_delete") == source:
            if st.button(f"⚠️ Confirm delete '{source}'", type="primary"):
                delete_watchlist(source)
                st.session_state.confirm_delete = None
                st.session_state.active_symbol = None
                st.success(f"Deleted '{source}'.")
                st.rerun()
        else:
            if st.button("🗑️ Delete watchlist"):
                st.session_state.confirm_delete = source
                st.rerun()

# ----------------------------------------------------------------------
# INDICATOR PICKER (choices built from your configured periods above)
# ----------------------------------------------------------------------
overlay_choices = (
    [f"SMA {p}" for p in settings["sma_periods"]]
    + [f"EMA {p}" for p in settings["ema_periods"]]
    + ["Bollinger Bands"]
)
oscillator_choices = [f"RSI {p}" for p in settings["rsi_periods"]] + ["MACD", "Stochastic", "ADX"]

ind_col1, ind_col2, ind_col3, ind_col4 = st.columns([2.2, 2.2, 1, 1])

with ind_col1:
    overlays = st.multiselect(
        "Overlays (on the price chart)", overlay_choices,
        default=[o for o in settings.get("chart_overlays", []) if o in overlay_choices],
    )
with ind_col2:
    oscillators = st.multiselect(
        "Oscillator panes (below)", oscillator_choices,
        default=[o for o in settings.get("chart_oscillators", []) if o in oscillator_choices],
    )
with ind_col3:
    show_volume = st.checkbox("Show volume", value=settings.get("chart_show_volume", True))
with ind_col4:
    st.write("")
    if st.button("💾 Save as default"):
        settings["chart_overlays"] = overlays
        settings["chart_oscillators"] = oscillators
        settings["chart_show_volume"] = show_volume
        save_indicator_settings(settings)
        st.session_state.indicator_settings = settings
        st.success("Saved.")

OVERLAY_COLORS_PALETTE = ["#378ADD", "#7F77DD", "#D4A24C", "#1BAF7A", "#D85A30", "#534AB7"]

# ----------------------------------------------------------------------
# BUILD THE WATCHLIST TABLE FOR THE LEFT PANEL
# ----------------------------------------------------------------------
if source == "NIFTY 500 (all)":
    universe = load_nifty500_list(sidebar=False)
else:
    wl = load_watchlist(source)
    if wl is not None and "Symbol" in wl.columns:
        universe = wl[["Symbol"]].drop_duplicates().copy()
        universe["Company"] = universe["Symbol"]
        universe["YF_Ticker"] = universe["Symbol"] + ".NS"
    else:
        universe = None

if universe is None:
    st.warning("Couldn't load a stock list yet. See the file uploader above.")
    st.stop()

if search:
    mask = (
        universe["Symbol"].str.contains(search, case=False, na=False)
        | universe["Company"].str.contains(search, case=False, na=False)
    )
    display_list = universe[mask]
    caption = f"{len(display_list)} match(es) for '{search}'"
else:
    display_list = universe.head(60)
    caption = f"Showing first 60 of {len(universe)} — use search to jump to others."

if st.session_state.active_symbol is None and len(universe) > 0:
    st.session_state.active_symbol = universe.iloc[0]["Symbol"]
    st.session_state.active_ticker = universe.iloc[0]["YF_Ticker"]

# ----------------------------------------------------------------------
# LAYOUT: watchlist panel (left) + chart (right)
# ----------------------------------------------------------------------
left, right = st.columns([1, 3.2])

with left:
    st.caption(caption)
    with st.container(height=620):
        for _, row in display_list.iterrows():
            is_active = row["Symbol"] == st.session_state.active_symbol
            label = f"{'▶ ' if is_active else ''}{row['Symbol']}"
            if st.button(label, key=f"watch_{row['Symbol']}", use_container_width=True):
                st.session_state.active_symbol = row["Symbol"]
                st.session_state.active_ticker = row["YF_Ticker"]
                st.rerun()

with right:
    symbol = st.session_state.active_symbol
    ticker = st.session_state.active_ticker
    st.subheader(symbol if symbol else "No symbol selected")

    if symbol:
        with st.spinner(f"Loading {symbol}..."):
            daily = fetch_daily_data(ticker, years=years_history)

        if daily is None or daily.empty:
            st.error(f"No price data found for {ticker}.")
        else:
            df = resample_ohlc(daily, timeframe)
            df = compute_indicators(df, settings)
            dates = [idx.strftime("%Y-%m-%d") for idx in df.index]

            candles = [
                {
                    "time": idx.strftime("%Y-%m-%d"),
                    "open": round(float(r["Open"]), 2),
                    "high": round(float(r["High"]), 2),
                    "low": round(float(r["Low"]), 2),
                    "close": round(float(r["Close"]), 2),
                }
                for idx, r in df.iterrows()
            ]
            volumes = [
                {
                    "time": idx.strftime("%Y-%m-%d"),
                    "value": float(r["Volume"]),
                    "color": "rgba(29,158,117,0.35)" if r["Close"] >= r["Open"] else "rgba(216,90,48,0.35)",
                }
                for idx, r in df.iterrows()
            ]
            # Invisible full-range anchor — added to every oscillator pane so its
            # time axis lines up bar-for-bar with the main chart (needed so the
            # panes pan/zoom together correctly).
            anchor = [{"time": d, "value": 0} for d in dates]

            def series_data(col):
                sub = df[col].dropna()
                return [{"time": idx.strftime("%Y-%m-%d"), "value": round(float(v), 2)} for idx, v in sub.items()]

            overlay_js = ""
            color_i = 0
            for name in overlays:
                if name == "Bollinger Bands":
                    for col, color in [("BB_High", "#B4B2A9"), ("BB_Mid", "#888780"), ("BB_Low", "#B4B2A9")]:
                        overlay_js += f"""
                        {{
                          const s = chart.addLineSeries({{ color: '{color}', lineWidth: 1 }});
                          s.setData({json.dumps(series_data(col))});
                        }}"""
                else:
                    col = name.replace(" ", "")
                    color = OVERLAY_COLORS_PALETTE[color_i % len(OVERLAY_COLORS_PALETTE)]
                    color_i += 1
                    if col in df.columns:
                        overlay_js += f"""
                        {{
                          const s = chart.addLineSeries({{ color: '{color}', lineWidth: 1.5 }});
                          s.setData({json.dumps(series_data(col))});
                        }}"""

            def pane_key(name):
                return name.lower().replace(" ", "_").replace("%", "pct")

            panes_html = ""
            panes_js = ""
            for name in oscillators:
                key = pane_key(name)
                panes_html += (
                    f'<div style="font-family:monospace; font-size:12px; color:#666; '
                    f'padding:6px 2px 2px;">{name}</div>'
                    f'<div id="chart_{key}" style="width:100%; height:150px;"></div>'
                )
                base_chart_js = f"""
                const chart_{key} = LightweightCharts.createChart(document.getElementById('chart_{key}'), {{
                  width: container.clientWidth, height: 150,
                  layout: {{ background: {{ color: '#ffffff' }}, textColor: '#333' }},
                  grid: {{ vertLines: {{ color: '#eee' }}, horzLines: {{ color: '#eee' }} }},
                  timeScale: {{ visible: true, borderColor: '#ccc' }},
                  rightPriceScale: {{ borderColor: '#ccc' }},
                  crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }}
                }});
                chart_{key}.addLineSeries({{ color: 'rgba(0,0,0,0)', lineWidth: 0 }}).setData({json.dumps(anchor)});
                allCharts.push(chart_{key});
                """
                if name.startswith("RSI"):
                    col = name.replace(" ", "")
                    panes_js += base_chart_js + f"""
                    const line_{key} = chart_{key}.addLineSeries({{ color: '#D4A24C', lineWidth: 1.5 }});
                    line_{key}.setData({json.dumps(series_data(col))});
                    line_{key}.createPriceLine({{ price: 70, color: '#D85A30', lineWidth: 1, lineStyle: 2 }});
                    line_{key}.createPriceLine({{ price: 30, color: '#1D9E75', lineWidth: 1, lineStyle: 2 }});
                    """
                elif name == "MACD":
                    panes_js += base_chart_js + f"""
                    chart_{key}.addHistogramSeries({{ color: '#B4B2A9' }}).setData({json.dumps(series_data('MACD_Hist'))});
                    chart_{key}.addLineSeries({{ color: '#378ADD', lineWidth: 1.5 }}).setData({json.dumps(series_data('MACD'))});
                    chart_{key}.addLineSeries({{ color: '#D85A30', lineWidth: 1.5 }}).setData({json.dumps(series_data('MACD_Signal'))});
                    """
                elif name == "Stochastic":
                    panes_js += base_chart_js + f"""
                    const kLine_{key} = chart_{key}.addLineSeries({{ color: '#378ADD', lineWidth: 1.5 }});
                    kLine_{key}.setData({json.dumps(series_data('Stoch_%K'))});
                    chart_{key}.addLineSeries({{ color: '#D85A30', lineWidth: 1.5 }}).setData({json.dumps(series_data('Stoch_%D'))});
                    kLine_{key}.createPriceLine({{ price: 80, color: '#D85A30', lineWidth: 1, lineStyle: 2 }});
                    kLine_{key}.createPriceLine({{ price: 20, color: '#1D9E75', lineWidth: 1, lineStyle: 2 }});
                    """
                elif name == "ADX":
                    panes_js += base_chart_js + f"""
                    const adxLine_{key} = chart_{key}.addLineSeries({{ color: '#534AB7', lineWidth: 1.5 }});
                    adxLine_{key}.setData({json.dumps(series_data('ADX'))});
                    adxLine_{key}.createPriceLine({{ price: 25, color: '#888780', lineWidth: 1, lineStyle: 2 }});
                    """

            volume_js = ""
            if show_volume:
                volume_js = f"""
                const volumeSeries = chart.addHistogramSeries({{
                  priceFormat: {{ type: 'volume' }},
                  priceScaleId: 'vol'
                }});
                chart.priceScale('vol').applyOptions({{
                  scaleMargins: {{ top: 0.85, bottom: 0 }},
                  visible: false
                }});
                volumeSeries.setData({json.dumps(volumes)});
                """

            CHART_HTML = f"""
            <div id="legend" style="font-family:monospace; font-size:13px; padding:4px 2px 8px;"></div>
            <div id="chart_container" style="width:100%; height:480px;"></div>
            {panes_html}
            <script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
            <script>
              const container = document.getElementById('chart_container');
              const allCharts = [];

              const chart = LightweightCharts.createChart(container, {{
                width: container.clientWidth,
                height: 480,
                layout: {{ background: {{ color: '#ffffff' }}, textColor: '#333' }},
                grid: {{ vertLines: {{ color: '#eee' }}, horzLines: {{ color: '#eee' }} }},
                timeScale: {{ timeVisible: true, borderColor: '#ccc' }},
                rightPriceScale: {{ borderColor: '#ccc' }},
                crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
                handleScroll: true,
                handleScale: true
              }});
              allCharts.push(chart);

              const candleSeries = chart.addCandlestickSeries({{
                upColor: '#1D9E75', downColor: '#D85A30',
                borderVisible: false,
                wickUpColor: '#1D9E75', wickDownColor: '#D85A30'
              }});
              candleSeries.setData({json.dumps(candles)});

              {volume_js}
              {overlay_js}
              {panes_js}

              const legend = document.getElementById('legend');
              function fmt(p) {{ return p === undefined ? '' : p.toFixed(2); }}
              chart.subscribeCrosshairMove(param => {{
                if (!param.time || !param.seriesData.get(candleSeries)) {{
                  legend.innerHTML = '{symbol} — {timeframe}';
                  return;
                }}
                const d = param.seriesData.get(candleSeries);
                legend.innerHTML =
                  '{symbol} — {timeframe} &nbsp; O ' + fmt(d.open) +
                  ' &nbsp; H ' + fmt(d.high) +
                  ' &nbsp; L ' + fmt(d.low) +
                  ' &nbsp; C ' + fmt(d.close);
              }});

              let syncing = false;
              allCharts.forEach((c, idx) => {{
                c.timeScale().subscribeVisibleLogicalRangeChange(range => {{
                  if (syncing || !range) return;
                  syncing = true;
                  allCharts.forEach((other, j) => {{
                    if (j !== idx) other.timeScale().setVisibleLogicalRange(range);
                  }});
                  syncing = false;
                }});
              }});

              chart.timeScale().fitContent();
              window.addEventListener('resize', () => {{
                allCharts.forEach(c => c.applyOptions({{ width: container.clientWidth }}));
              }});
            </script>
            """
            total_height = 520 + len(oscillators) * 175
            components.html(CHART_HTML, height=total_height, scrolling=False)

            # ---- Key fundamentals ----
            st.markdown("##### Key Fundamentals")
            fund = fetch_fundamentals(ticker)
            if fund is None:
                st.caption("Fundamental data not available for this stock.")
            else:
                f1, f2, f3, f4, f5, f6 = st.columns(6)
                f1.metric("Market Cap", format_market_cap(fund["Market Cap"]))
                f2.metric("P/E (TTM)", format_number(fund["P/E (TTM)"]))
                f3.metric("P/B", format_number(fund["P/B"]))
                f4.metric("EPS (TTM)", format_number(fund["EPS (TTM)"], suffix=""))
                f5.metric("Dividend Yield", format_percent(fund["Dividend Yield"]))
                f6.metric("ROE", format_percent(fund["ROE"]))

                g1, g2, g3, g4, g5, g6 = st.columns(6)
                g1.metric("52W High", format_number(fund["52W High"]))
                g2.metric("52W Low", format_number(fund["52W Low"]))
                g3.metric("Debt/Equity", format_number(fund["Debt/Equity"]))
                g4.metric("Profit Margin", format_percent(fund["Profit Margin"]))
                g5.metric("Forward P/E", format_number(fund["Forward P/E"]))
                g6.metric("Sector", fund["Sector"] or "—")

                if fund["Industry"]:
                    st.caption(f"Industry: {fund['Industry']}")
