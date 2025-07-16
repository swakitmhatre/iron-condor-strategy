from datetime import datetime, time
from pytz import timezone
from utils import log_message

def market_open():
    """
    Checks if current time (IST) is within Indian market hours.
    Market hours: 09:15 to 15:30 IST, Monday to Friday
    """

    # Use pytz to get IST timezone
    ist = timezone('Asia/Kolkata')
    now_ist = datetime.now(ist)

    # Define market start and end times
    market_start = time(9, 15)
    market_end = time(15, 30)

    # Log debug info
    log_message(f"[DEBUG] Current IST time: {now_ist.strftime('%Y-%m-%d %H:%M:%S')}")

    # Check for weekend
    if now_ist.weekday() >= 5:
        log_message("Market closed (Weekend)")
        return False

    # Check time range
    current_time = now_ist.time()
    if market_start <= current_time <= market_end:
        return True

    log_message("Market closed (Outside market hours)")
    return False
