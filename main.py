# main.py
import logging
from strategy import run_strategy

logging.basicConfig(
    filename='logs/strategy.log',
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
)

logging.info("Iron Condor strategy running")
run_strategy()
