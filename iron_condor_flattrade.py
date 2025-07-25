import requests
import time
import json
import os
from datetime import datetime, timedelta
import pytz

# CONFIGURATION
FLATTRADE_CLIENT_CODE = "FT053224"  # Replace with your client code
FLATTRADE_API_KEY = "5a98658739d3414e85d55c51dc7b2646"
FLATTRADE_API_SECRET = "2025.1d7850e257bb4858858073f31e5f7a9718f9062892b4aec5"
FLATTRADE_TOTP = "123456"  # Replace with your TOTP
TOKEN_FILE = "token.txt"
MULTIPLIER = 1  # Lot multiplier (1 lot = 50 qty for NIFTY)
MTM_PERCENT = 0.0025  # 0.25% of margin
LOG_FILE = "iron_condor_log.txt"

# CONSTANTS
HEADERS = {"Content-Type": "application/json"}
IST = pytz.timezone("Asia/Kolkata")

# --- Helper Functions ---
def log(msg):
    with open(LOG_FILE, "a") as f:
        f.write(f"[{datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    print(msg)

def save_token(token):
    with open(TOKEN_FILE, "w") as f:
        json.dump(token, f)

def load_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    return None

def is_token_valid(token):
    return token and 'access_token' in token and time.time() < token.get("expiry", 0)

def generate_token():
    url = "https://authapi.flattrade.in/trade/apitoken"
    payload = {
        "app_key": FLATTRADE_API_KEY,
        "app_secret": FLATTRADE_API_SECRET,
        "client_code": FLATTRADE_CLIENT_CODE,
        "totp": FLATTRADE_TOTP
    }
    response = requests.post(url, json=payload)
    data = response.json()
    if 'token' in data:
        token_data = {
            "access_token": data['token'],
            "expiry": time.time() + 36000  # 1 hour expiry
        }
        save_token(token_data)
        return token_data
    else:
        raise Exception("Token generation failed: " + str(data))

def get_token():
    token = load_token()
    if not is_token_valid(token):
        log("Token expired or missing. Generating new token.")
        token = generate_token()
    return token['access_token']

# --- Strategy Core ---
def get_live_price(token):
    url = f"https://api.flattrade.in/quotes/ltp/NSE/NIFTY"
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(url, headers=headers)
    return float(res.json()['last_price'])

def get_option_symbol(expiry: str, strike: int, opt_type: str):
    return f"NIFTY{expiry}{strike:05}{opt_type}"

def get_next_week_expiry():
    today = datetime.now(IST)
    next_thursday = today + timedelta((3 - today.weekday()) % 7 + 7)
    return next_thursday.strftime("%d%b%y").upper()

def place_order(token, symbol, side, qty):
    url = "https://api.flattrade.in/trade/placeorder"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "exchange": "NSE",
        "symbol": symbol,
        "quantity": qty,
        "price": 0,
        "product": "MIS",
        "transaction_type": side,
        "order_type": "MKT",
        "validity": "DAY"
    }
    res = requests.post(url, json=payload, headers=headers)
    return res.json()

def calculate_margin():
    return 135000 * MULTIPLIER

def get_pnl(token):
    url = "https://api.flattrade.in/trade/book/position"
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get(url, headers=headers)
    data = res.json()
    return sum(float(p['unrealized_pnl']) + float(p['realized_pnl']) for p in data)

# --- Main Strategy ---
def run_strategy():
    token = get_token()
    expiry = get_next_week_expiry()
    live_price = get_live_price(token)
    atm = round(live_price / 50) * 50
    buy_ce_strike = atm + 9 * 50
    buy_pe_strike = atm - 9 * 50
    sell_ce_strike = atm + 11 * 50
    sell_pe_strike = atm - 11 * 50
    qty = 50 * MULTIPLIER

    buy_ce = get_option_symbol(expiry, buy_ce_strike, "CE")
    buy_pe = get_option_symbol(expiry, buy_pe_strike, "PE")
    sell_ce = get_option_symbol(expiry, sell_ce_strike, "CE")
    sell_pe = get_option_symbol(expiry, sell_pe_strike, "PE")

    log("Placing Buy legs first")
    place_order(token, buy_ce, "BUY", qty)
    place_order(token, buy_pe, "BUY", qty)

    time.sleep(1)
    log("Placing Sell legs")
    place_order(token, sell_ce, "SELL", qty)
    place_order(token, sell_pe, "SELL", qty)

    entry_time = datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')
    log(f"ENTRY_TIME: {entry_time}")

    mtm_target = calculate_margin() * MTM_PERCENT
    log(f"Target P&L: ₹{mtm_target:.2f}")

    # --- Monitor MTM ---
    while True:
        pnl = get_pnl(token)
        log(f"Current P&L: ₹{pnl:.2f}")
        if pnl >= mtm_target:
            log("MTM Target Hit. Exiting SELL legs.")
            place_order(token, sell_ce, "BUY", qty)
            place_order(token, sell_pe, "BUY", qty)
            exit_time = datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')
            log(f"EXIT_TIME: {exit_time}")
            break
        time.sleep(0.5)

if __name__ == "__main__":
    run_strategy()
