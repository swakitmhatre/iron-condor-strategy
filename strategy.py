import os
import time
import logging
from market_status import is_market_open
from dhan_api import DhanTrader
from position_handler import place_iron_condor, exit_all_positions
from telegram_notifier import send_telegram_message
from utils import get_mtm, get_required_margin, get_next_week_expiry

MTM_TARGET_PCT = 0.20 / 100  # 0.20%
CHECK_INTERVAL = 10  # seconds
MANUAL_EXIT_FLAG = "stop.flag"
FORCE_ENTRY_FLAG = "force_entry.flag"
LOG_FILE = "logs/strategy.log"

# Setup logging
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format="%(asctime)s - %(message)s")

def run_strategy():
    logging.info("Iron Condor strategy started")
    send_telegram_message("Iron Condor strategy started.")

    # Initialize trader
    trader = DhanTrader()

    # Check market open
    if not is_market_open():
        reason = "Market closed"
        logging.info(reason)
        send_telegram_message(reason)
        return

    # Get expiry (next week)
    expiry = get_next_week_expiry()

    # Calculate margin for 1 lot
    margin_required = get_required_margin(trader)
    if margin_required is None:
        logging.error("Could not fetch margin required")
        send_telegram_message("Could not fetch margin required.")
        return

    target_mtm = margin_required * MTM_TARGET_PCT
    logging.info(f"Margin Required: ₹{margin_required:.2f} | Target MTM: ₹{target_mtm:.2f}")

    # Decide to enter
    if not os.path.exists(FORCE_ENTRY_FLAG) and not trader.check_market_conditions():
        reason = "Unfavorable market conditions. No trade."
        logging.info(reason)
        send_telegram_message(reason)
        return

    # Place positions
    positions = place_iron_condor(trader, expiry)
    if not positions:
        logging.error("Position placement failed")
        send_telegram_message("Failed to place Iron Condor.")
        return
    send_telegram_message(f"Entered Iron Condor.\n{positions}")

    entry_time = time.strftime("%Y-%m-%d %H:%M:%S")
    mtm_first_reach_time = None

    # Monitor loop
    while True:
        time.sleep(CHECK_INTERVAL)

        if os.path.exists(MANUAL_EXIT_FLAG):
            logging.info("Manual exit flag detected. Exiting...")
            send_telegram_message("Manual exit flag triggered. Exiting all positions.")
            break

        mtm = get_mtm(trader)
        logging.info(f"Current MTM: ₹{mtm:.2f}")

        if mtm >= target_mtm and not mtm_first_reach_time:
            mtm_first_reach_time = time.strftime("%Y-%m-%d %H:%M:%S")
            logging.info(f"MTM target first reached at {mtm_first_reach_time}")

        if mtm >= target_mtm:
            logging.info("MTM target hit. Exiting...")
            send_telegram_message(f"MTM target ₹{target_mtm:.2f} hit.\nExiting all positions.")
            break

        if trader.has_nifty_moved_1_percent():
            logging.info("NIFTY moved >1%. Exiting...")
            send_telegram_message("NIFTY moved >1%. Exiting all positions.")
            break

    exit_all_positions(trader)
    logging.info(f"Exited at {time.strftime('%Y-%m-%d %H:%M:%S')} | Final MTM: ₹{get_mtm(trader):.2f}")
    send_telegram_message("All positions exited.")

