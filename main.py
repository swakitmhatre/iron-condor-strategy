# main.py

import logging
from strategy import run_strategy

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
)

if __name__ == "__main__":
    logging.info("📈 Iron Condor strategy running")
    try:
        run_strategy()
    except Exception as e:
        logging.exception(f"❌ Strategy failed: {e}")
