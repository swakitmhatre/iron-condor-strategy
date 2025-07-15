# utils.py

import requests
import logging
from datetime import datetime

def setup_logger(name, log_file, level=logging.INFO):
    handler = logging.FileHandler(log_file)
    formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
    handler.setFormatter(formatter)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    if not logger.hasHandlers():
        logger.addHandler(handler)
    return logger

# Main strategy logger
strategy_logger = setup_logger('strategy', 'logs/strategy.log')

def send_telegram_message(bot_token, chat
