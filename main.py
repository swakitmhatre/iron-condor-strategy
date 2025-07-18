# main.py

from strategy import run_strategy
from utils import log_message

if __name__ == "__main__":
    log_message("Iron Condor strategy running")
    try:
        run_strategy()
    except Exception as e:
        log_message(f"Unhandled Exception: {e}")
