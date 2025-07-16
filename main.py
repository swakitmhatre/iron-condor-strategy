# main.py

from strategy import run_strategy
from utils import log


if __name__ == "__main__":
    #log_message("Iron Condor strategy running")
    log("Main.py started successfully")

    run_strategy()


'''from strategy import run_strategy
from utils import log_message

from utils.telegram_bot import send_telegram_message
import time

logger = setup_logger()

logger.info("Starting Iron Condor strategy")

try:
    send_telegram_message("🚀 Iron Condor strategy has started.")
    run_strategy()
except Exception as e:
    logger.exception("Exception in main strategy loop")
    send_telegram_message(f"❌ Strategy crashed with error:\n{e}")'''
