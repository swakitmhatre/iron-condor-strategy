import os
import json
import time
import requests
from datetime import datetime

# Readable timestamp
def now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# Send Telegram alert
def send_telegram_message(bot_token, chat_id, message):
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message}
        requests.post(url, data=payload)
    except Exception as e:
        print(f"[{now()}] Telegram send error: {e}")
        
# Check if market is open (simple check for NSE timings)
def is_market_open():
    now_time = datetime.now().time()
    return now_time >= datetime.strptime("09:15", "%H:%M").time() and now_time <= datetime.strptime("15:30", "%H:%M").time()


# Write strategy logs
def log(message, log_file="strategy.log"):
    timestamp = now()
    with open(log_file, "a") as f:
        f.write(f"[{timestamp}] {message}\n")
    print(f"[{timestamp}] {message}")

# Read config
def read_config():
    with open("config.py", "r") as f:
        return f.read()

# Read MTM from file
def read_mtm(path="logs/mtm.json"):
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        return json.load(f)

# Write MTM to file
def write_mtm(data, path="logs/mtm.json"):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

# Stop flag check
def stop_flag_exists():
    return os.path.exists("stop.flag")

# Force entry flag
def force_entry_exists():
    return os.path.exists("force_entry.flag")
