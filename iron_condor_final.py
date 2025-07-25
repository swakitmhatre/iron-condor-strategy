import requests
import time
import datetime
import os
import json
import pandas as pd
from pathlib import Path

# === CONFIG ===
USER_ID = "FT053224"  # Replace with your Flattrade user ID
VC = "FA12345"       # Get from Flattrade (eg. "FA12345")
IMEI = "abc123"      # Unique string. You can generate a static one.
APP_KEY = "5a98658739d3414e85d55c51dc7b2646"
SECRET_KEY="2025.1d7850e257bb4858858073f31e5f7a9718f9062892b4aec5"
MARGIN_PER_LOT = 100000  # ₹1L approx per NIFTY Iron Condor
LOT_SIZE = 1
TOKEN_FILE = "token.txt"
SYMBOL_MASTER_CSV = "NFO_symbols.csv"
UNDERLYING = "NIFTY"

# === Logging ===
def log(msg):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")

# === Token Handling ===
def save_token(token):
    with open(TOKEN_FILE, "w") as f:
        json.dump({"token": token, "timestamp": time.time()}, f)

def load_token():
    if not Path(TOKEN_FILE).exists():
        return None
    with open(TOKEN_FILE, "r") as f:
        data = json.load(f)
    if time.time() - data["timestamp"] > 23 * 3600:  # 23 hrs validity
        return None
    return data["token"]

def generate_token():
    totp = input("Enter your Flattrade TOTP: ")
    url = "https://auth.flattrade.in/tradeplusLogin/authenticate"
    payload = {
        "user": USER_ID,
        "password": totp,
        "vc": VC,
        "app_key": APP_KEY,
        "imei": IMEI
    }
    try:
        res = requests.post(url, json=payload)
        res.raise_for_status()
        token = res.json().get("susertoken")
        if not token:
            raise Exception("Token generation failed.")
        save_token(token)
        return token
    except Exception as e:
        log(f"Token generation error: {e}")
        exit(1)

def get_token():
    token = load_token()
    if token:
        return token
    log("Token expired or missing. Generating new token.")
    return generate_token()

# === Symbol Master Download ===
def download_symbol_master():
    url = "https://api.flattrade.in/symbol_master/NFO_symbols.csv"
    try:
        res = requests.get(url)
        res.raise_for_status()
        with open(SYMBOL_MASTER_CSV, "wb") as f:
            f.write(res.content)
        log("Symbol master downloaded.")
    except Exception as e:
        log(f"Failed to download symbol master: {e}")
        exit(1)

# === ATM Strike Discovery ===
def get_strike_symbols():
    if not Path(SYMBOL_MASTER_CSV).exists():
        download_symbol_master()

    df = pd.read_csv(SYMBOL_MASTER_CSV)
    df = df[df['TradingSymbol'].str.startswith(UNDERLYING)]
    df = df[df['SymbolName'] == UNDERLYING]
    df = df[df['OptionType'].isin(['CE', 'PE'])]

    spot_price = get_live_price(get_token())
    atm_strike = round(spot_price / 50) * 50

    buy_ce_strike = atm_strike + 9 * 50
    buy_pe_strike = atm_strike - 9 * 50
    sell_ce_strike = atm_strike + 11 * 50
    sell_pe_strike = atm_strike - 11 * 50

    expiry = sorted(df['Expiry'].unique())[1]  # next week
    legs = {
        'BUY_CE': get_trading_symbol(df, buy_ce_strike, 'CE', expiry),
        'BUY_PE': get_trading_symbol(df, buy_pe_strike, 'PE', expiry),
        'SELL_CE': get_trading_symbol(df, sell_ce_strike, 'CE', expiry),
        'SELL_PE': get_trading_symbol(df, sell_pe_strike, 'PE', expiry),
    }

    log(f"Selected strikes: {legs}")
    return legs

def get_trading_symbol(df, strike, opt_type, expiry):
    row = df[(df['StrikePrice'] == strike) &
             (df['OptionType'] == opt_type) &
             (df['Expiry'] == expiry)]
    if row.empty:
        raise Exception(f"Symbol not found for {strike} {opt_type}")
    return row.iloc[0]['TradingSymbol']

# === Order Execution ===
def place_order(token, symbol, side, qty):
    url = "https://api.flattrade.in/trade/1.0.0/place_order"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "exchange": "NFO",
        "symbol": symbol,
        "action": side,
        "product": "M",
        "quantity": qty,
        "price": 0,
        "trigger_price": 0,
        "disclosed_quantity": 0,
        "validity": "DAY",
        "order_type": "MKT"
    }
    try:
        res = requests.post(url, json=payload, headers=headers)
        res.raise_for_status()
        log(f"Order placed: {side} {symbol}")
    except Exception as e:
        log(f"Order failed for {symbol}: {e}")

# === Live Price ===
def get_live_price(token):
    url = f"https://api.flattrade.in/order/1.0.0/quotes?symbols=NSE_INDEX|Nifty+50"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        res = requests.get(url, headers=headers)
        res.raise_for_status()
        return float(res.json()[0]['last_price'])
    except Exception as e:
        log(f"Price fetch failed: {e}")
        return 0

# === MTM PnL Check ===
def get_mtm(token):
    url = "https://api.flattrade.in/order/1.0.0/daywise_pnl"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        res = requests.get(url, headers=headers)
        res.raise_for_status()
        return float(res.json()['total_pnl'])
    except Exception as e:
        log(f"MTM fetch failed: {e}")
        return 0

# === Strategy Execution ===
def run_strategy():
    token = get_token()
    legs = get_strike_symbols()
    qty = LOT_SIZE * 50
    margin = MARGIN_PER_LOT * LOT_SIZE
    mtm_target = 0.0025 * margin

    log("Entering BUY legs first...")
    place_order(token, legs['BUY_CE'], "BUY", qty)
    place_order(token, legs['BUY_PE'], "BUY", qty)
    log("Waiting 2s before SELL legs...")
    time.sleep(2)

    log("Entering SELL legs...")
    place_order(token, legs['SELL_CE'], "SELL", qty)
    place_order(token, legs['SELL_PE'], "SELL", qty)
    entry_time = datetime.datetime.now()
    log(f"Entry complete at {entry_time.strftime('%H:%M:%S')}")

    log("Monitoring MTM...")
    while True:
        mtm = get_mtm(token)
        log(f"MTM: ₹{mtm:.2f}")
        if mtm >= mtm_target:
            log(f"MTM target hit: {mtm:.2f} >= {mtm_target:.2f}")
            log("Exiting SELL legs...")
            place_order(token, legs['SELL_CE'], "BUY", qty)
            place_order(token, legs['SELL_PE'], "BUY", qty)
            log("Exit complete.")
            break
        time.sleep(10)

# === Start ===
if __name__ == "__main__":
    run_strategy()
