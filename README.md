# 📈 ETF Tracker — free, cloud-hosted, with dip alerts

A zero-cost ETF dashboard **and** an unattended dip-alert bot. Nothing runs on
your PC: the dashboard is hosted on **Streamlit Community Cloud** and the alerts
run on a **GitHub Actions** schedule. Notifications are pushed via **ntfy.sh**.

```
Streamlit Cloud  ──>  app.py            (you open this to look at prices)
GitHub Actions   ──>  check_alerts.py   (runs every 30 min, market hours, no PC needed)
        │
        └── ntfy.sh ──> 🔔 phone / browser push when an ETF dips
```

| Piece            | Service                  | Cost | Needs your PC? |
|------------------|--------------------------|------|----------------|
| Dashboard UI     | Streamlit Community Cloud| Free | No             |
| Dip alert bot    | GitHub Actions (cron)    | Free*| No             |
| Push notifications | ntfy.sh                | Free | No             |
| Market data      | yfinance (Yahoo)         | Free | No             |

\* GitHub Actions is free unlimited on **public** repos.

---

## Files
| File | Purpose |
|------|---------|
| `config.py` | Portfolio, thresholds, ntfy topic, budgets — **edit this** |
| `data_feed.py` | Fetches quotes / candlesticks from yfinance |
| `alerts.py` | Dip detection + ntfy push |
| `check_alerts.py` | Cron entry point (used by GitHub Actions) |
| `app.py` | Streamlit dashboard |
| `.github/workflows/dip-alerts.yml` | The scheduled alert job |

---

## Setup (≈ 10 minutes, one time)

### 1. Pick a notification topic & install the app
- Install the **ntfy** app ([Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy) / [iOS](https://apps.apple.com/us/app/ntfy/id1625396347)) or just open https://ntfy.sh in a browser.
- **Subscribe** to a topic name — anything unique and hard to guess, e.g. `etf-tracker-ankur-7h3k`.
- Put that same name in `config.py` → `NTFY_TOPIC` (or set it as a GitHub secret, step 3).

> ⚠️ ntfy topics are public to anyone who knows the name — use a random suffix.

### 2. Push this folder to a **public** GitHub repo
```bash
cd etf-tracker
git init
git add .
git commit -m "ETF tracker"
gh repo create etf-tracker --public --source=. --push
```

### 3. (Optional) Store the topic as a secret
Repo → **Settings → Secrets and variables → Actions → New repository secret**
- Name: `NTFY_TOPIC`  Value: your topic name

If you skip this, it falls back to the value in `config.py`.

### 4. Turn on the alert bot
- Repo → **Actions** tab → enable workflows.
- Open **ETF dip alerts** → **Run workflow** → tick *force* → run, to test immediately.
- You should get a 🔔 if anything is currently dipping. After that it runs itself
  every 30 min during NSE market hours.

### 5. Deploy the dashboard (free)
- Go to https://share.streamlit.io → **Create app** → pick your repo.
- Main file path: `app.py`
- Deploy. You get a permanent URL like `https://etf-tracker.streamlit.app`.

Done. The dashboard is live on a URL; the alerts fire whether or not anyone has
the dashboard open.

---

## Run locally (optional, for testing)
```bash
pip install -r requirements.txt
python alerts.py            # send a test notification
python data_feed.py         # print live quotes + flag bad symbols
python check_alerts.py --force   # run the dip check once now
streamlit run app.py        # open the dashboard
```

---

## Tuning
All in `config.py`:
- `DIP_THRESHOLD_PCT` — how far below today's open before alerting (default 1%).
- `DIP_STEP_PCT` — re-alert only after another full step down (anti-spam).
- `ETFS` — add/remove holdings; fix any `yf` symbol the dashboard flags with ❓.
- Cron frequency / window: edit `.github/workflows/dip-alerts.yml`.

## Notes
- yfinance data is delayed ~15 min — fine for SIP/dip decisions, not for trading.
- To swap in a real-time feed later (e.g. Upstox API), replace the body of
  `data_feed.fetch_quotes()`; nothing else changes.
