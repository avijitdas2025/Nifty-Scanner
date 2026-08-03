"""
common.py
---------
Shared helpers used by both pages/1_Chart.py and pages/2_Scanner.py:
  - Loading the NIFTY 500 constituent list (live from NSE, with manual
    CSV upload fallback)
  - Fetching + resampling price data
  - Saving/loading watchlists as local CSV files
"""

import io
import os
import json
import datetime as dt

import pandas as pd
import requests
import streamlit as st
import yfinance as yf
import ta

NSE_500_URL = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
WATCHLIST_DIR = os.path.join(BASE_DIR, "watchlists")
SETTINGS_FILE = os.path.join(BASE_DIR, "indicator_settings.json")
os.makedirs(WATCHLIST_DIR, exist_ok=True)


# ----------------------------------------------------------------------
# NIFTY 500 LIST
# ----------------------------------------------------------------------
@st.cache_data(ttl=60 * 60 * 24, show_spinner=False)
def load_nifty500_from_nse():
    """Try to download the live NIFTY 500 list directly from NSE."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept": "text/csv,application/csv,*/*",
    }
    resp = requests.get(NSE_500_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    df.columns = [c.strip() for c in df.columns]
    symbol_col = [c for c in df.columns if c.lower() == "symbol"][0]
    name_col = [c for c in df.columns if "company" in c.lower()][0]
    out = df[[symbol_col, name_col]].rename(columns={symbol_col: "Symbol", name_col: "Company"})
    out["Symbol"] = out["Symbol"].str.strip()
    out["YF_Ticker"] = out["Symbol"] + ".NS"
    return out


def load_nifty500_list(sidebar=True):
    """Load the list, falling back to a manual CSV upload if NSE blocks us."""
    target = st.sidebar if sidebar else st
    try:
        df = load_nifty500_from_nse()
        if len(df) > 400:
            return df
    except Exception as e:
        target.warning(f"Could not auto-download NSE list ({e}).")

    target.info(
        "Upload the NIFTY 500 list instead. Download it from: "
        "https://www.niftyindices.com/indices/equity/broad-based-indices/nifty-500 "
        "(look for 'Download list of constituents' — CSV)."
    )
    uploaded = target.file_uploader("Upload NIFTY 500 CSV", type=["csv"], key="nifty_upload")
    if uploaded is not None:
        df = pd.read_csv(uploaded)
        df.columns = [c.strip() for c in df.columns]
        symbol_col = [c for c in df.columns if c.lower() == "symbol"][0]
        name_col = [c for c in df.columns if "company" in c.lower()][0]
        out = df[[symbol_col, name_col]].rename(columns={symbol_col: "Symbol", name_col: "Company"})
        out["Symbol"] = out["Symbol"].str.strip()
        out["YF_Ticker"] = out["Symbol"] + ".NS"
        return out
    return None


# ----------------------------------------------------------------------
# PRICE DATA
# ----------------------------------------------------------------------
@st.cache_data(ttl=60 * 60 * 6, show_spinner=False)
def fetch_daily_data(ticker, years=5):
    """Download daily OHLCV data for a ticker."""
    end = dt.date.today()
    start = end - dt.timedelta(days=365 * years)
    df = yf.download(ticker, start=start, end=end, interval="1d", progress=False, auto_adjust=True)
    if df.empty:
        return None
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna()


def resample_ohlc(daily_df, timeframe):
    """Convert daily OHLCV into Weekly or Monthly bars."""
    if timeframe == "Daily":
        return daily_df
    rule = "W" if timeframe == "Weekly" else "ME"
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    return daily_df.resample(rule).agg(agg).dropna()


@st.cache_data(ttl=60 * 60 * 12, show_spinner=False)
def fetch_fundamentals(ticker):
    """
    Pull key fundamental metrics for a ticker via Yahoo Finance.
    Returns a dict — any field Yahoo doesn't have for this stock is None.
    """
    try:
        info = yf.Ticker(ticker).info
    except Exception:
        return None
    if not info or info.get("regularMarketPrice") is None and info.get("currentPrice") is None:
        return None
    return {
        "Market Cap": info.get("marketCap"),
        "P/E (TTM)": info.get("trailingPE"),
        "Forward P/E": info.get("forwardPE"),
        "P/B": info.get("priceToBook"),
        "EPS (TTM)": info.get("trailingEps"),
        "Dividend Yield": info.get("dividendYield"),
        "52W High": info.get("fiftyTwoWeekHigh"),
        "52W Low": info.get("fiftyTwoWeekLow"),
        "ROE": info.get("returnOnEquity") or _fallback_roe(info),
        "Debt/Equity": info.get("debtToEquity"),
        "Profit Margin": info.get("profitMargins"),
        "Sector": info.get("sector"),
        "Industry": info.get("industry"),
    }


def _fallback_roe(info):
    """Some NSE stocks don't have Yahoo's direct returnOnEquity field.
    Approximate ROE as EPS / Book Value per share when both are available."""
    eps = info.get("trailingEps")
    book_value = info.get("bookValue")
    if eps and book_value and book_value != 0:
        return eps / book_value
    return None


def format_market_cap(value):
    """Format a raw INR market cap number as Cr (crores)."""
    if value is None:
        return "—"
    crores = value / 1e7
    if crores >= 1e5:
        return f"₹{crores/1e5:,.2f} Lakh Cr"
    return f"₹{crores:,.0f} Cr"


def format_number(value, suffix="", decimals=2):
    if value is None:
        return "—"
    return f"{value:,.{decimals}f}{suffix}"


def format_percent(value):
    if value is None:
        return "—"
    return f"{value*100:,.2f}%"


# ----------------------------------------------------------------------
# INDICATOR SETTINGS — saved locally so your periods/parameters and
# on-chart selections persist across app restarts.
# ----------------------------------------------------------------------
DEFAULT_SETTINGS = {
    "sma_periods": [20, 50, 200],
    "ema_periods": [20, 50],
    "rsi_periods": [14],
    "macd": {"fast": 12, "slow": 26, "signal": 9},
    "bollinger": {"window": 20, "dev": 2.0},
    "stochastic": {"k": 14, "d": 3},
    "adx_period": 14,
    # Which computed indicators are actually switched on, per page:
    "chart_overlays": ["SMA 20", "SMA 50", "SMA 200"],
    "chart_oscillators": ["RSI 14"],
    "chart_show_volume": True,
    "scanner_overlays": ["SMA 20", "SMA 50", "SMA 200", "Bollinger Bands"],
    "scanner_oscillators": ["RSI 14", "MACD"],
}


def load_indicator_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                loaded = json.load(f)
            merged = DEFAULT_SETTINGS.copy()
            merged.update(loaded)
            return merged
        except Exception:
            pass
    return DEFAULT_SETTINGS.copy()


def save_indicator_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=2)


# ----------------------------------------------------------------------
# INDICATORS (shared by the Chart page's indicator picker and the Scanner)
# ----------------------------------------------------------------------
def compute_indicators(df, settings=None):
    """
    Add indicator columns using periods/parameters from `settings`
    (falls back to DEFAULT_SETTINGS if not given). Column naming:
      SMA{p}, EMA{p}, RSI{p}  — one column per configured period
      MACD, MACD_Signal, MACD_Hist
      BB_High, BB_Mid, BB_Low
      Stoch_%K, Stoch_%D
      ADX
    """
    s = settings or DEFAULT_SETTINGS
    df = df.copy()
    close, high, low = df["Close"], df["High"], df["Low"]

    for p in s.get("sma_periods", []):
        df[f"SMA{p}"] = ta.trend.sma_indicator(close, window=int(p))
    for p in s.get("ema_periods", []):
        df[f"EMA{p}"] = ta.trend.ema_indicator(close, window=int(p))
    for p in s.get("rsi_periods", []):
        df[f"RSI{p}"] = ta.momentum.rsi(close, window=int(p))

    m = s.get("macd", DEFAULT_SETTINGS["macd"])
    macd = ta.trend.MACD(close, window_slow=int(m["slow"]), window_fast=int(m["fast"]), window_sign=int(m["signal"]))
    df["MACD"] = macd.macd()
    df["MACD_Signal"] = macd.macd_signal()
    df["MACD_Hist"] = macd.macd_diff()

    b = s.get("bollinger", DEFAULT_SETTINGS["bollinger"])
    bb = ta.volatility.BollingerBands(close, window=int(b["window"]), window_dev=float(b["dev"]))
    df["BB_High"] = bb.bollinger_hband()
    df["BB_Low"] = bb.bollinger_lband()
    df["BB_Mid"] = bb.bollinger_mavg()

    st_p = s.get("stochastic", DEFAULT_SETTINGS["stochastic"])
    stoch = ta.momentum.StochasticOscillator(high, low, close, window=int(st_p["k"]), smooth_window=int(st_p["d"]))
    df["Stoch_%K"] = stoch.stoch()
    df["Stoch_%D"] = stoch.stoch_signal()

    adx = ta.trend.ADXIndicator(high, low, close, window=int(s.get("adx_period", 14)))
    df["ADX"] = adx.adx()

    return df


def parse_periods(text, fallback):
    """Parse a comma-separated string like '20, 50, 200' into a sorted int list."""
    try:
        vals = sorted(set(int(x.strip()) for x in text.split(",") if x.strip()))
        return vals if vals else fallback
    except Exception:
        return fallback


# ----------------------------------------------------------------------
# RULE ENGINE — options are generated dynamically from your configured
# SMA/EMA/RSI periods, so if you set RSI periods to "14,21" you'll see
# rules for both RSI(14) and RSI(21) automatically.
# ----------------------------------------------------------------------
def _last(df, col):
    return df[col].iloc[-1]


def _prev(df, col):
    return df[col].iloc[-2]


def build_rule_options(settings):
    """Returns (RULE_OPTIONS dict, NEEDS_VALUE set) built from `settings`."""
    rules = {}
    needs_value = set()

    for p in settings.get("rsi_periods", [14]):
        col = f"RSI{p}"
        rules[f"RSI({p}) above"] = (lambda df, val, c=col: _last(df, c) > val)
        rules[f"RSI({p}) below"] = (lambda df, val, c=col: _last(df, c) < val)
        rules[f"RSI({p}) crossed above"] = (lambda df, val, c=col: _prev(df, c) < val <= _last(df, c))
        rules[f"RSI({p}) crossed below"] = (lambda df, val, c=col: _prev(df, c) > val >= _last(df, c))
        needs_value |= {f"RSI({p}) above", f"RSI({p}) below", f"RSI({p}) crossed above", f"RSI({p}) crossed below"}

    for p in settings.get("sma_periods", [20, 50, 200]):
        col = f"SMA{p}"
        rules[f"Price above SMA{p}"] = (lambda df, val, c=col: _last(df, "Close") > _last(df, c))
        rules[f"Price below SMA{p}"] = (lambda df, val, c=col: _last(df, "Close") < _last(df, c))
        rules[f"SMA{p} rising (vs N bars ago)"] = (
            lambda df, val, c=col: df[c].iloc[-1] > df[c].iloc[-1 - int(val)]
        )
        rules[f"SMA{p} falling (vs N bars ago)"] = (
            lambda df, val, c=col: df[c].iloc[-1] < df[c].iloc[-1 - int(val)]
        )
        needs_value |= {f"SMA{p} rising (vs N bars ago)", f"SMA{p} falling (vs N bars ago)"}

    for p in settings.get("ema_periods", [20, 50]):
        col = f"EMA{p}"
        rules[f"EMA{p} rising (vs N bars ago)"] = (
            lambda df, val, c=col: df[c].iloc[-1] > df[c].iloc[-1 - int(val)]
        )
        rules[f"EMA{p} falling (vs N bars ago)"] = (
            lambda df, val, c=col: df[c].iloc[-1] < df[c].iloc[-1 - int(val)]
        )
        needs_value |= {f"EMA{p} rising (vs N bars ago)", f"EMA{p} falling (vs N bars ago)"}

    sma_periods = sorted(settings.get("sma_periods", [20, 50, 200]))
    if len(sma_periods) >= 2:
        fast, slow = sma_periods[-2], sma_periods[-1]
        rules[f"Golden Cross (SMA{fast} > SMA{slow})"] = (
            lambda df, val, f=f"SMA{fast}", s=f"SMA{slow}": _last(df, f) > _last(df, s)
        )
        rules[f"Death Cross (SMA{fast} < SMA{slow})"] = (
            lambda df, val, f=f"SMA{fast}", s=f"SMA{slow}": _last(df, f) < _last(df, s)
        )

    rules["MACD bullish (MACD > Signal)"] = lambda df, val: _last(df, "MACD") > _last(df, "MACD_Signal")
    rules["MACD bearish (MACD < Signal)"] = lambda df, val: _last(df, "MACD") < _last(df, "MACD_Signal")
    rules["MACD crossed bullish"] = lambda df, val: (
        _prev(df, "MACD") <= _prev(df, "MACD_Signal") and _last(df, "MACD") > _last(df, "MACD_Signal")
    )
    rules["MACD crossed bearish"] = lambda df, val: (
        _prev(df, "MACD") >= _prev(df, "MACD_Signal") and _last(df, "MACD") < _last(df, "MACD_Signal")
    )

    rules["Near lower Bollinger Band (within %)"] = (
        lambda df, val: (_last(df, "Close") - _last(df, "BB_Low")) / _last(df, "Close") * 100 < val
    )
    rules["Near upper Bollinger Band (within %)"] = (
        lambda df, val: (_last(df, "BB_High") - _last(df, "Close")) / _last(df, "Close") * 100 < val
    )
    needs_value |= {"Near lower Bollinger Band (within %)", "Near upper Bollinger Band (within %)"}

    rules["Stochastic %K above"] = lambda df, val: _last(df, "Stoch_%K") > val
    rules["Stochastic %K below"] = lambda df, val: _last(df, "Stoch_%K") < val
    needs_value |= {"Stochastic %K above", "Stochastic %K below"}

    rules["ADX above (strong trend)"] = lambda df, val: _last(df, "ADX") > val
    needs_value.add("ADX above (strong trend)")

    return rules, needs_value


def passes_rules(tf_dfs, active_rules, rule_options):
    """
    tf_dfs: dict like {"Weekly": df, "Monthly": df} (only timeframes actually used).
    active_rules: list of (timeframe, rule_name, value). Stock must pass ALL.
    """
    try:
        for timeframe, rule_name, val in active_rules:
            df = tf_dfs.get(timeframe)
            if df is None or len(df) < 30:
                return False
            if not rule_options[rule_name](df, val):
                return False
        return True
    except Exception:
        return False


def apply_theme(page_title, page_icon="📈"):
    """
    Call once at the top of every page, right after st.set_page_config().
    Applies consistent typography, spacing, and component styling on top of
    the base theme in .streamlit/config.toml.
    """
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
        }

        /* Tighter, cleaner top padding */
        .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
            max-width: 1400px;
        }

        /* Page titles */
        h1 {
            font-weight: 700 !important;
            letter-spacing: -0.02em;
            font-size: 1.9rem !important;
        }
        h2, h3 {
            font-weight: 600 !important;
            letter-spacing: -0.01em;
        }

        /* Buttons: flatter, more deliberate */
        .stButton > button {
            border-radius: 6px;
            border: 1px solid #E4E2DC;
            font-weight: 500;
            transition: all 0.15s ease;
        }
        .stButton > button:hover {
            border-color: #1D9E75;
            color: #1D9E75;
        }
        .stButton > button[kind="primary"] {
            background-color: #1D9E75;
            border: none;
        }
        .stButton > button[kind="primary"]:hover {
            background-color: #17835F;
        }

        /* Sidebar: subtle separation from main content */
        section[data-testid="stSidebar"] {
            background-color: #F3F2EE;
            border-right: 1px solid #E4E2DC;
        }
        section[data-testid="stSidebar"] h2 {
            font-size: 0.95rem !important;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            color: #6B6A63;
            margin-top: 1.2rem;
        }

        /* Dataframes / tables */
        [data-testid="stDataFrame"] {
            border: 1px solid #E4E2DC;
            border-radius: 8px;
        }

        /* Metrics: prevent value truncation ("...") when text is a bit long */
        [data-testid="stMetric"] {
            background-color: #FFFFFF;
            border: 1px solid #E4E2DC;
            border-radius: 8px;
            padding: 0.7rem 0.8rem;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.1rem !important;
            white-space: normal !important;
            overflow: visible !important;
            text-overflow: unset !important;
            line-height: 1.3 !important;
        }
        [data-testid="stMetricLabel"] {
            white-space: normal !important;
            overflow: visible !important;
        }

        /* Metric-like captions */
        .stCaption, [data-testid="stCaptionContainer"] {
            color: #8B8A82 !important;
        }

        /* Hide default Streamlit chrome for a cleaner, product-like feel */
        #MainMenu { visibility: hidden; }
        footer { visibility: hidden; }

        /* Input fields */
        .stTextInput > div > div > input,
        .stSelectbox > div > div,
        .stNumberInput > div > div > input {
            border-radius: 6px;
        }

        /* Expander header */
        .streamlit-expanderHeader {
            font-weight: 500;
            border-radius: 6px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ----------------------------------------------------------------------
# WATCHLISTS (saved as local CSV files under ./watchlists/)
# ----------------------------------------------------------------------
def list_saved_watchlists():
    files = [f[:-4] for f in os.listdir(WATCHLIST_DIR) if f.endswith(".csv")]
    return sorted(files)


def save_watchlist(name, df):
    safe_name = "".join(c for c in name if c.isalnum() or c in ("_", "-", " ")).strip()
    if not safe_name:
        return None
    path = os.path.join(WATCHLIST_DIR, f"{safe_name}.csv")
    df_to_save = df.copy()
    df_to_save["Saved On"] = dt.date.today().isoformat()
    if os.path.exists(path):
        existing = pd.read_csv(path)
        combined = pd.concat([existing, df_to_save], ignore_index=True)
        combined = combined.drop_duplicates(subset=["Symbol"], keep="last")
        combined.to_csv(path, index=False)
    else:
        df_to_save.to_csv(path, index=False)
    return path


def load_watchlist(name):
    path = os.path.join(WATCHLIST_DIR, f"{name}.csv")
    if os.path.exists(path):
        return pd.read_csv(path)
    return None


def delete_watchlist(name):
    path = os.path.join(WATCHLIST_DIR, f"{name}.csv")
    if os.path.exists(path):
        os.remove(path)
        return True
    return False
