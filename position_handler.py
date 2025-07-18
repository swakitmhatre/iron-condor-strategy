# position_handler.py

from utils import log_message

def place_iron_condor(dhan):
    try:
        spot = dhan.get_nifty_spot()
        log_message(f"NIFTY spot price: {spot}")

        # MOCK entry: Replace this section with live order placement using dhan.place_order()
        ce_sell = round(spot + 200, -1)
        ce_buy = ce_sell + 50
        pe_sell = round(spot - 200, -1)
        pe_buy = pe_sell - 50

        log_message(f"Placing Iron Condor: PE {pe_buy}-{pe_sell}, CE {ce_sell}-{ce_buy}")
        return True, {
            "ce_sell": ce_sell, "ce_buy": ce_buy,
            "pe_sell": pe_sell, "pe_buy": pe_buy
        }

    except Exception as e:
        raise Exception(f"Place Iron Condor failed: {e}")
