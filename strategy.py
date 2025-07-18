# strategy.py

import os
import time
from datetime import datetime
from dhan import Dhan
from filters import *
from position_handler import place_iron_condor
from utils import log_message
from config import DHAN_AUTH_TOKEN, DHAN_CLIENT_ID

entry_start = time_obj(9,15)
entry_end = time_obj(15,30)

def run_strategy():
    log_message("Strategy started")

    if not is_market_open():
        log_message("Market closed.")
        return

    tnow = datetime.now().time()
    if not (entry_start <= tnow <= entry_end):
        log_message("Outside entry time.")
        return

    if os.path.exists("force_entry.flag"):
        log_message("✔ Force entry flag detected.")
    elif not is_conditions_favorable():
        log_message("⚠ Conditions unfavorable.")
        return

    dhan = Dhan(DHAN_AUTH_TOKEN, DHAN_CLIENT_ID)

    try:
        ok, details = place_iron_condor(dhan)
        msg = "placed" if ok else "failed"
        log_message(f"Entry {msg}: {details}")
    except Exception as e:
        log_message(f"Error executing strategy: {e}")
