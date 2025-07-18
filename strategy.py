# strategy.py

import os
import time
from utils import *
from filters import *
from dhan import Dhan
from position_handler import place_iron_condor

# Entry window
entry_start = time_obj(9, 15)
entry_end = time_obj(15, 30)

def run_strategy():
    log_message("Iron Condor strategy started")

    # Market open check
    if not is_market_open():
        log_message("Market is closed. Exiting.")
        return

    # Time window check
    now = datetime.now().time()
    if not (entry_start <= now <= entry_end):
        log_message("Outside entry time window. Exiting.")
        return

    # Conditions
    if os.path.exists("force_entry.flag"):
        log_message("Force entry flag detected. Proceeding despite filters.")
    elif not is_conditions_favorable():
        log_message("Unfavorable market conditions. Entry aborted.")
        return

    # Setup Dhan
    from config import DHAN_AUTH_TOKEN, DHAN_CLIENT_ID
    dhan = Dhan(DHAN_AUTH_TOKEN, DHAN_CLIENT_ID)

    log_message("Conditions favorable. Executing strategy...")

    try:
        success, positions = place_iron_condor(dhan)
        if success:
            log_message("Positions placed successfully.")
        else:
            log_message("Failed to place positions.")
    except Exception as e:
        log_message(f"Exception occurred: {e}")
        log_message("Exited all positions due to Exception.")
