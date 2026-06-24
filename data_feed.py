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
    daily = t.history(period="5d", interval="1d").dropna(subset=["Close"])
    if daily.empty:
        return None

    today = daily.iloc[-1]
    prev_close = float(daily.iloc[-2]["Close"]) if len(daily) >= 2 else float(today["Close"])

    # Prefer the intraday session: first bar = true open, last bar = current price.
    open_ = float(today["Open"]) if _ok(today["Open"]) else None
    price = float(today["Close"]) if _ok(today["Close"]) else prev_close
    try:
        intr = t.history(period="1d", interval="1m").dropna(subset=["Close"])
        if not intr.empty:
            price = float(intr["Close"].iloc[-1])
            if _ok(intr["Open"].iloc[0]):
                open_ = float(intr["Open"].iloc[0])
    except Exception:
        pass

    pct_from_open = round((price - open_) / open_ * 100, 2) if _ok(open_) and open_ else None
    pct_from_prev = round((price - prev_close) / prev_close * 100, 2) if prev_close else None
    return {
        "price": round(price, 2),
        "open": round(open_, 2) if _ok(open_) else None,
        "prev_close": round(prev_close, 2),
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
    """Cumulative % return per ticker over 3M/6M/1Y/5Y (dividend/split-adjusted).

    None for any window the ETF isn't old enough to cover.
    """
    tickers = tickers or list(ETFS.keys())
    start = (datetime.now(IST) - timedelta(days=1900)).strftime("%Y-%m-%d")  # ~5.2y
    out: dict[str, dict] = {}
    for tk in tickers:
        labels = list(RETURN_PERIODS)
        r = {lbl: None for lbl in labels}
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
