# strategy.py

import logging
import os
from datetime import datetime
from utils import is_market_open, within_entry_window, place_iron_condor, exit_all_positions
from instruments import get_nifty_spot
from config import (
    STRATEGY_MARGIN,
    MTM_TARGET_PERCENT,
    MTM_STOPLOSS_PERCENT,
    ENTRY_START_TIME,
    ENTRY_END_TIME,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    FORCE_NEXT_WEEK_EXPIRY,
)
from telegram_utils import send_telegram_message
from dhan_api import Dhan
logger = logging.getLogger()

def run_strategy():
    logger.info("Strategy started")

    # Manual override check
    force_entry = os.path.exists("force_entry.flag")
    if force_entry:
        logger.info("✔ Force entry flag detected.")

    # Check market status
    if not force_entry and not is_market_open():
        logger.info("✖ Market is closed. Exiting strategy.")
        return

    # Entry time window check
    if not force_entry and not within_entry_window():
        logger.info("✖ Not within entry window. Exiting strategy.")
        return

    # Initialize Dhan API
    try:
        dhan = Dhan(DHAN_ACCESS_TOKEN, DHAN_CLIENT_ID)
        spot_price = dhan.get_nifty_spot()
        logger.info(f"NIFTY spot: {spot_price}")
    except Exception as e:
        logger.error(f"Error executing strategy: {e}")
        exit_all_positions()
        return

    # Place Iron Condor
    try:
        position_ids = place_iron_condor(dhan, spot_price)
        logger.info(f"✅ Iron Condor placed. Position IDs: {position_ids}")
    except Exception as e:
        logger.error(f"❌ Failed to place Iron Condor: {e}")
        exit_all_positions()
        return

    # Monitor MTM (basic loop can be expanded later)
    logger.info(f"🎯 Strategy live. Monitoring for MTM target: {MTM_TARGET_PERCENT}%")
