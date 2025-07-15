import os
import time
from datetime import datetime
from utils import *
from config import *
from dhan_api import DhanTrader
from position_handler import PositionHandler
from market_status import is_market_open

# Entry time window (you can customize)
entry_start_time = "09:30"
entry_end_time = "11:30"

# Initialize
log_message("Strategy started")
trader = DhanTrader()
handler = PositionHandler(trader)

try:
    # Exit if market is closed
    if not is_market_open():
        log_message("Market is closed. Exiting.")
        exit()

    # Entry Time Window Check
    if not is_time_between(entry_start_time, entry_end_time):
        log_message("Outside entry time window. Exiting.")
        exit()

    # Check if manual override
    if os.path.exists("force_entry.flag"):
        log_message("Force entry flag detected. Proceeding despite filters.")
    elif not is_conditions_favorable():
        log_message("Unfavorable market conditions. Entry aborted.")
        exit()

    # Run strategy
    log_message("Conditions favorable. Executing strategy...")
    handler.execute_iron_condor()

    # Monitor strategy
    while True:
        if os.path.exists("stop.flag"):
            log_message("Manual stop triggered via stop.flag")
            handler.exit_all_positions(reason="Manual Stop")
            break

        if handler.check_mtm_targets():
            break

        if handler.check_intraday_movement():
            break

        time.sleep(5)

except Exception as e:
    log_message(f"Exception: {e}")
    try:
        handler.exit_all_positions(reason="Error")
    except:
        log_message("Emergency exit failed")
