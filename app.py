"""ETF tracker dashboard (Streamlit Community Cloud — free hosting)."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from config import (
    ETFS, REFRESH_SECONDS, MONTHLY_SIP_BUDGET, MONTHLY_DIP_BUDGET,
    DIP_THRESHOLD_PCT, NTFY_TOPIC,
)
from data_feed import fetch_quotes, fetch_ohlc, is_market_open
import upstox_feed

st.set_page_config(page_title="ETF Tracker", page_icon="📈", layout="wide")


def _upstox_secrets():
    """(api_key, api_secret, redirect_uri) from Streamlit secrets, or Nones."""
    try:
        return (st.secrets["UPSTOX_API_KEY"], st.secrets["UPSTOX_API_SECRET"],
                st.secrets["UPSTOX_REDIRECT_URI"])
    except Exception:
        return (None, None, None)


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def get_quotes_yf():
    return fetch_quotes()


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def get_quotes_upstox(token):
    return upstox_feed.fetch_quotes(token)


def get_quotes():
    """Real-time Upstox if connected, else delayed yfinance. Returns (quotes, source)."""
    token = st.session_state.get("upstox_token")
    if token:
        try:
            q = get_quotes_upstox(token)
            if q:
                return q, "Upstox (real-time)"
        except Exception as e:
            st.session_state.pop("upstox_token", None)   # likely expired
            st.session_state["upstox_error"] = f"Upstox failed ({e}); using delayed data."
    return get_quotes_yf(), "Yahoo Finance (~15 min delayed)"


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def get_ohlc(ticker, period, interval):
    return fetch_ohlc(ticker, period=period, interval=interval)   # charts stay on yfinance


# ---- Upstox OAuth: capture ?code= from the redirect and swap for a token ----
api_key, api_secret, redirect_uri = _upstox_secrets()
if api_key and "code" in st.query_params and not st.session_state.get("upstox_token"):
    try:
        st.session_state["upstox_token"] = upstox_feed.exchange_code(
            api_key, api_secret, redirect_uri, st.query_params["code"])
        st.session_state.pop("upstox_error", None)
    except Exception as e:
        st.session_state["upstox_error"] = f"Login failed: {e}"
    st.query_params.clear()

# ---- Sidebar: data source / Upstox connection ----
with st.sidebar:
    st.header("Data source")
    if not api_key:
        st.caption("Add UPSTOX_API_KEY / _SECRET / _REDIRECT_URI in Streamlit "
                   "secrets to enable real-time. Until then: delayed yfinance.")
    elif st.session_state.get("upstox_token"):
        st.success("🟢 Upstox connected (real-time)")
        if st.button("Disconnect"):
            st.session_state.pop("upstox_token", None)
            st.rerun()
    else:
        st.info("Delayed data (yfinance). Connect Upstox for real-time:")
        st.link_button("🔑 Connect Upstox", upstox_feed.get_auth_url(api_key, redirect_uri))
        st.caption("Token expires daily (~03:30 IST) — reconnect each morning.")
    if st.session_state.get("upstox_error"):
        st.warning(st.session_state["upstox_error"])

# Auto-refresh only while the market is open.
if is_market_open():
    st_autorefresh(interval=REFRESH_SECONDS * 1000, key="refresh")

# ---- Header --------------------------------------------------------------
st.title("📈 ETF Portfolio Tracker")
open_now = is_market_open()
status = "🟢 Market open" if open_now else "🔴 Market closed"
refresh_note = f"auto-refresh {REFRESH_SECONDS}s" if open_now else "auto-refresh paused"

quotes, source = get_quotes()
if not quotes:
    st.error("No market data returned. Try again in a moment, or check ticker symbols in config.py.")
    st.stop()
st.caption(f"{status} · {refresh_note} · source: {source}")

# ---- Build the table -----------------------------------------------------
rows = [{
    "Ticker": tk, "Name": q["name"], "Alloc %": q["alloc"], "Freq": q["freq"],
    "Price ₹": q["price"], "Open ₹": q["open"], "Prev ₹": q["prev_close"],
    "% vs Open": q["pct_from_open"], "% vs Prev": q["pct_from_prev"],
} for tk, q in quotes.items()]
df = pd.DataFrame(rows).sort_values("% vs Open", na_position="last")

dips = df[df["% vs Open"] <= -DIP_THRESHOLD_PCT]

# Allocation-weighted day move (vs previous close), skipping missing data.
wdf = df.dropna(subset=["% vs Prev"])
day_move = (wdf["Alloc %"] * wdf["% vs Prev"]).sum() / wdf["Alloc %"].sum() if not wdf.empty else 0.0

# ---- Summary metrics -----------------------------------------------------
m1, m2, m3, m4 = st.columns(4)
m1.metric("Portfolio day move", f"{day_move:+.2f}%", help="Allocation-weighted change vs yesterday's close")
m2.metric("ETFs dipping", f"{len(dips)}", help=f"≥ {DIP_THRESHOLD_PCT:.0f}% below today's open")
m3.metric("Monthly SIP", f"₹{MONTHLY_SIP_BUDGET:,}")
m4.metric("Dip budget", f"₹{MONTHLY_DIP_BUDGET:,}")

st.divider()

# ---- Tabs (declutter) ----------------------------------------------------
tab_prices, tab_chart, tab_alloc, tab_help = st.tabs(
    ["📊 Prices", "📈 Chart", "🥧 Allocation", "ℹ️ How it works"]
)


def color_pct(v):
    """Light-theme friendly red/green for % columns."""
    if pd.isna(v):
        return ""
    if v <= -DIP_THRESHOLD_PCT:
        return "background-color:#fee2e2;color:#b91c1c;font-weight:600"
    if v < 0:
        return "color:#dc2626"
    if v > 0:
        return "color:#16a34a"
    return ""


with tab_prices:
    if len(dips):
        st.warning(f"🔔 {len(dips)} ETF(s) dipping ≥ {DIP_THRESHOLD_PCT:.0f}% below today's open.")
    else:
        st.success("No ETF is dipping past the alert threshold right now.")

    styled = (
        df.style
        .format({"Price ₹": "{:.2f}", "Open ₹": "{:.2f}", "Prev ₹": "{:.2f}",
                 "% vs Open": "{:+.2f}", "% vs Prev": "{:+.2f}", "Alloc %": "{:.0f}"},
                na_rep="n/a")
        .map(color_pct, subset=["% vs Open", "% vs Prev"])
    )
    st.dataframe(styled, use_container_width=True, hide_index=True, height=500)

    missing = set(ETFS) - set(quotes)
    if missing:
        st.caption("❓ No data for: " + ", ".join(missing) + " — fix the `yf` symbol in config.py.")

with tab_chart:
    cc1, cc2 = st.columns(2)
    ticker = cc1.selectbox("ETF", list(quotes.keys()))
    interval = cc2.selectbox("Interval", ["1m", "5m", "15m", "1h", "1d"], index=1)
    period = {"1m": "1d", "5m": "5d", "15m": "5d", "1h": "1mo", "1d": "1y"}[interval]
    ohlc = get_ohlc(ticker, period, interval)
    if ohlc is None or ohlc.empty:
        st.info("No chart data for this selection.")
    else:
        fig = go.Figure(go.Candlestick(
            x=ohlc.index, open=ohlc["Open"], high=ohlc["High"],
            low=ohlc["Low"], close=ohlc["Close"], name=ticker,
        ))
        fig.update_layout(template="plotly_white", height=460,
                          margin=dict(l=0, r=0, t=10, b=0),
                          xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

with tab_alloc:
    alloc_df = df[df["Alloc %"] > 0]
    pie = px.pie(alloc_df, names="Ticker", values="Alloc %", hole=0.5,
                 template="plotly_white")
    pie.update_traces(textposition="inside", textinfo="label+percent")
    pie.update_layout(height=460, margin=dict(l=0, r=0, t=10, b=0))
    st.plotly_chart(pie, use_container_width=True)

with tab_help:
    st.markdown(f"""
#### What each column means
| Column | Meaning |
|---|---|
| **Ticker** | Your INDmoney ETF symbol. |
| **Name** | Fund name. |
| **Alloc %** | Your target weight in the portfolio. |
| **Freq** | How often you SIP it (Daily / Weekly / Watch). |
| **Price ₹** | Latest traded price (most recent 1-minute bar). |
| **Open ₹** | Today's opening price. |
| **Prev ₹** | Yesterday's closing price. |
| **% vs Open** | Price change since *today's open* — the **dip metric** alerts watch. Red shading = dipping ≥ {DIP_THRESHOLD_PCT:.0f}%. |
| **% vs Prev** | Price change since *yesterday's close* — the headline day move. |

#### Where the data comes from (hybrid)
- **Default:** Yahoo Finance via `yfinance` — free, **~15 min delayed**. Used for the price table when Upstox isn't connected, and always for the candlestick chart.
- **Real-time (optional):** connect **Upstox** in the sidebar for live prices in the table. The token expires daily (~03:30 IST), so reconnect each morning; if it lapses, the dashboard auto-falls back to delayed data.
- **Alerts always use yfinance** (the cron must run unattended, with no daily login).
- This dashboard caches data for **{REFRESH_SECONDS}s** and auto-refreshes only during market hours (Mon–Fri 09:15–15:30 IST).

#### When a notification fires
- A separate **GitHub Actions** job runs **every 5 minutes during market hours** (it runs in the cloud — your PC can be off).
- It pushes a 🔔 alert to your phone (ntfy topic `{NTFY_TOPIC}`) when an ETF is **≥ {DIP_THRESHOLD_PCT:.0f}% below today's open**.
- **Anti-spam:** you're alerted once when a dip starts, and again only if it deepens by another full 1%.

#### Expected delay on an alert
- yfinance lag (~15 min) **+** the cron gap (now ~5 min) = an alert can arrive up to roughly **20 minutes** after the actual dip.
- The ~15 min data lag dominates — for true real-time you'd swap yfinance for a live broker API (e.g. Upstox) in `data_feed.py`.
""")

st.caption(f"🔔 Alerts go to ntfy topic `{NTFY_TOPIC}` · handled by GitHub Actions, independent of this page.")
