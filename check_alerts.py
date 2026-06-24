"""Entry point for the GitHub Actions cron job.

Runs unattended in the cloud: fetch quotes -> detect new dips -> push
notifications. State is persisted to alert_state.json (committed back by
the workflow) so the same dip isn't announced repeatedly.
"""
import json
import os
import sys
from pathlib import Path

from data_feed import fetch_quotes, is_market_open
from alerts import check_dips, notify_dips

STATE_FILE = Path(__file__).parent / "alert_state.json"


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def main() -> int:
    force = "--force" in sys.argv or os.getenv("FORCE_RUN") == "1"
    if not is_market_open() and not force:
        print("Market closed — skipping. (use --force to override)")
        return 0

    quotes = fetch_quotes()
    if not quotes:
        print("No quotes returned — check yf symbols / network.")
        return 1

    state = load_state()
    alerts, state = check_dips(quotes, state)
    save_state(state)

    if alerts:
        ok = notify_dips(alerts)
        print(f"Sent {len(alerts)} dip alert(s): {[a['ticker'] for a in alerts]} (ntfy ok={ok})")
    else:
        print(f"No new dips across {len(quotes)} ETFs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
