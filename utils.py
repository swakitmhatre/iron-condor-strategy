import json
import os
from datetime import datetime, timedelta, time
import pytz

# === Config ===
NIFTY_SYMBOL = "NIFTY"
FORCE_ENTRY_FILE = "force_entry.flag"
STOP_FLAG_FILE = "stop.flag"

# === Timezone handling ===
def get_ist_time():
    return datetime.now(pytz.timezone('Asia/Kolkata'))

# === Market Time Logic ===
def is_market_open():
    now = get_ist_time()
    market_open = time(9, 15)
    market_close = time(15, 30)
    is_weekday = now.weekday() < 5  # Monday to Friday

    log(f"Market check time: {now.strftime('%Y-%m-%d %H:%M:%S')} | Weekday: {now.weekday()}")

    return is_weekday and market_open <= now.time() <= market_close

# === Holiday Logic (can be expanded) ===
def is_holiday(today=None):
    if today is None:
        today = get_ist_time().date()
    
    holidays = [
        # Add your actual NSE holiday dates here (yyyy-mm-dd)
        datetime(2025, 1, 26).date(),  # Republic Day
        datetime(2025, 8, 15).date(),  # Independence Day
        datetime(2025, 10, 2).date(),  # Gandhi Jayanti
    ]
    return today in holidays

# === Manual Stop / Force Flags ===
def check_manual_exit():
    return os.path.exists(STOP_FLAG_FILE)

def check_force_entry():
    return os.path.exists(FORCE_ENTRY_FILE)

# === Strike Rounding ===
def get_strike_prices(spot_price):
    atm = round(spot_price / 50) * 50
    ce_strike = atm + 300
    pe_strike = atm - 300
    return pe_strike, ce_strike

# === Get Next Week Expiry ===
def get_next_week_expiry():
    today = get_ist_time().date()
    weekday = today.weekday()  # Monday = 0

    days_ahead = (3 - weekday + 7) % 7  # 3 = Thursday
    if days_ahead == 0:
        days_ahead = 7
    expiry = today + timedelta(days=days_ahead)
    return expiry.strftime('%Y-%m-%d')

# === Calculate MTM ===
def get_mtm(positions):
    return sum((p['ltp'] - p['entry_price']) * p['quantity'] for p in positions)

# === Margin Estimator (per lot) ===
def get_required_margin():
    # Approx ₹90,000 for 1-lot Iron Condor
    return 90000

# === Logger for quick debug ===
def log(message):
    timestamp = get_ist_time().strftime('%Y-%m-%d %H:%M:%S')
    with open("logs/strategy.log", "a") as f:
        f.write(f"{timestamp} - {message}\n")
