import requests
from datetime import datetime

def is_market_open():
    try:
        now = datetime.now()
        if now.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
            return False

        current_time = now.time()
        market_open = current_time >= datetime.strptime("09:15", "%H:%M").time()
        market_close = current_time <= datetime.strptime("15:30", "%H:%M").time()

        return market_open and market_close
    except Exception as e:
        print(f"Error checking market status: {e}")
        return False
