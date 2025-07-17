import requests
import json

BOT_TOKEN = "7770202577:AAHjZFGJg2Gt3c5S77i__SOCMVqRXd6ofY0"
CHAT_ID = "1872844861"

def send_telegram_message(message: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        response = requests.post(url, data=payload, timeout=5)
        if not response.ok:
            print(f"Telegram failed: {response.status_code}, {response.text}")
    except Exception as e:
        print(f"Telegram error: {e}")
