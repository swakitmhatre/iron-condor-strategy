# filters.py

from datetime import datetime, time
from utils import log_message

def time_obj(hr, minute):
    return time(hr, minute)

def is_market_open():
    now = datetime.now().time()
    return time(9,15) <= now <= time(15,30)

def is_conditions_favorable():
    # Placeholder
    return True
