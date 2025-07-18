
# utils.py

from datetime import datetime

def log_message(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    message = f"{timestamp} - {msg}"
    print(message)
    with open("strategy.log", "a") as f:
        f.write(message + "\n")


'''from datetime import datetime
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
import requests

def log_message(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    final_msg = f"{ts} - {msg}"
    print(final_msg)
    with open("strategy.log", "a") as f:
        f.write(final_msg + "\n")
    send_telegram_message(msg)

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, data=payload)
    except:
        pass'''
