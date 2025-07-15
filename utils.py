# Utility functions like log_message(), send_telegram_message() etc.
import logging
import os

def setup_logger():
    log_file = "strategy.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, mode='a'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger()
