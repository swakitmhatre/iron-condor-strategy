# Sends alerts to your Telegram using bot token and chat_id
# telegram_notifier.py

import requests
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "Markdown"
        }
        response = requests.post(url, data=data)
        return response.status_code == 200
    except Exception as e:
        print(f"Telegram error: {e}")
        return False
