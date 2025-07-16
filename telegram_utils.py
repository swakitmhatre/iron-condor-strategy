# telegram_utils.py

import requests
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from utils import log_message

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log_message("Telegram token or chat ID not set. Skipping Telegram alert.")
        return

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message
        }
        response = requests.post(url, data=data)
        if response.status_code != 200:
            log_message(f"Failed to send Telegram message: {response.text}")
    except Exception as e:
        log_message(f"Telegram error: {e}")
