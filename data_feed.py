"""Market data via yfinance (free, ~15 min delayed NSE quotes)."""
from __future__ import annotations

import math
from datetime import datetime, time, timezone, timedelta

import pandas as pd
import yfinance as yf

from config import ETFS, MARKET_OPEN, MARKET_CLOSE

IST = timezone(timedelta(hours=5, minutes=30))


def is_market_open(now: datetime | None = None) -> bool:
    """True during NSE cash-market hours (Mon–Fri 09:15–15:30 IST)."""
    now = (now or datetime.now(IST)).astimezone(IST)
    if now.weekday() >= 5:  # Sat/Sun
        return False
    open_t = time(*MARKET_OPEN)
    close_t = time(*MARKET_CLOSE)
    return open_t <= now.time() <= close_t


def _ok(x) -> bool:
    """True if x is a usable, non-NaN number."""
    try:
        return x is not None and not math.isnan(float(x))
    except (TypeError, ValueError):
        return False


def _fetch_one(yf_symbol: str) -> dict | None:
    """Return price snapshot for one symbol, or None if no data.

    Robust to NaN cells in yfinance daily bars: today's open and the latest
    price are taken from the intraday session when available, with daily-bar
    fallbacks. pct_from_open is None when no valid open exists yet.
    """
    t = yf.Ticker(yf_symbol)
    daily = t.history(period="7d", interval="1d").dropna(subset=["Close"])
    if daily.empty:
        return None

    # Intraday gives TODAY's true open + current price — the daily bar for the
    # current session is often unsettled (NaN), so we must not rely on it.
    intr = pd.DataFrame()
    try:
        intr = t.history(period="1d", interval="1m").dropna(subset=["Close"])
    except Exception:
        pass

    if not intr.empty:
        today_date = intr.index[-1].date()
        price = float(intr["Close"].iloc[-1])
        open_ = float(intr["Open"].iloc[0]) if _ok(intr["Open"].iloc[0]) else None
        # Previous close = last SETTLED daily close strictly before today.
        prior = daily[daily.index.date < today_date]
        prev_close = float(prior["Close"].iloc[-1]) if not prior.empty else None
        if open_ is None:  # fall back to today's daily open if intraday lacked it
            same = daily[daily.index.date == today_date]
            if not same.empty and _ok(same["Open"].iloc[-1]):
                open_ = float(same["Open"].iloc[-1])
    else:
        # Market closed and yfinance has settled the latest daily bar.
        last = daily.iloc[-1]
        price = float(last["Close"])
        open_ = float(last["Open"]) if _ok(last["Open"]) else None
        prev_close = float(daily.iloc[-2]["Close"]) if len(daily) >= 2 else None

    pct_from_open = round((price - open_) / open_ * 100, 2) if open_ else None
    pct_from_prev = round((price - prev_close) / prev_close * 100, 2) if prev_close else None
    return {
        "price": round(price, 2),
        "open": round(open_, 2) if open_ else None,
        "prev_close": round(prev_close, 2) if prev_close else None,
        "pct_from_open": pct_from_open,
        "pct_from_prev": pct_from_prev,
    }


def fetch_quotes(tickers: list[str] | None = None) -> dict[str, dict]:
    """Snapshot for each portfolio ticker. Failed symbols are omitted."""
    tickers = tickers or list(ETFS.keys())
    out: dict[str, dict] = {}
    for tk in tickers:
        meta = ETFS[tk]
        try:
            snap = _fetch_one(meta["yf"])
        except Exception:
            snap = None
        if snap:
            snap.update(name=meta["name"], alloc=meta["alloc"], freq=meta["freq"])
            out[tk] = snap
    return out


def fetch_ohlc(ticker: str, period: str = "1d", interval: str = "5m"):
    """Candlestick history for one ticker (used by the dashboard chart)."""
    return yf.Ticker(ETFS[ticker]["yf"]).history(period=period, interval=interval)


# Cumulative price-return windows, in calendar days.
RETURN_PERIODS = {"3M %": 91, "6M %": 182, "1Y %": 365, "5Y %": 1826}


def fetch_returns(tickers: list[str] | None = None) -> dict[str, dict]:
    """Per-ticker trend metrics from daily history (dividend/split-adjusted).

    Includes cumulative 3M/6M/1Y/5Y returns plus two "how cheap vs its own
    trend" signals used as buy-the-dip context:
      - "vs 50-DMA %": price vs its 50-day moving average (negative = below trend)
      - "20D DD %":    drawdown from the highest close in the last 20 sessions
    Any value is None when the ETF isn't old enough / lacks data.
    """
    tickers = tickers or list(ETFS.keys())
    start = (datetime.now(IST) - timedelta(days=1900)).strftime("%Y-%m-%d")  # ~5.2y
    out: dict[str, dict] = {}
    for tk in tickers:
        r = {lbl: None for lbl in RETURN_PERIODS}
        r["vs 50-DMA %"] = None
        r["20D DD %"] = None
        try:
            close = yf.Ticker(ETFS[tk]["yf"]).history(start=start, interval="1d")["Close"].dropna()
        except Exception:
            close = pd.Series(dtype=float)
        if not close.empty:
            last = float(close.iloc[-1])
            for lbl, days in RETURN_PERIODS.items():
                past = close[close.index <= close.index[-1] - pd.Timedelta(days=days)]
                if not past.empty and float(past.iloc[-1]):
                    base = float(past.iloc[-1])
                    r[lbl] = round((last - base) / base * 100, 2)
            # Distance below the 50-day moving average (needs >= 50 sessions).
            sma50 = close.rolling(50).mean().iloc[-1]
            if _ok(sma50) and float(sma50):
                r["vs 50-DMA %"] = round((last - float(sma50)) / float(sma50) * 100, 2)
            # Drawdown from the 20-session high (<= 0; 0 = at a fresh high).
            high20 = float(close.tail(20).max())
            if high20:
                r["20D DD %"] = round((last - high20) / high20 * 100, 2)
        out[tk] = r
    return out


if __name__ == "__main__":
    print(f"Market open: {is_market_open()}")
    q = fetch_quotes()
    for tk, s in q.items():
        o = f"{s['pct_from_open']:+.2f}%" if s["pct_from_open"] is not None else "  n/a"
        p = f"{s['pct_from_prev']:+.2f}%" if s["pct_from_prev"] is not None else "  n/a"
        print(f"{tk:12} ₹{s['price']:>9}  open {o}  prev {p}")
    missing = set(ETFS) - set(q)
    if missing:
        print("❓ No data (fix yf symbol in config.py):", ", ".join(missing))
