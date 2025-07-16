# Checks IV, gap-up, 1% NIFTY movement etc.
# filters.py

import datetime
from market_status import is_market_open
from datetime import datetime, timedelta
import os

def market_open():
    """Check if the current time is within market hours (IST)."""
    now_utc = datetime.utcnow()
    now_ist = now_utc + timedelta(hours=5, minutes=30)
    market_start = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    market_end = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_start <= now_ist <= market_end


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
