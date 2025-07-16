from datetime import datetime, timedelta
from utils import log_message

def market_open():
    """Check if the current time is within market hours (IST)."""
    now_utc = datetime.utcnow()
    now_ist = now_utc + timedelta(hours=5, minutes=30)

    # Define market start and end
    market_start = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    market_end = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)

    # Log exact time check
    log_message(f"[DEBUG] UTC Time: {now_utc.strftime('%Y-%m-%d %H:%M:%S')}, IST Time: {now_ist.strftime('%Y-%m-%d %H:%M:%S')}")
    log_message(f"[DEBUG] Market Open: {market_start.strftime('%H:%M:%S')} - {market_end.strftime('%H:%M:%S')}")

    # Final check
    if market_start <= now_ist <= market_end:
        return True
    else:
        log_message("Market closed")
        return False
