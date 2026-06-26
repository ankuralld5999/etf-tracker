"""Dip detection + ntfy.sh push notifications."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone, timedelta

import requests

from config import (
    NTFY_TOPIC, NTFY_SERVER, DIP_THRESHOLD_PCT, DIP_STEP_PCT,
)

IST = timezone(timedelta(hours=5, minutes=30))

# ntfy priority words -> the integer the JSON API expects.
_PRIORITY = {"min": 1, "low": 2, "default": 3, "high": 4, "urgent": 5}


def send_ntfy(title: str, message: str, priority: str = "default",
              tags: str = "chart_with_downwards_trend") -> bool:
    """Push a notification via ntfy's JSON API (handles UTF-8 / emoji).

    HTTP headers are latin-1 only, so we POST JSON to the server root with
    the topic in the body instead of using Title/Tags headers.
    """
    payload = {
        "topic": NTFY_TOPIC,
        "title": title,
        "message": message,
        "priority": _PRIORITY.get(priority, 3),
        "tags": [t.strip() for t in tags.split(",") if t.strip()],
    }
    try:
        r = requests.post(
            NTFY_SERVER.rstrip("/"),
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        return r.ok
    except Exception as e:  # network hiccup shouldn't crash the cron job
        print(f"ntfy send failed: {e}")
        return False


def check_dips(quotes: dict[str, dict], state: dict | None = None,
               threshold: float = DIP_THRESHOLD_PCT,
               step: float = DIP_STEP_PCT) -> tuple[list[dict], dict]:
    """Find ETFs dipping >= threshold below yesterday's close (the 1D % move).

    `state` carries per-day dedup info so we only re-alert when a dip
    deepens by another `step`. Returns (alerts, new_state).
    """
    today = datetime.now(IST).date().isoformat()
    if not state or state.get("date") != today:
        state = {"date": today, "levels": {}}

    alerts: list[dict] = []
    for tk, q in quotes.items():
        pct = q.get("pct_from_prev")       # 1D %: change vs yesterday's close
        if pct is None or (isinstance(pct, float) and math.isnan(pct)):
            continue                       # no usable previous close yet
        dip = -pct                         # positive number = below prev close
        if dip < threshold:
            continue
        bucket = math.floor(dip / step) * step   # 1.0, 1.5, 2.0, 2.5 ...
        if bucket > state["levels"].get(tk, 0):
            state["levels"][tk] = bucket
            alerts.append({"ticker": tk, "dip": round(dip, 2), **q})
    return alerts, state


def notify_dips(alerts: list[dict]) -> bool:
    """Send a single combined notification for all current dips."""
    if not alerts:
        return False
    alerts.sort(key=lambda a: a["dip"], reverse=True)
    worst = alerts[0]["dip"]

    lines = [
        f"{a['ticker']}  -{a['dip']:.2f}%  ₹{a['price']}  (prev ₹{a['prev_close']})"
        for a in alerts
    ]
    title = f"📉 {len(alerts)} ETF dip{'s' if len(alerts) > 1 else ''} — worst -{worst:.2f}%"
    message = "\n".join(lines) + "\n\nGood time to deploy dip budget."
    priority = "urgent" if worst >= 3 else "high" if worst >= 2 else "default"
    return send_ntfy(title, message, priority=priority)


if __name__ == "__main__":
    send_ntfy("✅ ETF tracker test",
              "If you can read this, ntfy notifications work.",
              priority="default", tags="white_check_mark")
    print(f"Test sent to {NTFY_SERVER}/{NTFY_TOPIC}")
