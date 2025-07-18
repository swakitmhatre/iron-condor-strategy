# strategy.py

import os
import time as t
from datetime import datetime
from config import *
from dhan import Dhan
from utils import send_telegram_message

def run_strategy():
    from utils import setup_logger
    setup_logger()
    logging = __import__('logging')

    logging.info("Strategy started")

    if os.path.exists(FORCE_ENTRY_FILE):
        logging.info("✔ Force entry flag detected.")
    else:
        logging.info("⏹ No force entry. Exiting.")
        return

    try:
        api = Dhan()
        spot_price = api.get_nifty_spot_price()
        logging.info(f"NIFTY spot price: {spot_price}")

        # [Your Iron Condor logic would go here...]
        send_telegram_message(f"🔔 Entry executed. Spot: {spot_price}")

    except Exception as e:
        logging.error(f"Error executing strategy: {e}")
        send_telegram_message(f"❌ Strategy failed: {e}")
