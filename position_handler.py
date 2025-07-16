# position_handler.py

from dhan import Dhan
from utils import get_strike_prices, log_message
import time

def place_iron_condor(dhan):
    # Example logic — replace with actual logic if needed
    ce_strike, pe_strike, hedge_ce, hedge_pe = get_strike_prices()

    positions = []

    # BUY hedge legs first
    hedge_ce_order = dhan.place_order(symbol="NIFTY", strike=hedge_ce, side="BUY")
    hedge_pe_order = dhan.place_order(symbol="NIFTY", strike=hedge_pe, side="BUY")

    positions.extend([hedge_ce_order, hedge_pe_order])
    time.sleep(1)

    # SELL main legs
    ce_order = dhan.place_order(symbol="NIFTY", strike=ce_strike, side="SELL")
    pe_order = dhan.place_order(symbol="NIFTY", strike=pe_strike, side="SELL")

    positions.extend([ce_order, pe_order])

    log_message(f"Orders placed: {[p['id'] for p in positions]}")
    return True, positions

def exit_all_positions(dhan, positions):
    for p in positions:
        opposite_side = "SELL" if p["side"] == "BUY" else "BUY"
        dhan.place_order(symbol=p["symbol"], strike=p["strike"], side=opposite_side)
        log_message(f"Exited: {p['symbol']} {p['strike']} {opposite_side}")
        time.sleep(1)
