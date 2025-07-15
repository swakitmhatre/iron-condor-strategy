# Iron Condor Strategy for Dhan

# Iron Condor Strategy – Dhan API (Paper Trading)

This strategy automates Iron Condor options trading using Dhan’s API with support for paper trading, MTM tracking, exit filters, market condition checks, and Telegram alerts.

---

## ✅ Features

- **Broker:** Dhan (uses API token only, no login needed)
- **Trade Mode:** Paper Trading by default (safe testing)
- **Strategy:** Iron Condor (Sell ATM ±9 legs, Buy ATM ±11 legs)
- **Entry Sequence:** Buy legs first → then Sell legs (for margin benefit)
- **Exit Sequence:** Sell legs first → then Buy legs
- **Timing Window:** Active between 10:00 AM – 1:50 PM
- **Exit Triggers:**
  - MTM Target (0.20% of margin)
  - NIFTY 1% intraday move
  - Manual flag file: `stop.flag`
- **Market Conditions Check:**
  - Avoid high IV, gap-up/down, large overnight move
  - Skip trade if filters fail (can be overridden via `force_entry.flag`)
- **Logging:**
  - Entry/Exit details
  - MTM timestamps
  - Errors & reasons for skipping
- **Telegram Bot:**
  - Sends live alerts: Entry, Exit, Errors, PnL

---

## 🔧 Files

| File | Purpose |
|------|---------|
| `main.py` | Main strategy logic |
| `config.py` | Configurations: token, chat ID, MTM % |
| `utils.py` | Broker functions, helper methods |
| `telegram_bot.py` | Telegram message sender |
| `deploy.sh` | Startup script for AWS |
| `requirements.txt` | Python dependencies |
| `strategy.log` | Strategy logs |
| `stop.flag` | Manual exit trigger (create this file to stop strategy) |

---

## 🚀 Setup

1. **Install Requirements**
   ```bash
   pip install -r requirements.txt


This is the deployment-ready strategy with all features.
