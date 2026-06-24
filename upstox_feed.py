"""Upstox real-time data adapter (dashboard only).

Mirrors data_feed.fetch_quotes() so the dashboard can swap sources.
Upstox access tokens expire daily (~03:30 IST), so this is used only for
the interactive dashboard; the unattended alert cron stays on yfinance.

OAuth flow (daily):
  1. open get_auth_url(...) -> user logs in to Upstox
  2. Upstox redirects to your redirect_uri with ?code=XXXX
  3. exchange_code(...) -> access_token  (held in the Streamlit session)
"""
from __future__ import annotations

import csv
import gzip
import io

import requests

from config import ETFS

API = "https://api.upstox.com/v2"
INSTRUMENTS_URL = "https://assets.upstox.com/market-quote/instruments/exchange/complete.csv.gz"


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------
def get_auth_url(api_key: str, redirect_uri: str) -> str:
    return (f"{API}/login/authorization/dialog?response_type=code"
            f"&client_id={api_key}&redirect_uri={redirect_uri}")


def exchange_code(api_key: str, api_secret: str, redirect_uri: str, code: str) -> str:
    """Exchange the one-time ?code for a daily access token."""
    r = requests.post(
        f"{API}/login/authorization/token",
        headers={"accept": "application/json",
                 "Content-Type": "application/x-www-form-urlencoded"},
        data={
            "code": code,
            "client_id": api_key,
            "client_secret": api_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["access_token"]


# ---------------------------------------------------------------------------
# Instrument-key lookup (NSE equity/ETF segment)
# ---------------------------------------------------------------------------
def load_instrument_keys(symbols: list[str]) -> dict[str, str]:
    """Map NSE trading symbol -> Upstox instrument_key for the given symbols."""
    wanted = {s.upper() for s in symbols}
    out: dict[str, str] = {}
    raw = requests.get(INSTRUMENTS_URL, timeout=60).content
    text = gzip.decompress(raw).decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        key = row.get("instrument_key", "")
        sym = (row.get("tradingsymbol") or "").upper()
        if key.startswith("NSE_EQ|") and sym in wanted:
            out[sym] = key
    return out


# ---------------------------------------------------------------------------
# Quotes
# ---------------------------------------------------------------------------
def _upstox_symbol(ticker: str) -> str:
    """NSE trading symbol used for Upstox lookup (override via ETFS[tk]['nse'])."""
    return ETFS[ticker].get("nse", ticker).upper()


def fetch_quotes(access_token: str, tickers: list[str] | None = None) -> dict[str, dict]:
    """Live snapshot per portfolio ticker, same shape as data_feed.fetch_quotes."""
    tickers = tickers or list(ETFS.keys())
    sym_for = {tk: _upstox_symbol(tk) for tk in tickers}
    keymap = load_instrument_keys(list(sym_for.values()))   # symbol -> instrument_key
    inst_keys = [keymap[s] for s in sym_for.values() if s in keymap]
    if not inst_keys:
        return {}

    r = requests.get(
        f"{API}/market-quote/quotes",
        headers={"accept": "application/json", "Authorization": f"Bearer {access_token}"},
        params={"instrument_key": ",".join(inst_keys)},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json().get("data", {})

    # Response is keyed by "NSE_EQ:SYMBOL"; index by trading symbol for lookup.
    by_symbol = {}
    for v in data.values():
        ts = (v.get("symbol") or "").upper()
        if ts:
            by_symbol[ts] = v

    out: dict[str, dict] = {}
    for tk in tickers:
        v = by_symbol.get(sym_for[tk])
        if not v:
            continue
        ohlc = v.get("ohlc", {}) or {}
        price = float(v.get("last_price") or 0) or None
        open_ = float(ohlc.get("open") or 0) or None
        prev_close = float(ohlc.get("close") or 0) or None   # Upstox quote 'close' = prev close
        if price is None:
            continue
        meta = ETFS[tk]
        out[tk] = {
            "price": round(price, 2),
            "open": round(open_, 2) if open_ else None,
            "prev_close": round(prev_close, 2) if prev_close else None,
            "pct_from_open": round((price - open_) / open_ * 100, 2) if open_ else None,
            "pct_from_prev": round((price - prev_close) / prev_close * 100, 2) if prev_close else None,
            "name": meta["name"], "alloc": meta["alloc"], "freq": meta["freq"],
        }
    return out
