import requests
import json
import time
import datetime
import pytz
import os
import pyotp
import csv
from pprint import pprint

# ====== CONFIGURATION ======
API_KEY = "5a98658739d3414e85d55c51dc7b2646"
API_SECRET = "2025.1d7850e257bb4858858073f31e5f7a9718f9062892b4aec5"
CLIENT_CODE = "FT053224"
VC = "your_virtual_code"
IMEI = "your_imei_number"
TOTP_SECRET = input("Enter TOTP secret (shown in authenticator app): ").strip()

LOT_MULTIPLIER = 1
TOKEN_FILE = "token.txt"
SYMBOL_MASTER_FILE = "symbol_master.csv"
UNDERLYING = "NIFTY"
MARGIN_PER_LOT = 85000  # Example; update with actual margin from broker

# ====== LOGGER ======
def log(msg):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")
    with open("strategy_log.txt", "a") as f:
        f.write(f"[{timestamp}] {msg}\n")

# ====== TOKEN HANDLER ======
def save_token(token):
    with open(TOKEN_FILE, "w") as f:
        json.dump({"token": token, "timestamp": time.time()}, f)

def load_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)
            if time.time() - data.get("timestamp", 0) < 23 * 3600:
                return data["token"]
    return None

def get_new_token():
    otp = pyotp.TOTP(TOTP_SECRET).now()
    payload = {
        "apkversion": "1.0.0",
        "uid": CLIENT_CODE,
        "pwd": API_SECRET,
        "factor2": otp,
        "vc": VC,
        "appkey": API_KEY,
        "imei": IMEI
    }
    headers = {"Content-Type": "application/json"}
    try:
        res = requests.post("https://authapi.flattrade.in/trade/apitoken", json=payload, headers=headers)
        res_data = res.json()
        if res_data.get("stat") == "Ok":
            token = res_data["susertoken"]
            save_token(token)
            return token
        else:
            log(f"Token generation failed: {res_data}")
    except Exception as e:
        log(f"Token request exception: {e}")
    return None

def get_token():
    token = load_token()
    if token:
        log("Using cached token.")
        return token
    log("Token expired or missing. Generating new token...")
    return get_new_token()

# ====== SYMBOL MASTER HANDLER ======
def download_symbol_master():
    try:
        url = "https://api.flattrade.in/api/market/symbol-master-csv"
        r = requests.get(url)
        with open(SYMBOL_MASTER_FILE, "wb") as f:
            f.write(r.content)
        log("Symbol master downloaded.")
    except Exception as e:
        log(f"Error downloading symbol master: {e}")

def get_option_symbol(strike, option_type, expiry):
    with open(SYMBOL_MASTER_FILE, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            if (
                row["TradingSymbol"].startswith("NFO:NIFTY") and
                row["Expiry"].startswith(expiry) and
                row["StrikePrice"] == str(strike) and
                row["OptionType"] == option_type
            ):
                return row["TradingSymbol"]
    return None

# ====== PRICE & PNL ======
def get_ltp(token, symbol):
    url = "https://api.flattrade.in/market/quote"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"symbols": symbol}
    try:
        res = requests.get(url, headers=headers, params=params)
        data = res.json()[0]
        return float(data["last_price"])
    except Exception as e:
        log(f"Failed to get LTP for {symbol}: {e}")
        return 0.0

def get_atm_strike(token):
    url = "https://api.flattrade.in/market/quote"
    headers = {"Authorization": f"Bearer {token}"}
    params = {"symbols": "NSE:NIFTY50"}
    try:
        res = requests.get(url, headers=headers, params=params)
        price = float(res.json()[0]["last_price"])
        return round(price / 50) * 50
    except Exception as e:
        log(f"ATM fetch failed: {e}")
        return 0

def get_pnl(token):
    url = "https://api.flattrade.in/trade/pnl"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        res = requests.get(url, headers=headers)
        data = res.json()
        return float(data.get("total_pnl", 0))
    except Exception as e:
        log(f"PNL fetch error: {e}")
        return 0

# ====== ORDER EXECUTION ======
def place_order(token, symbol, side, qty):
    url = "https://api.flattrade.in/trade/placeorder"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "exchange": "NFO",
        "symbol": symbol,
        "qty": qty,
        "type": "MKT",
        "side": side,
        "product": "M",
        "validity": "DAY"
    }
    try:
        res = requests.post(url, headers=headers, json=payload)
        data = res.json()
        if data.get("stat") == "Ok":
            log(f"Order placed: {side} {symbol} x{qty}")
        else:
            log(f"Order failed: {data}")
    except Exception as e:
        log(f"Order exception: {e}")

# ====== STRATEGY RUNNER ======
def run_strategy():
    download_symbol_master()
    token = get_token()
    if not token:
        log("Aborting. Token fetch failed.")
        return

    atm = get_atm_strike(token)
    expiry = (datetime.date.today() + datetime.timedelta(days=(7 - datetime.date.today().weekday()) + 1)).strftime("%Y-%m-%d")

    buy_ce_strike = atm + 450
    buy_pe_strike = atm - 450
    sell_ce_strike = atm + 550
    sell_pe_strike = atm - 550

    buy_ce = get_option_symbol(buy_ce_strike, "CE", expiry)
    buy_pe = get_option_symbol(buy_pe_strike, "PE", expiry)
    sell_ce = get_option_symbol(sell_ce_strike, "CE", expiry)
    sell_pe = get_option_symbol(sell_pe_strike, "PE", expiry)

    qty = 50 * LOT_MULTIPLIER

    log("Placing BUY legs first...")
    place_order(token, buy_ce, "BUY", qty)
    place_order(token, buy_pe, "BUY", qty)
    log("Condition met. Placing SELL legs...")
    place_order(token, sell_ce, "SELL", qty)
    place_order(token, sell_pe, "SELL", qty)

    log("Iron Condor Entry Completed.")

    entry_time = datetime.datetime.now()
    mtm_target = MARGIN_PER_LOT * 0.0025 * LOT_MULTIPLIER
    log(f"MTM Target: {mtm_target}")

    # ===== MONITORING =====
    while True:
        pnl = get_pnl(token)
        log(f"Live PnL: {pnl}")
        if pnl >= mtm_target:
            log("MTM Target hit. Exiting sell legs...")
            place_order(token, sell_ce, "BUY", qty)
            place_order(token, sell_pe, "BUY", qty)
            log("Sell legs exited. Exiting buy legs...")
            place_order(token, buy_ce, "SELL", qty)
            place_order(token, buy_pe, "SELL", qty)
            log("Strategy exited.")
            break
        time.sleep(10)

# ====== MAIN ======
if __name__ == "__main__":
    run_strategy()
