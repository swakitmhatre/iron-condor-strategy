# main.py

from strategy import run_strategy
from utils import log_message

if __name__ == "__main__":
    log_message("Iron Condor strategy running")
    try:
        run_strategy()
    except Exception as e:
        log_message(f"Exception occurred: {e}")





'''# main.py

import os
import time
from datetime import datetime
from utils import *
from config import *
from dhan_api import DhanTrader
from position_handler import PositionHandler
from market_status import is_market_open
from filters import is_time_between, is_conditions_favorable
from config import ENTRY_START, ENTRY_END


entry_start_time = "09:30"
entry_end_time = "14:30"

log_message("Iron Condor strategy running")
trader = DhanTrader()
handler = PositionHandler(trader)

try:
    if not is_market_open():
        log_message("Market is closed. Exiting.")
        exit()

   # Manual override check first
    if os.path.exists("force_entry.flag"):
        log_message("Force entry flag detected. Proceeding despite filters.")
    else:
        # Entry Time Window Check
        if not is_time_between(entry_start_time, entry_end_time):
            log_message("Outside entry time window. Exiting.")
            exit()

        # Market conditions check
        if not is_conditions_favorable():
            log_message("Unfavorable market conditions. Entry aborted.")
            exit()
    log_message("Conditions favorable. Executing strategy...")
    handler.execute_iron_condor()

    while True:
        if os.path.exists("stop.flag"):
            log_message("Manual stop triggered")
            handler.exit_all_positions(reason="Manual Stop")
            break

        if handler.check_mtm_targets():
            break

        if handler.check_intraday_movement():
            break

        time.sleep(CHECK_INTERVAL)

except Exception as e:
    log_message(f"Exception occurred: {e}")
    try:
        handler.exit_all_positions(reason="Exception")
    except:
        log_message("Emergency exit failed.")
        '''
