# strategy.py

import time
import os
from datetime import datetime

from dhan import Dhan
from config import *
from position_handler import place_iron_condor, exit_all_positions
from utils import log_message, get_mtm, get_required_margin
from telegram_utils import send_telegram_message
from time_helper import is_market_open

def run_strategy():
    log_message("Iron Condor strategy started")

    if not is_market_open():
        log_message("Market closed")
        return

    if not os.path.exists("entry.flag") and not os.path.exists("force_entry.flag"):
        log_message("No entry.flag or force_entry.flag present")
        return

    dhan = Dhan()

    # Place iron condor
    success, positions = place_iron_condor(dhan)
    if not success:
        log_message("Failed to place iron condor")
        return

    log_message("Iron Condor placed successfully")
    send_telegram_message("🟢 Iron Condor placed successfully.")

    entry_time = datetime.now().strftime("%H:%M:%S")
    margin_required = get_required_margin(positions)
    target_profit = margin_required * 0.002  # 0.20% target

    log_message(f"Target PnL: ₹{target_profit:.2f} | Margin used: ₹{margin_required:.2f}")
    send_telegram_message(f"🎯 Target: ₹{target_profit:.2f} | Margin: ₹{margin_required:.2f}")

    while True:
        time.sleep(5)

        # Manual exit
        if os.path.exists("stop.flag"):
            log_message("Manual stop.flag found. Exiting...")
            send_telegram_message("🛑 Manual stop.flag detected. Exiting positions.")
            break

        # Exit if NIFTY moves >1% or market closed
        if not is_market_open():
            log_message("Market closed mid-session. Exiting...")
            break

        mtm = get_mtm(positions)
        log_message(f"Live PnL: ₹{mtm:.2f}")

        if mtm >= target_profit:
            log_message(f"🎉 MTM target reached at ₹{mtm:.2f}")
            send_telegram_message(f"🎉 Target hit! Profit: ₹{mtm:.2f}")
            break

    exit_all_positions(dhan, positions)
    log_message(f"Exited all positions at {datetime.now().strftime('%H:%M:%S')}")
    send_telegram_message("📤 Exited all positions successfully.")
