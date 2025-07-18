# utils.py

import os
import logging
from datetime import datetime, time
from dhan import Dhan
from instruments import get_nifty_option_symbol

logger = logging.getLogger()

# ---- Market Conditions ----

def is_market_open():
    now = datetime.now().time()
    return time(9, 15) <= now <= time(15, 30)

def within_entry_window():
    now = datetime.now().time()
    return time(9, 20) <= now <= time(9, 45)

# ---- Iron Condor Entry ----

def place_iron_condor(dhan: Dhan, spot_price: float):
    ce_strike = round(spot_price / 50) * 50 + 200  # OTM CE
    pe_strike = round(spot_price / 50) * 50 - 200  # OTM PE

    expiry = dhan.get_next_week_expiry()

    symbols = {
        "ce_sell": get_nifty_option_symbol(expiry, ce_strike, "CE"),
        "pe_sell": get_nifty_option_symbol(expiry, pe_strike, "PE"),
        "ce_buy": get_nifty_option_symbol(expiry, ce_strike + 100, "CE"),
        "pe_buy": get_nifty_option_symbol(expiry, pe_strike - 100, "PE"),
    }

    qty = 50  # 1 lot
    positions = []

    # Buy Legs First (for margin efficiency)
    dhan.place_order(symbols["ce_buy"], qty, "BUY")
    dhan.place_order(symbols["pe_buy"], qty, "BUY")
    dhan.place_order(symbols["ce_sell"], qty, "SELL")
    dhan.place_order(symbols["pe_sell"], qty, "SELL")

    positions.extend(symbols.values())
    return positions

# ---- Safe Exit Logic ----

def exit_all_positions():
    try:
        with open("open_positions.txt", "r") as f:
            symbols = [line.strip() for line in f.readlines()]
    except FileNotFoundError:
        logger.info("No open positions to exit.")
        return

    try:
        dhan = Dhan(os.getenv("DHAN_ACCESS_TOKEN"), os.getenv("DHAN_CLIENT_ID"))
        for sym in symbols:
            dhan.place_order(sym, 50, "EXIT")
            logger.info(f"Exited: {sym}")
    except Exception as e:
        logger.error(f"Error during exit: {e}")
