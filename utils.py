import os
import pytz
import logging
from datetime import datetime, time

# Setup logging
LOG_FILE = 'logs/strategy.log'
os.makedirs('logs', exist_ok=True)
logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s - %(message)s')

IST = pytz.timezone('Asia/Kolkata')

def now():
    """Returns current time in IST."""
    return datetime.now(IST)

def log_message(msg):
    """Logs and prints a message with timestamp."""
    timestamp = now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"{timestamp} - {msg}")
    logging.info(msg)

def is_market_open():
    """Returns True if current IST time is within market hours (9:15 to 15:30)."""
    current_time = now().time()
    market_start = time(9, 15)
    market_end = time(15, 30)
    return market_start <= current_time <= market_end

def send_telegram_message(message):
    """Send Telegram alert using bot token and chat ID."""
    import requests
    token = "7770202577:AAHjZFGJg2Gt3c5S77i__SOCMVqRXd6ofY0"
    chat_id = "1872844861"
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message}
        requests.post(url, data=payload)
    except Exception as e:
        log_message(f"Telegram error: {e}")
