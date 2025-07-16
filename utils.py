import os
import pytz
import logging
from datetime import datetime, timedelta, time
import requests
from dhan import Dhan

# === Logging Setup ===
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
    ce_sell = spot
    ce_buy = ce_sell + step
    pe_sell = spot
    pe_buy = pe_sell - step
    return {
        "ce_sell": ce_sell,
        "ce_buy": ce_buy,
        "pe_sell": pe_sell,
        "pe_buy": pe_buy
    }

def get_mtm(positions):
    """Calculate MTM PnL from current positions."""
    mtm = 0
    for p in positions:
        buy_price = p.get('average_price', 0)
        ltp = p.get('ltp', 0)
        quantity = abs(p.get('quantity', 0))
        direction = 1 if p['transaction_type'] == 'BUY' else -1
        mtm += direction * (ltp - buy_price) * quantity
    return mtm

def get_required_margin(dhan: Dhan):
    """Estimate margin from Dhan positions."""
    try:
        positions = dhan.get_positions()
        unique_symbols = set([p['trading_symbol'] for p in positions])
        return 150000 * len(unique_symbols) / 4  # rough estimate per lot
    except Exception as e:
        log_message(f"Margin fetch error: {e}")
        return 150000  # fallback to single-lot margin

def get_next_week_expiry():
    """Return next Thursday's date string in yyyy-mm-dd format."""
    today = now().date()
    days_ahead = (3 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    next_thursday = today + timedelta(days=days_ahead)
    return next_thursday.strftime('%Y-%m-%d')
