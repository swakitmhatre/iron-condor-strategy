import requests
import time
import json
import hmac
import hashlib
import base64
import os
import csv
import logging
from datetime import datetime, timedelta
import pyotp
import pandas as pd

# ----------------- USER CONFIGURATION ------------------
API_KEY = "5a98658739d3414e85d55c51dc7b2646"
API_SECRET = "2025.1d7850e257bb4858858073f31e5f7a9718f9062892b4aec5"
CLIENT_CODE = "FT053224"
PASSWORD = "Mona@1969"
VC = "your_vc"
IMEI = "your_imei"
TOTP_SECRET = "your_totp_secret"
MULTIPLIER = 1  # Number of lots
TOKEN_FILE = "token.txt"
SYMBOL_MASTER_URL = "https://api.flattrade.in/api/market/symbolmaster"
SYMBOL_MASTER_FILE = "symbol_master.csv"
UNDERLYING = "NIFTY"
MTM_TARGET_PERCENT = 0.25
LOG_FILE = "iron_condor_log.txt"

# ----------------- LOGGER SETUP ------------------
logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# ----------------- AUTH & TOKEN MGMT ------------------
def generate_token():
    try:
        totp = pyotp.TOTP(TOTP_SECRET).now()
        payload = {
            "api_key": API_KEY,
            "secret_key": API_SECRET,
            "client_code": CLIENT_CODE,
            "password": PASSWORD,
            "totp": totp,
            "vc": VC,
            "imei": IMEI
        }
        res = requests.post("https://authapi.flattrade.in/trade/apitoken", json=payload)
        res_data = res.json()
        token = res_data.get("token")
        if token:
            with open(TOKEN_FILE, 'w') as f:
                json.dump({"token": token, "timestamp": time.time()}, f)
            return token
        else:
            raise Exception(f"Token generation failed: {res_data}")
    except Exception as e:
        logging.error(f"Token generation error: {str(e)}")
        raise

def get_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'r') as f:
            data = json.load(f)
            if time.time() - data['timestamp'] < 86400:
                return data['token']
    logging.info("Token expired or missing. Generating new token.")
    return generate_token()

# ----------------- SYMBOL MASTER & ATM ------------------
def download_symbol_master():
    try:
        r = requests.get(SYMBOL_MASTER_URL)
        with open(SYMBOL_MASTER_FILE, 'wb') as f:
            f.write(r.content)
    except Exception as e:
        logging.error(f"Failed to download symbol master: {e}")
        raise

def get_option_symbols():
    try:
        if not os.path.exists(SYMBOL_MASTER_FILE):
            download_symbol_master()

        df = pd.read_csv(SYMBOL_MASTER_FILE)
        df = df[df['Exchange'] == 'NFO']
        nifty_data = df[df['TradingSymbol'].str.contains(UNDERLYING)]

        atm_price = get_live_price(get_token())
        atm_strike = round(atm_price / 50) * 50

        expiry = sorted(set(nifty_data['Expiry']))[1]  # next week expiry

        strikes = {
            "CE_BUY": atm_strike + 450,
            "PE_BUY": atm_strike - 450,
            "CE_SELL": atm_strike + 550,
            "PE_SELL": atm_strike - 550
        }

        symbols = {}
        for leg, strike in strikes.items():
            opttype = "CE" if "CE" in leg else "PE"
            row = nifty_data[(nifty_data['StrikePrice'] == strike) &
                             (nifty_data['OptionType'] == opttype) &
                             (nifty_data['Expiry'] == expiry)]
            if not row.empty:
                symbols[leg] = row.iloc[0]['TradingSymbol']

        return symbols
    except Exception as e:
        logging.error(f"Error in get_option_symbols: {e}")
        raise

# ----------------- PRICE, MARGIN, MTM ------------------
def get_live_price(token):
    try:
        url = f"https://api.flattrade.in/quotes/live?symbols=NSE:{UNDERLYING}-EQ"
        headers = {"Authorization": f"Bearer {token}"}
        res = requests.get(url, headers=headers)
        return float(res.json()[0]['last_price'])
    except Exception as e:
        logging.error(f"Failed to fetch live price: {e}")
        raise

def get_mtm(token):
    try:
        url = "https://api.flattrade.in/trade/pnl"
        headers = {"Authorization": f"Bearer {token}"}
        res = requests.get(url, headers=headers)
        data = res.json()
        return float(data.get("net_m2m", 0))
    except Exception as e:
        logging.error(f"Failed to fetch MTM: {e}")
        return 0

def get_margin():
    base_margin = 150000  # for 1 lot, approx
    return base_margin * MULTIPLIER

def log_event(message):
    print(message)
    logging.info(message)

# ----------------- ORDER MGMT ------------------
def place_order(token, symbol, qty, side):
    try:
        url = "https://api.flattrade.in/trade/placeOrder"
        headers = {"Authorization": f"Bearer {token}"}
        data = {
            "exchange": "NFO",
            "symbol": symbol,
            "quantity": qty,
            "price": 0,
            "trigger_price": 0,
            "disclosed_quantity": 0,
            "transaction_type": side,
            "order_type": "MARKET",
            "product": "M",
            "validity": "DAY"
        }
        res = requests.post(url, headers=headers, json=data)
        res.raise_for_status()
        log_event(f"Order Placed: {side} {symbol} {qty} @ Market")
    except Exception as e:
        logging.error(f"Order failed for {symbol}: {e}")

# ----------------- STRATEGY ------------------
def run_strategy():
    token = get_token()
    symbols = get_option_symbols()
    qty = 50 * MULTIPLIER

    # ENTRY
    place_order(token, symbols['CE_BUY'], qty, "BUY")
    place_order(token, symbols['PE_BUY'], qty, "BUY")
    time.sleep(1)
    place_order(token, symbols['CE_SELL'], qty, "SELL")
    place_order(token, symbols['PE_SELL'], qty, "SELL")
    entry_time = datetime.now()
    log_event(f"Entry completed at {entry_time}")

    # TRACKING
    margin = get_margin()
    target_mtm = MTM_TARGET_PERCENT / 100 * margin
    log_event(f"Tracking for MTM Target: {target_mtm:.2f}")

    while True:
        mtm = get_mtm(token)
        log_event(f"Live MTM: {mtm:.2f}")
        if mtm >= target_mtm:
            condition_time = datetime.now()
            log_event(f"MTM target hit at {condition_time}")

            place_order(token, symbols['CE_SELL'], qty, "BUY")
            place_order(token, symbols['PE_SELL'], qty, "BUY")
            time.sleep(1)
            place_order(token, symbols['CE_BUY'], qty, "SELL")
            place_order(token, symbols['PE_BUY'], qty, "SELL")

            exit_time = datetime.now()
            log_event(f"Exited all legs at {exit_time}")
            break
        time.sleep(5)

# ----------------- MAIN ------------------
if __name__ == "__main__":
    try:
        run_strategy()
    except Exception as e:
        logging.error(f"Strategy failed: {e}")
        print(f"Strategy encountered an error: {e}")
