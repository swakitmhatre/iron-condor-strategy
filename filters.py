# filters.py

from datetime import datetime, time
from utils import log_message

def time_obj(hr, min):
    return time(hr, min)

def is_market_open():
    now = datetime.now().time()
    return time(9, 15) <= now <= time(15, 30)

def is_conditions_favorable():
    # For now always true. You can add IV, news, or trend filters here.
    return True
