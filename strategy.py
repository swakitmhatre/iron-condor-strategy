# strategy.py

import os
import time
from datetime import datetime
from market_status import is_market_open
from position_handler import place_iron_condor, exit_all_positions
from telegram_utils import send_telegram_message
from utils import log_message, read_mtm, get_required_margin

def run_strategy():
    log_message("Iron Condor strategy running")

    is_open, reason = is_market_open()
    log_message(reason)
    if not is_open and not os.path.exists("force_entry.flag"):
        return

    log_message("Iron Condor strategy started")
    send_telegram_message("🟢 Strategy Started")

    # Place iron condor positions
    place_iron_condor()

    entry_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    margin_required = get_required_margin()
    target_profit = margin_required * 0.002  # 0.2% of margin

    log_message(f"Target MTM profit: ₹{target_profit:.2f}")
    send_telegram_message(f"🎯 MTM Target: ₹{target_profit:.2f}")

    target_reached_time = None

    # Continuous monitoring
    while True:
        mtm = read_mtm()
        log_message(f"Current MTM: ₹{mtm:.2f}")

        if mtm >= target_profit and target_reached_time is None:
            target_reached_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_message(f"MTM target first reached at: {target_reached_time}")
            send_telegram_message(f"✅ MTM Target Reached at {target_reached_time} (₹{mtm:.2f})")

        # Manual exit trigger
        if os.path.exists("stop.flag"):
            log_message("Manual exit triggered")
            send_telegram_message("🛑 Manual exit triggered")
            exit_all_positions()
            break

        # Sudden market move exit condition (handled inside exit_all_positions)
        if abs(mtm) > margin_required * 0.01:  # >1% move
            log_message("⚠️ MTM >1% detected, exiting all positions")
            send_telegram_message("⚠️ MTM exceeded 1%, exiting positions")
            exit_all_positions()
            break

        time.sleep(30)

    exit_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message(f"Strategy exited at {exit_time} | Final MTM: ₹{mtm:.2f}")
    send_telegram_message(f"🔚 Strategy exited at {exit_time}\nFinal MTM: ₹{mtm:.2f}")
