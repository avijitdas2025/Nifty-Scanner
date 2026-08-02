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
    rule = "W" if timeframe == "Weekly" else "M"
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    return daily_df.resample(rule).agg(agg).dropna()


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
