# NIFTY 500 Toolkit — Setup Guide

This app runs on your own computer and opens in your web browser. No coding
needed after these one-time setup steps.

## What you get

Two workspaces, switchable from the sidebar:

- **📈 Chart** — a TradingView-style view. A watchlist panel on the left
  (defaults to all NIFTY 500 stocks) lists every symbol; click one to load
  its candlestick chart on the right. Scroll to zoom, click-and-drag to
  pan, hover any candle to see its Open/High/Low/Close in the legend —
  the same interactions as tradingview.com, since it uses TradingView's
  own open-source charting library.
- **🔍 Scanner** — build shortlisting rules that can mix timeframes (e.g.
  Monthly RSI above 60 AND Weekly RSI crossed above 60), scan all 500
  stocks, and save the result as a named watchlist. Saved watchlists
  automatically show up as a selectable source on the Chart page.

## Step 1: Install Python (one-time, ~5 minutes)

1. Go to https://www.python.org/downloads/
2. Download the latest version for your operating system.
3. Run the installer.
   - **Windows only:** tick "Add Python to PATH" before clicking Install.

## Step 2: Get the app files

Put these files in one folder, e.g. `Documents/NiftyToolkit/`, **keeping
the folder structure exactly as given**:

```
NiftyToolkit/
├── Home.py
├── common.py
├── requirements.txt
├── README.md
└── pages/
    ├── 1_Chart.py
    └── 2_Scanner.py
```

## Step 3: Open a terminal in that folder

- **Windows:** Open the folder in File Explorer, click the address bar,
  type `cmd`, press Enter.
- **Mac:** Open Terminal, type `cd ` (with a space), drag the folder into
  the Terminal window, press Enter.

## Step 4: Install the required packages (one-time)

```
pip install -r requirements.txt
```

If `pip` isn't recognized on Windows, try `pip3` or
`python -m pip install -r requirements.txt`.

## Step 5: Run the app

```
streamlit run Home.py
```

Your browser opens automatically to `http://localhost:8501`. Use the
sidebar to switch between **Chart** and **Scanner**. To stop the app,
go back to the terminal and press `Ctrl + C`.

## Using the Chart page

1. **Watchlist dropdown** at the top: choose "NIFTY 500 (all)" (default)
   or any watchlist you've saved from the Scanner page.
2. **Search box**: type a symbol or company name to jump to it directly —
   without a search, the panel shows the first 60 stocks (loading all 500
   candlesticks up front would be slow, so this keeps it responsive).
3. **Click any stock** in the left panel — the chart on the right updates
   immediately.
4. **Timeframe**: Daily / Weekly / Monthly, applies to whichever stock is
   selected.
5. On the chart itself: **scroll to zoom**, **click-and-drag to pan**,
   **hover a candle** to see its OHLC values in the small legend above
   the chart.
6. This page ships with no indicator overlays by design, since you're
   adding your own. Open `pages/1_Chart.py` and look for the comment
   `ADD YOUR OWN INDICATORS HERE` — add a line series the same way the
   candlestick and volume series are set up, with your own computed values.

## Using the Scanner page

1. **Sidebar → Stock Universe**: auto-downloads the NIFTY 500 list from
   NSE. If NSE blocks the automatic download, upload the CSV yourself
   (download from niftyindices.com → NIFTY 500 → "Download list of
   constituents").
2. **Build rules**: each rule has its own timeframe dropdown plus a
   condition, so you can mix timeframes in a single scan, e.g.:
   - Rule 1: **Monthly** → RSI(14) above → 60
   - Rule 2: **Weekly** → RSI(14) crossed above → 60

   "Crossed above/below" only fires on the bar where the value actually
   crosses the threshold, unlike "above/below" which just checks where
   it currently sits. Click "Add another rule" for more conditions — a
   stock must pass ALL of them to be shortlisted.
3. Click **Scan NIFTY 500**. The first scan takes a few minutes since it
   downloads price history for up to 500 stocks — repeat scans within
   the same day are faster since results are cached.
4. Review the shortlist, inspect any stock's chart with RSI/MACD panels,
   then **save it as a watchlist** by typing a name and clicking save.
   Saving again under the same name updates existing symbols and adds new
   ones rather than duplicating rows.
5. Switch to the Chart page — your saved watchlist now appears in the
   watchlist dropdown at the top.

## Want your own indicators or rules in the Scanner too?

Open `pages/2_Scanner.py`:
- Add a new column inside `compute_indicators()`.
- Add a new entry to `RULE_OPTIONS` (a function that reads the last one or
  two rows of the dataframe and returns True/False). If it needs a number
  from the user, add its name to `NEEDS_VALUE` too. It appears in the
  rule-builder automatically — no other changes needed.

## Customising and saving indicators

Both pages now have an **⚙️ Customise periods / parameters** panel:
- SMA / EMA / RSI accept comma-separated periods, so you can set
  `30,44` for SMA or `14,21` for RSI — any custom lengths you want.
- MACD, Bollinger Bands, Stochastic, and ADX each have their own
  adjustable parameters (fast/slow/signal, window/std-dev, %K/%D, period).

Click **💾 Save indicator parameters** and they're written to
`indicator_settings.json` next to `Home.py` — shared by both pages, so a
period you set on one page is available on the other too.

On the Chart page, the **Overlays** / **Oscillator panes** / **Show volume**
selections are separate from the parameters above — pick which indicators
you actually want to *see*, then click **💾 Save as default** to remember
that choice for next time. The Scanner's inspect-chart has its own
save-as-default picker too, so the two pages can show different indicators
if you like.

Rules on the Scanner page are generated from whatever periods you've
configured — set RSI periods to `14,21` and you'll see rule options for
both RSI(14) and RSI(21) automatically.

## Making it portable to other machines / phone access

Copy the whole folder (keeping the `pages/` subfolder) to any other
computer and repeat Steps 1–5. For phone access without installing
anything, host it for free on Streamlit Community Cloud (share.streamlit.io)
— ask me if you'd like the walkthrough for that.

## Notes

- Data comes from Yahoo Finance. Indian tickers are queried with a `.NS`
  suffix (e.g. `RELIANCE.NS`), added automatically.
- Watchlists are saved as plain CSV files in a `watchlists` folder that's
  created automatically next to `Home.py` the first time you save one.
- If a rule combination returns 0 results on the Scanner, try loosening
  thresholds (e.g. RSI above 50 instead of above 60).
