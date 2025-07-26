import base64
import requests
import json
import time
import datetime
import pyotp
import logging
from cryptography.fernet import Fernet

# ====== USER CONFIGURATION ======
API_KEY = "5a98658739d3414e85d55c51dc7b2646"
API_SECRET = "2025.1d7850e257bb4858858073f31e5f7a9718f9062892b4aec5"
CLIENT_ID = "FT053224"
PASSWORD = "Mona@1969"
VC = "your_vc"           # example: "FA12345"
IMEI = "your_imei"       # example: "abc123xyz"
LOT_MULTIPLIER = 1
MTM_PERCENT = 0.0025     # 0.25%
UNDERLYING = "NIFTY"
# =================================

# === ENCRYPTED TOTP SECRET AND FERNET KEY ===
FERNET_KEY = b'9dabT3qDS1z0VBJYirSKtYQs01X3ClxEOcTmLvOJCTE='  # keep it as bytes
ENCRYPTED_TOTP = b'gAAAAABohKY2BTkTaljdVg110nPlCyBFoTrHQh9lXccZL9l5S2DNgKHyrEx4k-xhsLsV3lYb8Rcax40txOz7_g_R46UQ-wNNu5X5bStijNwauA9qztfmByC3lDqOZpDisync-ah3MfQK'  # bytes
# Use Fernet.generate_key() once, and encrypt your 16-digit base32 TOTP using that key.
# ============================================

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
TOKEN_FILE = "token.txt"
SYMBOL_FILE = "symbol_master.csv"

def decrypt_totp():
    fernet = Fernet(FERNET_KEY)
    return fernet.decrypt(ENCRYPTED_TOTP).decode()

def download_symbol_master():
    try:
        url = "https://flattrade.s3.ap-south-1.amazonaws.com/scripmaster/Nfo_Index_Derivatives.csv"
        r = requests.get(url)
        with open(SYMBOL_FILE, "wb") as f:
            f.write(r.content)
        logging.info("Symbol master downloaded.")
    except Exception as e:
        logging.error(f"Failed to download symbol master: {e}")

def get_token():
    try:
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)
        if time.time() - data["timestamp"] < 23 * 3600:
            return data["token"]
    except:
        pass
    return get_new_token()
'''
def get_new_token():
    totp_secret = decrypt_totp()
    otp = pyotp.TOTP(totp_secret).now()
    print("otp------>",otp)
    # Step 1: Get request_code
    session_payload = {
        "api_key": API_KEY,
        "client_code": CLIENT_ID,
        "password": PASSWORD,
        "totp": otp
    }

    try:
        session_resp = requests.post("https://authapi.flattrade.in/trade/session", json=session_payload)
        session_data = session_resp.json()

        request_code = session_data.get("request_code")
        if not request_code:
            raise Exception(f"Failed to get request_code: {session_data}")

        # Step 2: Get token using request_code
        token_payload = {
            "api_key": API_KEY,
            "request_code": request_code,
            "vc": VC,
            "imei": IMEI
        }

        token_resp = requests.post("https://authapi.flattrade.in/trade/apitoken", json=token_payload)
        token_data = token_resp.json()
        print("token_data---->",token_data)

        token = token_data.get("token")
        if token:
            with open(TOKEN_FILE, "w") as f:
                json.dump({"token": token, "timestamp": time.time()}, f)
            logging.info("New token generated.")
            return token
        else:
            raise Exception(f"Token generation failed: {token_data}")

    except Exception as e:
        logging.error(f"Token error: {e}")
        raise
'''
def get_new_token():
    print("1. Open the following URL in your browser and log in:")
    print(f"https://auth.flattrade.in/?app_key={API_KEY}")
    print("\n2. After login, copy the 'request_code' from the redirect URL.")
    request_code = input("Enter request_code: ").strip()

    payload = {
        "api_key": API_KEY,
        "request_code": request_code,
        "api_secret": API_SECRET
    }

    try:
        print("payload---->",payload)
        r = requests.post("https://authapi.flattrade.in/trade/apitoken", json=payload)
        r.raise_for_status()
        res = r.json()
        token = res.get("token")
        if token:
            with open(TOKEN_FILE, "w") as f:
                json.dump({"token": token, "timestamp": time.time()}, f)
            logging.info("✅ New token generated and saved.")
            return token
        else:
            raise Exception(f"❌ Token generation failed: {res}")
    except Exception as e:
        logging.error(f"Token error: {e}")
        raise
        
#incorret function argument mismatch        
def get_live_price(jKey, uid, exch="NSE", token="22"):
    """
    Fetches the live price for the given token using Flattrade GetQuotes API.
    token = instrument token (not auth token)
    uid = client code (e.g., FZ00000)
    jKey = session token from apitoken call
    """
    try:
        jData = {
            "uid": uid,
            "exch": exch,
            "token": token
        }

        payload = {
            "jData": json.dumps(jData),
            "jKey": jKey
        }

        url = "https://piconnect.flattrade.in/PiConnectTP/GetQuotes"
        response = requests.post(url, data=payload)
        data = response.json()

        # The field may vary, but usually it's in data["lp"]
        live_price = float(data["lp"])
        return live_price

    except Exception as e:
        logging.error(f"Live price fetch failed: {e}")
        raise

def get_pnl(token):
    try:
        r = requests.get("https://api.flattrade.in/trade/pnl", headers={"Authorization": f"Bearer {token}"})
        return float(r.json()["net_pnl"])
    except Exception as e:
        logging.warning(f"PNL fetch failed: {e}")
        return 0.0

def get_margin(token):
    try:
        r = requests.get("https://api.flattrade.in/trade/margin", headers={"Authorization": f"Bearer {token}"})
        return float(r.json()["total_margin"])
    except Exception as e:
        logging.warning(f"Margin fetch failed: {e}")
        return 150000  # fallback default

def place_order(token, symbol, qty, side):
    order = {
        "exchange": "NFO",
        "symbol": symbol,
        "quantity": qty,
        "order_type": "MARKET",
        "product": "M",
        "transaction_type": side,
        "validity": "DAY"
    }
    try:
        r = requests.post("https://api.flattrade.in/trade/placeOrder", headers={"Authorization": f"Bearer {token}"}, json=order)
        res = r.json()
        logging.info(f"{side} {symbol}: {res}")
    except Exception as e:
        logging.error(f"Order failed: {e}")

def find_atm_strikes(price):
    atm = round(price / 50) * 50
    return atm - 300, atm - 100, atm + 100, atm + 300

def get_symbol(expiry, strike, opt_type):
    try:
        with open(SYMBOL_FILE) as f:
            for line in f:
                if f"{UNDERLYING}{expiry}" in line and f"{strike}" in line and opt_type in line and "CE" in line or "PE" in line:
                    return line.split(",")[0]
    except Exception as e:
        logging.error(f"Symbol lookup failed: {e}")
    return None

def run_strategy():
    download_symbol_master()
    token = get_token()
    live_price = get_live_price(token)
    margin = get_margin(token)
    mtm_target = margin * MTM_PERCENT
    lot_size = 50 * LOT_MULTIPLIER

    expiry = datetime.datetime.now().strftime("%y%b").upper()
    strikes = find_atm_strikes(live_price)

    symbols = {
        "buy_pe": get_symbol(expiry, strikes[0], "PE"),
        "sell_pe": get_symbol(expiry, strikes[1], "PE"),
        "sell_ce": get_symbol(expiry, strikes[2], "CE"),
        "buy_ce": get_symbol(expiry, strikes[3], "CE")
    }

    logging.info(f"Selected symbols: {symbols}")

    # Entry - Buy first
    place_order(token, symbols["buy_pe"], lot_size, "BUY")
    place_order(token, symbols["buy_ce"], lot_size, "BUY")
    place_order(token, symbols["sell_pe"], lot_size, "SELL")
    place_order(token, symbols["sell_ce"], lot_size, "SELL")

    logging.info("Iron Condor entered. Monitoring MTM...")

    while True:
        pnl = get_pnl(token)
        if pnl <= -mtm_target:
            logging.info(f"MTM target hit. Exiting... PnL: {pnl}")
            break
        time.sleep(10)

    # Exit - Sell legs first
    place_order(token, symbols["sell_pe"], lot_size, "BUY")
    place_order(token, symbols["sell_ce"], lot_size, "BUY")
    place_order(token, symbols["buy_pe"], lot_size, "SELL")
    place_order(token, symbols["buy_ce"], lot_size, "SELL")
    logging.info("All legs exited.")

if __name__ == "__main__":
    run_strategy()
