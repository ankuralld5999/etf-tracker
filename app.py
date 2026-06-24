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
from datetime import datetime, timezone, timedelta, time as dtime
from pathlib import Path

from data_feed import fetch_quotes, fetch_ohlc, fetch_returns, is_market_open
import upstox_feed

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    return datetime.now(IST)


def token_expiry(issued: datetime) -> datetime:
    """Upstox access tokens expire at 03:30 IST the following day."""
    exp = issued.astimezone(IST).replace(hour=3, minute=30, second=0, microsecond=0)
    if issued.astimezone(IST).time() >= dtime(3, 30):
        exp += timedelta(days=1)
    return exp

_FAVICON = Path(__file__).parent / "assets" / "favicon.svg"
st.set_page_config(
    page_title="ETF Tracker",
    page_icon=str(_FAVICON) if _FAVICON.exists() else "📈",
    layout="wide",
)

# ---- Design system (Fraunces / Inter Tight / JetBrains Mono) ----------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&family=Inter+Tight:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root{
  --ink:#1A1A2E; --paper:#FBFAF7; --card:#FFFFFF; --line:#ECE7DC;
  --indigo:#2D2A6E; --gold:#C8A04A; --gain:#138A5E; --loss:#C0392B;
}
html, body, [class*="css"], .stApp { background: var(--paper); }
.block-container{ max-width:1180px; padding-top:2.2rem; padding-bottom:3rem; }

/* Base type */
.stApp, .stMarkdown, p, span, label, div[data-testid="stMarkdownContainer"]{
  font-family:'Inter Tight', system-ui, sans-serif; color:var(--ink);
}
/* Display headings */
h1, h2, h3{ font-family:'Fraunces', Georgia, serif !important; color:var(--ink);
  letter-spacing:-0.01em; font-weight:600; }
h1{ font-size:clamp(1.9rem, 4.2vw, 3rem); line-height:1.05; }
h2{ font-size:clamp(1.3rem, 3vw, 1.8rem); }
h3{ font-size:clamp(1.05rem, 2.2vw, 1.3rem); }

/* Eyebrow caption under the title */
.stCaption, .stCaption p, [data-testid="stCaptionContainer"]{
  font-family:'JetBrains Mono', monospace !important; font-size:.8rem !important;
  letter-spacing:.04em; color:#6B6780 !important; text-transform:none; }

/* Metric cards with a gold top rule */
[data-testid="stMetric"]{
  background:var(--card); border:1px solid var(--line); border-radius:14px;
  padding:1rem 1.1rem; box-shadow:0 1px 0 rgba(26,26,46,.02);
  position:relative; overflow:hidden; }
[data-testid="stMetric"]::before{
  content:""; position:absolute; top:0; left:0; right:0; height:3px;
  background:linear-gradient(90deg, var(--gold), #E7C887); }
[data-testid="stMetricValue"]{
  font-family:'JetBrains Mono', monospace !important;
  font-variant-numeric:tabular-nums; font-weight:600;
  font-size:clamp(1.3rem, 3.2vw, 1.7rem) !important; }
[data-testid="stMetricLabel"]{ font-family:'Inter Tight',sans-serif !important;
  color:#6B6780 !important; font-weight:500; letter-spacing:.01em; }

/* Tabs */
[data-baseweb="tab-list"]{ gap:.25rem; border-bottom:1px solid var(--line); }
[data-baseweb="tab"]{ font-family:'Inter Tight',sans-serif; font-weight:500;
  font-size:.98rem; padding:.4rem .9rem; }
[data-baseweb="tab"][aria-selected="true"]{ color:var(--indigo); }
[data-baseweb="tab-highlight"]{ background:var(--gold) !important; }

/* Tabular figures everywhere data shows */
[data-testid="stDataFrame"] *{
  font-family:'JetBrains Mono', monospace !important;
  font-variant-numeric:tabular-nums; font-size:.86rem; }
[data-testid="stDataFrame"]{ border:1px solid var(--line); border-radius:12px; }

/* Buttons / links */
.stButton button, .stLinkButton a{ border-radius:10px; font-weight:600;
  font-family:'Inter Tight',sans-serif; }

hr{ border-color:var(--line); }

@media (max-width:640px){
  .block-container{ padding-top:1.4rem; padding-left:.8rem; padding-right:.8rem; }
}
</style>
""", unsafe_allow_html=True)


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


@st.cache_data(ttl=3600, show_spinner="Loading historical returns…")
def get_returns():
    return fetch_returns()   # slow-moving; yfinance; refreshed hourly


# ---- Upstox OAuth: capture ?code= from the redirect and swap for a token ----
api_key, api_secret, redirect_uri = _upstox_secrets()
if api_key and "code" in st.query_params and not st.session_state.get("upstox_token"):
    try:
        st.session_state["upstox_token"] = upstox_feed.exchange_code(
            api_key, api_secret, redirect_uri, st.query_params["code"])
        st.session_state["upstox_connected_at"] = now_ist()
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
        conn = st.session_state.get("upstox_connected_at")
        if conn:
            exp = token_expiry(conn)
            mins = max(0, int((exp - now_ist()).total_seconds() // 60))
            st.caption(f"Connected {conn:%d %b %H:%M} IST")
            st.caption(f"Token valid until {exp:%d %b %H:%M} IST · ~{mins // 60}h {mins % 60}m left")
        if st.button("Disconnect"):
            st.session_state.pop("upstox_token", None)
            st.session_state.pop("upstox_connected_at", None)
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

# ---- Palette (shared with Plotly) ----------------------------------------
INK, PAPER, LINE = "#1A1A2E", "#FBFAF7", "#ECE7DC"
INDIGO, GOLD, GAIN, LOSS = "#2D2A6E", "#C8A04A", "#138A5E", "#C0392B"
MONO = "JetBrains Mono, monospace"


def style_fig(fig, height=460):
    fig.update_layout(
        template="plotly_white", height=height,
        margin=dict(l=8, r=8, t=12, b=8),
        font=dict(family=MONO, size=12, color=INK),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        xaxis=dict(showgrid=False, rangeslider_visible=False),
        yaxis=dict(gridcolor=LINE, zeroline=False),
        legend=dict(orientation="h", y=1.04, x=0, bgcolor="rgba(0,0,0,0)"),
    )
    return fig


# ---- Header --------------------------------------------------------------
st.markdown("<div style='font-family:JetBrains Mono,monospace;font-size:.72rem;"
            "letter-spacing:.22em;color:#C8A04A;text-transform:uppercase;'>"
            "Long-term portfolio · INDmoney</div>", unsafe_allow_html=True)
st.title("ETF Portfolio Tracker")
open_now = is_market_open()
status = "🟢 Market open" if open_now else "🔴 Market closed"
refresh_note = f"auto-refresh {REFRESH_SECONDS}s" if open_now else "auto-refresh paused"

quotes, source = get_quotes()
if not quotes:
    st.error("No market data returned. Try again in a moment, or check ticker symbols in config.py.")
    st.stop()
st.caption(f"{status} · {refresh_note} · source: {source} · updated {now_ist():%d %b %H:%M:%S} IST")

# ---- Build the table -----------------------------------------------------
ret = get_returns()
rows = [{
    "Ticker": tk, "Name": q["name"], "Alloc %": q["alloc"], "Freq": q["freq"],
    "Price ₹": q["price"], "Open ₹": q["open"], "Prev ₹": q["prev_close"],
    "% vs Open": q["pct_from_open"], "1D %": q["pct_from_prev"],
    "3M %": ret.get(tk, {}).get("3M %"), "6M %": ret.get(tk, {}).get("6M %"),
    "1Y %": ret.get(tk, {}).get("1Y %"), "5Y %": ret.get(tk, {}).get("5Y %"),
} for tk, q in quotes.items()]
df = pd.DataFrame(rows).sort_values("% vs Open", na_position="last")

PCT_COLS = ["% vs Open", "1D %", "3M %", "6M %", "1Y %", "5Y %"]
dips = df[df["% vs Open"] <= -DIP_THRESHOLD_PCT]

# Allocation-weighted day move (vs previous close), skipping missing data.
wdf = df.dropna(subset=["1D %"])
day_move = (wdf["Alloc %"] * wdf["1D %"]).sum() / wdf["Alloc %"].sum() if not wdf.empty else 0.0

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
    """Palette-matched red/green for % columns."""
    if pd.isna(v):
        return "color:#9A96A8"
    if v <= -DIP_THRESHOLD_PCT:
        return f"background-color:#FBE3DF;color:{LOSS};font-weight:600"
    if v < 0:
        return f"color:{LOSS}"
    if v > 0:
        return f"color:{GAIN}"
    return ""


with tab_prices:
    if len(dips):
        st.warning(f"🔔 {len(dips)} ETF(s) dipping ≥ {DIP_THRESHOLD_PCT:.0f}% below today's open.")
    else:
        st.success("No ETF is dipping past the alert threshold right now.")

    fmt = {"Price ₹": "{:.2f}", "Open ₹": "{:.2f}", "Prev ₹": "{:.2f}", "Alloc %": "{:.0f}"}
    fmt.update({c: "{:+.2f}" for c in PCT_COLS})
    styled = (
        df.style
        .format(fmt, na_rep="n/a")
        .map(color_pct, subset=PCT_COLS)
    )
    st.dataframe(styled, use_container_width=True, hide_index=True, height=500)

    missing = set(ETFS) - set(quotes)
    if missing:
        st.caption("❓ No data for: " + ", ".join(missing) + " — fix the `yf` symbol in config.py.")

with tab_chart:
    cc1, cc2, cc3 = st.columns([1.2, 1, 1])
    ticker = cc1.selectbox("ETF", list(quotes.keys()))
    chart_type = cc2.selectbox("Chart type", ["Line", "Area", "Candlestick", "OHLC bars"])
    interval = cc3.selectbox("Interval", ["1m", "5m", "15m", "1h", "1d"], index=1)
    show_ma = st.checkbox("Overlay 20-period moving average", value=False)

    period = {"1m": "1d", "5m": "5d", "15m": "5d", "1h": "1mo", "1d": "1y"}[interval]
    ohlc = get_ohlc(ticker, period, interval)

    if ohlc is None or ohlc.empty:
        st.info("No chart data for this selection yet — try a different interval.")
    else:
        x, c = ohlc.index, ohlc["Close"]
        fig = go.Figure()
        if chart_type == "Candlestick":
            fig.add_trace(go.Candlestick(
                x=x, open=ohlc["Open"], high=ohlc["High"], low=ohlc["Low"], close=c,
                name=ticker, increasing_line_color=GAIN, decreasing_line_color=LOSS))
        elif chart_type == "OHLC bars":
            fig.add_trace(go.Ohlc(
                x=x, open=ohlc["Open"], high=ohlc["High"], low=ohlc["Low"], close=c,
                name=ticker, increasing_line_color=GAIN, decreasing_line_color=LOSS))
        elif chart_type == "Area":
            fig.add_trace(go.Scatter(
                x=x, y=c, name=ticker, mode="lines", line=dict(color=INDIGO, width=2),
                fill="tozeroy", fillcolor="rgba(45,42,110,0.10)"))
            fig.update_yaxes(range=[c.min() * 0.995, c.max() * 1.005])
        else:  # Line
            fig.add_trace(go.Scatter(
                x=x, y=c, name=ticker, mode="lines", line=dict(color=INDIGO, width=2)))

        if show_ma and len(c) >= 20:
            fig.add_trace(go.Scatter(
                x=x, y=c.rolling(20).mean(), name="MA-20", mode="lines",
                line=dict(color=GOLD, width=1.6, dash="dash")))

        st.plotly_chart(style_fig(fig), use_container_width=True)
        st.caption("Charts use Yahoo Finance data (delayed). Live Upstox prices apply to the Prices table.")

with tab_alloc:
    alloc_df = df[df["Alloc %"] > 0].sort_values("Alloc %", ascending=False)
    palette = ["#2D2A6E", "#3E3A8C", "#5A56A8", "#C8A04A", "#D9B968", "#138A5E",
               "#1FA876", "#7C7AB0", "#9A96A8", "#C0392B", "#E07A5F", "#A88A3E"]
    pie = go.Figure(go.Pie(
        labels=alloc_df["Ticker"], values=alloc_df["Alloc %"], hole=0.58,
        marker=dict(colors=palette, line=dict(color=PAPER, width=2)),
        textinfo="label+percent", textfont=dict(family=MONO, size=12),
        sort=False))
    pie.add_annotation(text="Target<br>weights", showarrow=False,
                       font=dict(family="Fraunces, serif", size=16, color=INK))
    st.plotly_chart(style_fig(pie), use_container_width=True)

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
| **1D %** | Today's return (vs yesterday's close). |
| **3M / 6M / 1Y / 5Y %** | **Cumulative** return over that window (not annualised), dividend- & split-adjusted. `n/a` if the ETF isn't that old. |

*Returns are computed from Yahoo Finance daily history and cached for 1 hour (they move slowly).*

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
