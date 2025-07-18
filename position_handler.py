# position_handler.py

from utils import log_message

def place_iron_condor(dhan):
    spot = dhan.get_nifty_spot()
    log_message(f"NIFTY spot: {spot}")

    ce_sell = round(spot + 200, -1)
    ce_buy = ce_sell + 50
    pe_sell = round(spot - 200, -1)
    pe_buy = pe_sell - 50

    log_message(f"✔︎ Iron Condor legs: Sell CE@{ce_sell}, Buy CE@{ce_buy}; Sell PE@{pe_sell}, Buy PE@{pe_buy}")
    return True, {"legs": (ce_sell, ce_buy, pe_sell, pe_buy)}
