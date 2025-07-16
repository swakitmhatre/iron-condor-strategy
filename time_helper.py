# time_helper.py

from datetime import datetime, time
import pytz

def is_market_open():
    india_tz = pytz.timezone("Asia/Kolkata")
    now = datetime.now(india_tz)
    market_open = time(9, 15)
    market_close = time(15, 30)

    if now.weekday() >= 5:
        return False, "Market closed (Weekend)"
    if now.time() < market_open:
        return False, "Market not yet opened"
    if now.time() > market_close:
        return False, "Market closed (Post 3:30 PM)"
    return True, "Market is open"
