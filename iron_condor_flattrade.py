import base64
import requests
import json
import time
import datetime
import pyotp
import logging
import hashlib
from cryptography.fernet import Fernet
from datetime import datetime, timedelta

# ====== USER CONFIGURATION ======
API_KEY = "8a321b48cc3a48d2b3f4d52c4eb719be"
API_SECRET = "2025.c633e7fdb18949f391b4677ba9132e691f2d6c6dcd1ca276"
CLIENT_ID = "FT053224"
PASSWORD = "Swakit@123"
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
            print("saved token---->",data["token"])
            return data["token"]
    except:
        pass
    return get_new_token()

def generate_hash(api_key, request_token, api_secret):
    return hashlib.sha256(f"{api_key}{request_token}{api_secret}".encode()).hexdigest()
    
def get_new_token():
    print("1. Open the following URL in your browser and log in:")
    print(f"https://auth.flattrade.in/?app_key={API_KEY}")
    print("\n2. After login, copy the 'request_code' from the redirect URL.")
    request_code = input("Enter request_code: ").strip()
    hashed_secret = generate_hash(API_KEY, request_code, API_SECRET)
    payload = {
        "api_key": API_KEY,
        "request_code": request_code,
        "api_secret": hashed_secret
    }

    try:
        #print("payload---->",payload)
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
def get_live_price(jKey, uid, symbol_token="26000",exch="NSE"):
    """
    Fetches the live price for the given token using Flattrade GetQuotes API.
    token = instrument token (not auth token)
    uid = client code (e.g., FZ00000)
    jKey = session token from apitoken call
    symbol token for nifty 50 is--->26000,(https://flattrade.s3.ap-south-1.amazonaws.com/scripmaster/Nfo_Equity_Derivatives.csv)
    """
    try:
        jData = {
            "uid": uid,
            "exch": exch,
            "token": str(symbol_token)
        }
        jDataString=json.dumps(jData)
        payload = 'jData='+jDataString+'&jKey='+jKey;
        
        headers = {"Content-Type": "application/json"}
        #print("GetQuotes payload---->",payload)
        url = "https://piconnect.flattrade.in/PiConnectTP/GetQuotes"
        response = requests.post(url,data=payload)
        data = response.json()
        print("ltp json data--->",data)
        # The field may vary, but usually it's in data["lp"]
        live_price = float(data["lp"])
        return live_price

    except Exception as e:
        logging.error(f"Live price fetch failed: {e}")
        raise

def get_pnl(jkey):
    try:
        jData_dict = {
            "uid": "FT053224",
            "actid": "FT053224",
        }
        payload = f"jData={json.dumps(jData_dict)}&jKey={jkey}"

        headers = {
            "Content-Type": "application/json"
        }
        r = requests.post("https://piconnect.flattrade.in/PiConnectTP/Limits", data=payload,headers=headers)
        #return float(r.json()["uzpnl_d_i"])
        return float(r.json()["urmtom"])
    except Exception as e:
        logging.warning(f"PNL fetch failed: {e}")
        return 0.0

def get_rpnl(jkey):
    try:
        jData_dict = {
            "uid": "FT053224",
            "actid": "FT053224",
        }
        payload = f"jData={json.dumps(jData_dict)}&jKey={jkey}"

        headers = {
            "Content-Type": "application/json"
        }
        r = requests.post("https://piconnect.flattrade.in/PiConnectTP/Limits", data=payload,headers=headers)
        print("in rpnl()",r.json())
        #return float(r.json()["uzpnl_d_i"])
        return float(r.json()["rpnl"])
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

def place_order(jkey, symbol, qty, SIDE):
    try:
        jData_dict = {
            "uid": "FT053224",
            "actid": "FT053224",
            "exch": "NFO",
            "tsym": str(symbol),
            "qty": str(qty),
            "prc": "0",
            "prd": "I",
            "trantype": SIDE,
            "prctyp": "MKT",
            "ret": "DAY"
        }
        payload = f"jData={json.dumps(jData_dict)}&jKey={jkey}"

        headers = {
            "Content-Type": "application/json"
        }
        print("order paylod---->",payload)
        
        #r = requests.post("https://piconnect.flattrade.in/PiConnectTP/PlaceOrder", headers={"Authorization": f"Bearer {token}"}, json=payload)
        r = requests.post("https://piconnect.flattrade.in/PiConnectTP/PlaceOrder", data=payload,headers=headers)
        print("Order API raw response:", r.text)
        res = r.json()
        logging.info(f"{SIDE} {symbol}: {res}")
    except Exception as e:
        logging.error(f"Order failed: {e}")

def find_atm_strikes(price):
    atm = round(price / 50) * 50
    return atm - 550, atm - 450, atm + 450, atm + 550

def get_symbol(expiry, strike, opt_type):
    try:
        trading_symbol=UNDERLYING+expiry+opt_type+str(strike)
        #Print("UNDERLYING----->",trading_symbol)
        with open(SYMBOL_FILE) as f:
            for line in f:
                #if f"{UNDERLYING}{expiry}" in line and f"{strike}" in line  and "C" in line or "P" in line:
                if f"{trading_symbol}" in line:
                    #print("option--->",line)
                    return line.split(",")[4]
    except Exception as e:
        logging.error(f"Symbol lookup failed: {e}")
    return None
    
def get_next_weekly_expiry():
    today = datetime.now().date()
    weekday = today.weekday()  # Monday=0, Tuesday=1, ..., Sunday=6

    # Tuesday = weekday=1
    days_to_tuesday = (1 - weekday) % 7
    if days_to_tuesday == 0:
        # today is Tuesday, so skip to *next* Tuesday
        days_to_tuesday = 7

    # Get this week's Tuesday
    this_tuesday = today + timedelta(days=days_to_tuesday)

    # Next week's Tuesday = this week's Tuesday + 7 days
    next_tuesday = this_tuesday + timedelta(days=7)

    expiry_str = next_tuesday.strftime("%d%b%y").upper()  # format like 25OCT14
    return next_tuesday, expiry_str

def run_strategy():
    download_symbol_master()
    token = get_token()
    #HERE TOKEN IS LOGIN_TOKEN I.E JKey ,NOT SYMBOL TOKEN.
    live_price = get_live_price(token,CLIENT_ID)
    #margin = get_margin(token)
    margin = 100000
    #mtm_target = margin * MTM_PERCENT
    mtm_target=35
    lot_size = 75 * LOT_MULTIPLIER

    #expiry = datetime.datetime.now().strftime("%y%b%d").upper()
    expiry_date, expiry = get_next_weekly_expiry()
    print("expiry--->",expiry)
    strikes = find_atm_strikes(live_price)
    print("strikes------>",strikes)

    symbols = {
        "buy_pe": get_symbol(expiry, strikes[0], "P"),
        "sell_pe": get_symbol(expiry, strikes[1], "P"),
        "sell_ce": get_symbol(expiry, strikes[2], "C"),
        "buy_ce": get_symbol(expiry, strikes[3], "C")
    }

    logging.info(f"Selected symbols: {symbols}")
    rpnl=get_rpnl(token)
    # Entry - Buy first
    jkey=token
    entry_start = time.perf_counter()
    place_order(jkey, symbols["buy_pe"], lot_size, "B")
    place_order(jkey, symbols["buy_ce"], lot_size, "B")
    place_order(jkey, symbols["sell_pe"], lot_size, "S")
    place_order(jkey, symbols["sell_ce"], lot_size, "S")

    entry_delay = round(time.perf_counter() - entry_start, 3)
    entry_time = datetime.now()
    logging.info(f"✅ ENTRY COMPLETE | Time = {entry_time} | Delay = {entry_delay}s")
    logging.info("Iron Condor entered. Monitoring MTM...")

    while True:
        pnl = get_pnl(token)
        pnl= pnl-rpnl
        logging.info(f"📈 MTM = ₹{pnl:.2f}  rpnl = ₹{rpnl:.2f}")
        if pnl <= -mtm_target or pnl >= mtm_target :
            condition_met_time = datetime.now()
            logging.info(f"🎯 TARGET HIT at {condition_met_time}")
            # Exit - Sell legs first
            place_order(jkey, symbols["sell_pe"], lot_size, "B")
            place_order(jkey, symbols["sell_ce"], lot_size, "B")
            time.sleep(0.01)
            place_order(jkey, symbols["buy_pe"], lot_size, "S")
            place_order(jkey, symbols["buy_ce"], lot_size, "S")
            exit_time = datetime.now()
            logging.info(f"🏁 Strategy Exit Time = {exit_time}")
            logging.info("✅ All legs exited. Strategy complete.\n")
            logging.info(f"MTM target hit. Exiting... PnL: {pnl}")
            break
        time.sleep(0.10)

    
if __name__ == "__main__":
    run_strategy()
