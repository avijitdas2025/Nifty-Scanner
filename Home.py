"""
Home.py — entry point for the app. Run this with:
    streamlit run Home.py

Streamlit automatically turns the "pages" folder into a sidebar menu:
  - 📈 Chart   — TradingView-style watchlist + candlestick chart
  - 🔍 Scanner — build rules, scan NIFTY 500, save shortlists as watchlists
"""

import streamlit as st
from common import apply_theme

st.set_page_config(page_title="NIFTY 500 Toolkit", layout="wide", page_icon="📊")
apply_theme("NIFTY 500 Toolkit")

st.title("📊 NIFTY 500 Toolkit")
st.write(
    "Use the sidebar to switch between the two workspaces:"
)
st.markdown(
    """
- **📈 Chart** — Click any stock in the watchlist
  (defaults to all NIFTY 500) to load its candlestick chart. Scroll to zoom,
  drag to pan, hover a candle to see its Open/High/Low/Close.
- **🔍 Scanner** — build rules across Daily/Weekly/Monthly timeframes, scan
  the NIFTY 500, and save your shortlist as a watchlist. Saved watchlists
  automatically appear as a selectable source on the Chart page.
"""
)
st.info("Pick a page from the sidebar on the left to get started.")
