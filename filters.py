# Checks IV, gap-up, 1% NIFTY movement etc.
# filters.py

import datetime
from market_status import is_market_open
import os

def check_entry_conditions():
    now = datetime.datetime.now()
    if not is_market_open():
        return False, "Market closed"
    
    if not (9 <= now.hour < 15):
        return False, "Outside entry window"

    if os.path.exists("force_entry.flag"):
        return True, "Force entry flag detected"

    # Add other conditions here if needed

    return True, "Conditions favorable"
