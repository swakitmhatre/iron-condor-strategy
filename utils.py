# utils.py

import datetime
import os
import pytz
import json
import requests

# Constants
LOT_SIZE = 50  # for NIFTY

def get_ist_now():
    return datetime.datetime.now(pytz.timezone("Asia/Kolkata"))

def get_next_week_expiry():
    today = get_ist_now().date()
    weekday = today.weekday()

    # If today is Thursday (3), next expiry is next Thursday
    days_ahead = 3 - weekday + 7
    next_expiry = today + datetime.timedelta(days=days_ahead)
    return next_expiry.strftime("%Y-%m-%d")

def get_strike_prices(spot_price, step=50):
    atm = round(spot_price / step) * step
    ce_strike = atm + 300
    pe_strike = atm - 300
    hedge_ce = ce_strike + 200
    hedge_pe = pe_strike - 200
    return ce_strike, pe_strike, hedge_ce, hedge_pe

def get_mtm(positions_file="logs/positions.json"):
    try:
        if not os.path.exists(positions_file):
            return 0.0

        with open(positions_file, "r") as f:
            data = json.load(f)

        total_mtm = 0.0
        for pos in data.get("positions", []):
            total_mtm += pos.get("pnl", 0.0)
        return round(total_mtm, 2)
    except Exception as e:
        print(f"[MTM] Error calculating MTM: {e}")
        return 0.0

def get_required_margin():
    # Replace with actual margin fetching using Dhan API if needed
    # For now assume ₹1.2 lakh per Iron Condor (4 legs)
    return 120000.0

def log_message(message, log_file="logs/strategy.log"):
    now = get_ist_now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, "a") as f:
        f.write(f"[{now}] {message}\n")
    print(f"[{now}] {message}")
