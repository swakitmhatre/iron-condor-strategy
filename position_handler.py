# Handles entry, exit, MTM tracking, stop flag, intraday checks
# position_handler.py

from dhan_api import DhanTrader
from utils import get_strike_prices
from config import DHAN_API_KEY, DHAN_CLIENT_ID

dhan = DhanTrader(DHAN_API_KEY, DHAN_CLIENT_ID)

def place_iron_condor():
    atm_ce, atm_pe, otm_ce, otm_pe = get_strike_prices()

    orders = [
        {"symbol": otm_ce, "side": "SELL"},
        {"symbol": otm_pe, "side": "SELL"},
        {"symbol": atm_ce, "side": "BUY"},
        {"symbol": atm_pe, "side": "BUY"},
    ]

    success = True
    for order in orders:
        result = dhan.place_order(order["symbol"], order["side"])
        if not result:
            success = False
            print(f"Failed to place {order['side']} order for {order['symbol']}")
    
    return success

def exit_all_positions():
    dhan.exit_all_positions()
