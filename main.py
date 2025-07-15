from strategy import run_strategy
from utils.logger import setup_logger
from utils.telegram_bot import send_telegram_message
import time

logger = setup_logger()

logger.info("Starting Iron Condor strategy")

try:
    send_telegram_message("🚀 Iron Condor strategy has started.")
    run_strategy()
except Exception as e:
    logger.exception("Exception in main strategy loop")
    send_telegram_message(f"❌ Strategy crashed with error:\n{e}")
