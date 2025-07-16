from datetime import datetime, timedelta
from utils import log_message

def market_open():
    """
    Check if the market is open based on Indian market hours (IST).
    Market hours: Monday–Friday, 09:15 to 15:30 IST
    """
    now_utc = datetime.utcnow()
    now_ist = now_utc + timedelta(hours=5, minutes=30)

    market_start = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
    market_end = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)

    log_message(f"[DEBUG] UTC now: {now_utc.strftime('%Y-%m-%d %H:%M:%S')}")
    log_message(f"[DEBUG] IST now: {now_ist.strftime('%Y-%m-%d %H:%M:%S')}")
    log_message(f"[DEBUG] Market hours (IST): {market_start.strftime('%H:%M:%S')} - {market_end.strftime('%H:%M:%S')}")

    if now_ist.weekday() >= 5:
        log_message("Market closed (Weekend)")
        return False

    if market_start <= now_ist <= market_end:
        return True

    log_message("Market closed (Outside market hours)")
    return False
