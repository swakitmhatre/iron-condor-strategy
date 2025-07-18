# utils.py

from datetime import datetime

def log_message(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    text = f"{ts} - {msg}"
    print(text)
    with open("strategy.log", "a") as f:
        f.write(text + "\n")
