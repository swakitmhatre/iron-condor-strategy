# utils.py

import logging
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
import requests

def setup_logger():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(message)s",
        handlers=[
            logging.FileHandler("strategy.log"),
            logging.StreamHandler()
        ]
    )

def send_telegram_message(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
        requests.post(url, data=payload)
    except Exception as e:
        logging.error(f"Telegram error: {e}")
