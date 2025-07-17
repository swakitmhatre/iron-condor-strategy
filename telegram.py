import requests

BOT_TOKEN = "7770202577:AAHjZFGJg2Gt3c5S77i__SOCMVqRXd6ofY0"
CHAT_ID = "1872844861"

def send_telegram_update(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, data=data, timeout=5)
    except Exception as e:
        print(f"Telegram error: {e}")
