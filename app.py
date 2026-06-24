"""ETF tracker dashboard (Streamlit Community Cloud — free hosting)."""
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from config import (
    ETFS, REFRESH_SECONDS, MONTHLY_SIP_BUDGET, MONTHLY_DIP_BUDGET,
    DIP_THRESHOLD_PCT, NTFY_TOPIC,
)
from data_feed import fetch_quotes, fetch_ohlc, is_market_open

st.set_page_config(page_title="ETF Tracker", page_icon="📈", layout="wide")


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def get_quotes():
    return fetch_quotes()


@st.cache_data(ttl=REFRESH_SECONDS, show_spinner=False)
def get_ohlc(ticker, period, interval):
    return fetch_ohlc(ticker, period=period, interval=interval)


# Auto-refresh only while the market is open.
if is_market_open():
    st_autorefresh(interval=REFRESH_SECONDS * 1000, key="refresh")

# ---- Header --------------------------------------------------------------
left, right = st.columns([3, 1])
with left:
    st.title("📈 ETF Portfolio Tracker")
    status = "🟢 Market open" if is_market_open() else "🔴 Market closed"
    st.caption(f"{status} · auto-refresh {REFRESH_SECONDS}s · data ~15 min delayed (yfinance)")
with right:
    st.metric("Monthly SIP", f"₹{MONTHLY_SIP_BUDGET:,}")
    st.metric("Dip budget", f"₹{MONTHLY_DIP_BUDGET:,}")

quotes = get_quotes()
if not quotes:
    st.error("No market data returned. Check ticker symbols in config.py or try again.")
    st.stop()

# ---- Price table ---------------------------------------------------------
rows = []
for tk, q in quotes.items():
    rows.append({
        "Ticker": tk,
        "Name": q["name"],
        "Alloc %": q["alloc"],
        "Freq": q["freq"],
        "Price ₹": q["price"],
        "Open ₹": q["open"],
        "% vs Open": q["pct_from_open"],
        "% vs Prev": q["pct_from_prev"],
    })
df = pd.DataFrame(rows).sort_values("% vs Open")

dips = df[df["% vs Open"] <= -DIP_THRESHOLD_PCT]
st.subheader(f"Live prices · {len(dips)} ETF(s) dipping ≥ {DIP_THRESHOLD_PCT}% below open")


def color_pct(v):
    if v <= -DIP_THRESHOLD_PCT:
        return "background-color:#7f1d1d;color:white"
    if v < 0:
        return "color:#f87171"
    if v > 0:
        return "color:#4ade80"
    return ""


styled = (
    df.style
    .format({"Price ₹": "{:.2f}", "Open ₹": "{:.2f}",
             "% vs Open": "{:+.2f}", "% vs Prev": "{:+.2f}", "Alloc %": "{:.0f}"},
            na_rep="n/a")
    .map(color_pct, subset=["% vs Open", "% vs Prev"])
)
st.dataframe(styled, use_container_width=True, hide_index=True)

missing = set(ETFS) - set(quotes)
if missing:
    st.warning("❓ No data for: " + ", ".join(missing) + " — fix the `yf` symbol in config.py.")

# ---- Chart + allocation --------------------------------------------------
c1, c2 = st.columns([2, 1])

with c1:
    st.subheader("Candlestick")
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
        fig.update_layout(height=420, margin=dict(l=0, r=0, t=10, b=0),
                          xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)

with c2:
    st.subheader("Allocation")
    alloc_df = df[df["Alloc %"] > 0]
    pie = px.pie(alloc_df, names="Ticker", values="Alloc %", hole=0.45)
    pie.update_layout(height=420, margin=dict(l=0, r=0, t=10, b=0),
                      showlegend=True)
    st.plotly_chart(pie, use_container_width=True)

st.caption(f"🔔 Dip alerts pushed to ntfy topic: `{NTFY_TOPIC}` "
           f"(handled separately by the GitHub Actions cron — works even when this page is closed).")
