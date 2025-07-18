# utils.py

import os
from datetime import datetime, time
import logging
from dhan_api import Dhan
from instruments import get_option_symbols, get_option_ltp, get_next_thursday_expiry

from config import ENTRY_START_TIME, ENTRY_END_TIME

def is_market_open():
    now = datetime.now().time()
    return time(9, 15) <= now <= time(15, 30)

def within_entry_window():
    now = datetime.now().time()
    return ENTRY_START_TIME <= now <= ENTRY_END_TIME

def place_iron_condor(dhan: Dhan, spot_price: float, use_next_week: bool):
    expiry = get_next_thursday_expiry(weeks_ahead=1 if use_next_week else 0)
    ce_sell, ce_buy, pe_sell, pe_buy = get_option_symbols(spot_price, expiry)

    # Place buy legs first
    dhan.place_order(ce_buy, 'BUY')
    dhan.place_order(pe_buy, 'BUY')
    dhan.place_order(ce_sell, 'SELL')
    dhan.place_order(pe_sell, 'SELL')

    return [ce_sell, ce_buy, pe_sell, pe_buy]

def exit_all_positions(dhan: Dhan):
    positions = dhan.get_positions()
    for pos in positions:
        if pos['quantity'] != 0:
            dhan.exit_position(pos['trading_symbol'])

def calculate_mtm(dhan: Dhan, traded_symbols: list):
    mtm = 0
    for sym in traded_symbols:
        ltp = get_option_ltp(dhan, sym)
        if ltp is None:
            continue
        buy_or_sell = 'SELL' if 'CE' in sym or 'PE' in sym else 'BUY'
        mtm += -ltp if buy_or_sell == 'SELL' else ltp
    return mtm

def save_timestamp_log(event_type: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    filename = "target_hit.log" if event_type == "target" else "stoploss_hit.log"
    with open(filename, "a") as f:
        f.write(f"{now}\n")
