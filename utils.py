import os
from datetime import datetime

LOG_FILE = "strategy.log"
MTM_FILE = "mtm.txt"

def log_message(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    full_message = f"{timestamp} - {message}"
    print(full_message)
    with open(LOG_FILE, "a") as f:
        f.write(full_message + "\n")

def save_mtm(mtm_value):
    with open(MTM_FILE, "w") as f:
        f.write(str(mtm_value))

def get_mtm():
    try:
        with open(MTM_FILE, "r") as f:
            return float(f.read())
    except FileNotFoundError:
        return 0.0

def get_required_margin():
    # Placeholder: Replace this with dynamic margin logic if available
    return 110000.0  # for 1-lot Iron Condor approx
