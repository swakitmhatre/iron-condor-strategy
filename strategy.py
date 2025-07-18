# strategy.py

import logging
import os
from datetime import datetime
from utils import (
    is_market_open,
    within_entry_window,
    place_iron_condor,
    exit_all_positions,
    calculate_mtm,
    save_timestamp_log
)
from instruments import get_nifty_spot
from config import (
    STRATEGY_MARGIN,
    MTM_TARGET_PERCENT,
    MTM_STOPLOSS_PERCENT,
    ENTRY_START_TIME,
    ENTRY_END_TIME,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    FORCE_NEXT_WEEK_EXPIRY
)
from telegram_utils import send_telegram_message
from dhan_api import Dhan

# ✅ Instantiate Dhan API
dhan = Dhan()

# ✅ Main strategy runner
def run_strategy():
    logging.info("Strategy started")

    if os.path.exists("stop.flag"):
        logging.info("🛑 stop.flag detected. Exiting strategy.")
        return

    force_entry = os.path.exists("force_entry.flag")

    if force_entry:
        logging.info("✔ Force entry flag detected.")
    else:
        if not is_market_open():
            logging.info("⛔ Market is closed. Exiting.")
            return
        if not within_entry_window():
            logging.info("⏰ Outside entry window. Exiting.")
            return

    try:
        # ✅ Get NIFTY spot
        nifty_spot = get_nifty_spot(dhan)
        if not nifty_spot or not isinstance(nifty_spot, (int, float)):
            raise Exception(f"Fetch NIFTY spot failed: {nifty_spot}")
        logging.info(f"✅ NIFTY Spot: {nifty_spot}")

        # ✅ Place Iron Condor
        positions = place_iron_condor(dhan, nifty_spot, FORCE_NEXT_WEEK_EXPIRY)
        send_telegram_message("🟢 Iron Condor Placed", TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
        logging.info("✅ Iron Condor positions placed")

        # ✅ Track MTM
        while True:
            if os.path.exists("stop.flag"):
                logging.info("🛑 Manual stop.flag detected during monitoring. Exiting all.")
                send_telegram_message("🛑 Manual Exit Triggered", TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
                exit_all_positions(dhan)
                break

            mtm = calculate_mtm(dhan, positions)
            logging.info(f"📊 Live MTM: ₹{mtm:.2f}")

            target = STRATEGY_MARGIN * MTM_TARGET_PERCENT / 100
            stoploss = STRATEGY_MARGIN * MTM_STOPLOSS_PERCENT / 100

            if mtm >= target:
                logging.info(f"🎯 Target hit: ₹{mtm:.2f}")
                save_timestamp_log("target")
                send_telegram_message(f"🎯 Target hit ₹{mtm:.2f}", TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
                exit_all_positions(dhan)
                break
            elif mtm <= -stoploss:
                logging.info(f"⚠️ Stoploss hit: ₹{mtm:.2f}")
                save_timestamp_log("stoploss")
                send_telegram_message(f"🔴 Stoploss hit ₹{mtm:.2f}", TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
                exit_all_positions(dhan)
                break

    except Exception as e:
        logging.exception(f"❌ Error executing strategy: {e}")
        send_telegram_message(f"❌ Strategy error: {e}", TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)
