import os
import pytz
import logging
from datetime import datetime, time
import requests

# === Logging setup ===
LOG_FILE = 'logs/strategy.log'
os.makedirs('logs', exist_ok=True)
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s - %(message)s')

# === Timezone ===
IST = pytz.timezone('Asia/Kolkata')

def now():
    """Returns current datetime in IST."""
    return datetime.now(IST)

def log_message(msg):
    """Log + print message with timestamp."""
    timestamp = now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"{timestamp} - {msg}")
    logging.info(msg)

def is_market_open():
    """Returns True if current IST time is within market hours (9:15 AM to 3:30 PM)."""
    current_time = now().time()
    market_start = time(9, 15)
    market_end = time(15, 30)
    return market_start <= current_time <= market_end

def send_telegram_message(message):
    """Send a Telegram alert using bot token and chat ID."""
    try:
        token = "7770202577:AAHjZFGJg2Gt3c5S77i__SOCMVqRXd6ofY0"
        chat_id = "1872844861"
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message}
        requests.post(url, data=payload)
    except Exception as e:
        log_message(f"Telegram error: {e}")

def get_strike_prices(spot_price, step=50):
    """Return closest ATM strike and 1-step OTM strikes for Iron Condor."""
    spot = round(spot_price / step) * step
    ce_sell = spot + 0  # ATM CE
    ce_buy = ce_sell + step
    pe_sell = spot - 0  # ATM PE
    pe_buy = pe_sell - step
    return {
        "ce_sell": ce_sell,
        "ce_buy": ce_buy,
        "pe_sell": pe_sell,
        "pe_buy": pe_buy
    }
