# instruments.py
# instruments.py

from datetime import datetime, timedelta

def get_next_week_expiry():
    today = datetime.today()
    weekday = today.weekday()
    days_until_thursday = (3 - weekday + 7) % 7
    next_expiry = today + timedelta(days=days_until_thursday + 7)
    return next_expiry.strftime('%d%b%Y').upper()

def get_nifty_spot():
    return 22200  # placeholder or fetch live from API

def get_nifty_option_symbol(strike, option_type, expiry):
    return f"NIFTY{expiry}{strike}{option_type}"

'''from datetime import datetime, timedelta

def get_next_week_expiry():
    today = datetime.now()
    weekday = today.weekday()

    # Thursday = 3
    days_until_thursday = (3 - weekday) % 7
    if days_until_thursday == 0:
        days_until_thursday = 7  # move to next week's expiry

    next_thursday = today + timedelta(days=days_until_thursday)
    return next_thursday.strftime("%d%b%Y").upper()  # e.g., 18JUL2024

def get_nifty_option_symbol(expiry_str, strike_price, option_type):
    """
    expiry_str: in format '18JUL2024'
    strike_price: e.g. 22200
    option_type: 'CE' or 'PE'
    """
    return f"NIFTY{expiry_str}{strike_price}{option_type}"
    '''
