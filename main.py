# main.py

from strategy import run_strategy

if __name__ == "__main__":
    import logging
    from utils import setup_logger
    setup_logger()
    logging.info("Iron Condor strategy running")
    run_strategy()
