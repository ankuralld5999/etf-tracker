"""Central configuration for the ETF tracker.

Edit ETFS to change your portfolio. `yf` is the Yahoo Finance symbol
(NSE tickers use the .NS suffix). If a symbol shows ❓ in the dashboard
health check, fix it here.
"""
import os

# ---------------------------------------------------------------------------
# Portfolio  (key = INDmoney ticker)
# ---------------------------------------------------------------------------
ETFS = {
    "MIDCAPETF":  {"name": "Mirae Midcap 150 ETF",   "yf": "MIDCAPETF.NS",  "alloc": 16, "freq": "Daily"},
    "NIFTYBEES":  {"name": "Nippon Nifty 50 BeES",   "yf": "NIFTYBEES.NS",  "alloc": 14, "freq": "Daily"},
    "MON100":     {"name": "Motilal NASDAQ 100 ETF", "yf": "MON100.NS",     "alloc": 14, "freq": "Daily"},
    # Yahoo has no UTI Next-50 symbol; NEXT50IETF tracks the same index (proxy for dip %).
    "UTINEXT50":  {"name": "UTI Nifty Next 50 ETF",  "yf": "NEXT50IETF.NS", "alloc": 12, "freq": "Daily"},
    "HDFCSML250": {"name": "HDFC Smallcap 250 ETF",  "yf": "HDFCSML250.NS", "alloc": 12, "freq": "Daily"},
    "BANKBEES":   {"name": "Nippon Bank BeES",       "yf": "BANKBEES.NS",   "alloc":  8, "freq": "Weekly"},
    "GOLDBEES":   {"name": "Nippon Gold BeES",       "yf": "GOLDBEES.NS",   "alloc":  5, "freq": "Weekly"},
    "ICICIB22":   {"name": "ICICI Bharat 22 ETF",    "yf": "ICICIB22.NS",   "alloc":  5, "freq": "Weekly"},
    "ITBEES":     {"name": "Nippon IT BeES",         "yf": "ITBEES.NS",     "alloc":  5, "freq": "Daily"},
    "AUTOBEES":   {"name": "Nippon Auto ETF",        "yf": "AUTOBEES.NS",   "alloc":  4, "freq": "Weekly"},
    "PHARMABEES": {"name": "Nippon Pharma ETF",      "yf": "PHARMABEES.NS", "alloc":  3, "freq": "Daily"},
    "FMCGIETF":   {"name": "ICICI FMCG ETF",         "yf": "FMCGIETF.NS",   "alloc":  2, "freq": "Weekly"},
    "PSUBNKBEES": {"name": "Nippon PSU Bank BeES",   "yf": "PSUBNKBEES.NS", "alloc":  0, "freq": "Watch"},
}

# ---------------------------------------------------------------------------
# Notifications  (ntfy.sh — free, no account)
# Override with the NTFY_TOPIC env var / GitHub secret in production.
# ---------------------------------------------------------------------------
# `or` (not getenv default) so an empty env var / unset GitHub secret still falls back.
NTFY_TOPIC = os.getenv("NTFY_TOPIC") or "etf-tracker-ankur"
NTFY_SERVER = os.getenv("NTFY_SERVER") or "https://ntfy.sh"

# ---------------------------------------------------------------------------
# Alert thresholds
# ---------------------------------------------------------------------------
DIP_THRESHOLD_PCT = 0.5   # start alerting once an ETF is this % below today's open
DIP_STEP_PCT      = 0.5   # re-alert only after it drops another full step (anti-spam)

# ---------------------------------------------------------------------------
# Budgets (₹)  — informational, shown on the dashboard
# ---------------------------------------------------------------------------
MONTHLY_SIP_BUDGET = 35000
MONTHLY_DIP_BUDGET = 6726

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
REFRESH_SECONDS = 60

# Market hours (IST) — Mon–Fri 09:15–15:30
MARKET_OPEN  = (9, 15)
MARKET_CLOSE = (15, 30)
