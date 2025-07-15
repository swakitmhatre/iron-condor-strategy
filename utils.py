# utils.py

import datetime

def get_next_thursday():
    today = datetime.date.today()
    days_ahead = 3 - today.weekday()  # Thursday is 3
    if days_ahead <= 0:
        days_ahead += 7
    next_thursday = today + datetime.timedelta(days=days_ahead)
    return next_thursday.strftime('%d%b%Y').upper()  # Format: 18JUL2024

def get_strike_prices():
    """
    Returns ATM_CE, ATM_PE, OTM_CE, OTM_PE symbols based on dummy ATM logic (e.g., 24000).
    Replace with dynamic ATM calculation logic if needed.
    """
    expiry = get_next_thursday()
    atm_strike = 24000  # replace with live spot price rounded to nearest 100

    otm_ce = f"NIFTY{expiry}24500CE"
    otm_pe = f"NIFTY{expiry}23500PE"
    atm_ce = f"NIFTY{expiry}{atm_strike}CE"
    atm_pe = f"NIFTY{expiry}{atm_strike}PE"

    return atm_ce, atm_pe, otm_ce, otm_pe
