import os
import json
from datetime import datetime

def log_message(msg):
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {msg}")
    with open("strategy.log", "a") as f:
        f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - {msg}\n")

def get_strike_prices(spot, step=50):
    atm = round(spot / step) * step
    return {
        "ce_sell": atm + 300,
        "pe_sell": atm - 300,
        "ce_buy": atm + 500,
        "pe_buy": atm - 500
    }

def should_exit_due_to_market_move(initial_spot, current_spot):
    move_percent = abs(current_spot - initial_spot) / initial_spot
    return move_percent >= 0.01

def check_manual_exit():
    return os.path.exists("stop.flag")

def check_force_entry():
    return os.path.exists("force_entry.flag")
