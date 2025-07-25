import requests, json, time, csv, os, pyotp, base64
from datetime import datetime
from cryptography.fernet import Fernet

# -------------------- USER CONFIG -------------------- #
API_KEY = "your_api_key"
API_SECRET = "your_api_secret"
CLIENT_ID = "your_client_code"
VC = "your_virtual_code"
IMEI = "your_device_imei"
LOT_MULTIPLIER = 1
MTM_TARGET_PERCENT = 0.25
UNDERLYING = "NIFTY"
SYMBOL_MASTER_URL = "https://api.flattrade.in/api/market/symbol_master"
# ------------------------------------------------------ #

TOKEN_FILE = "token.txt"
TOTP_SECRET_FILE = "totp_secret.enc"
FERNET_KEY_FILE = "fernet.key"
CSV_FILE = "symbol_master.csv"

def download_symbol_master():
    try:
        r = requests.get(SYMBOL_MASTER_URL)
        if r.status_code == 200:
            with open(CSV_FILE, "wb") as f:
                f.write(r.content)
            print(f"[{datetime.now()}] Symbol master downloaded.")
        else:
            print("Failed to download symbol master.")
    except Exception as e:
        print("Symbol master error:", e)

def decrypt_totp_secret():
    try:
        with open(FERNET_KEY_FILE, "rb") as f:
            key = f.read()
        with open(TOTP_SECRET_FILE, "rb") as f:
            encrypted = f.read()
        fernet = Fernet(key)
        return fernet.decrypt(encrypted).decode()
    except Exception as e:
        print("TOTP decryption error:", e)
        exit(1)

def load_token():
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE) as f:
            data = json.load(f)
        if time.time() - data["timestamp"] > 23 * 3600:
            return None
        return data["token"]
    except Exception:
        return None

def save_token(token):
    with open(TOKEN_FILE, "w") as f:
        json.dump({"token": token, "timestamp": time.time()}, f)

def get_new_token():
    totp_secret = decrypt_totp_secret()
    otp = pyotp.TOTP(totp_secret).now()
    payload = {
        "api_key": API_KEY,
        "api_secret": API_SECRET,
        "request_code": otp
    }
    try:
        res = requests.post("https://authapi.flattrade.in/trade/apitoken", json=payload)
        data = res.json()
        token = data.get("token")
        if token:
            save_token(token)
            return token
        else:
            raise Exception(f"Token error: {data}")
    except Exception as e:
        print("Token generation failed:", e)
        exit(1)

def get_token():
    token = load_token()
    if token:
        return token
    print(f"[{datetime.now()}] Token expired or missing. Generating new token...")
    return get_new_token()

def find_atm_strike():
    with open(CSV_FILE, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        options = [row for row in reader if UNDERLYING in row["TradingSymbol"] and row["Segment"] == "NFO-OPT"]
    # Filter NIFTY CE/PE for nearest expiry
    expiry = sorted(set(o["Expiry"] for o in options))[0]
    filtered = [o for o in options if o["Expiry"] == expiry]
    strikes = sorted({int(o["StrikePrice"]) for o in filtered})
    atm = min(strikes, key=lambda x: abs(x - get_live_price(get_token())))
    return atm, expiry

def get_live_price(token):
    url = f"https://api.flattrade.in/api/quote/{UNDERLYING}-EQ"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        res = requests.get(url, headers=headers)
        data = res.json()
        return float(data["last_price"])
    except Exception as e:
        print("Live price error:", e)
        exit(1)

def place_order(token, tsymbol, side, qty):
    payload = {
        "exchange": "NFO",
        "tradingsymbol": tsymbol,
        "transaction_type": side,
        "order_type": "MARKET",
        "product": "M",
        "quantity": qty
    }
    headers = {"Authorization": f"Bearer {token}"}
    try:
        res = requests.post("https://api.flattrade.in/trade/placeorder", json=payload, headers=headers)
        print(f"[{datetime.now()}] {side} {tsymbol} -> {res.json()}")
    except Exception as e:
        print("Order failed:", e)

def get_mtm(token):
    try:
        headers = {"Authorization": f"Bearer {token}"}
        res = requests.get("https://api.flattrade.in/trade/pnl", headers=headers)
        data = res.json()
        return float(data["data"]["mtm"])
    except Exception as e:
        print("MTM fetch error:", e)
        return 0

def run_strategy():
    download_symbol_master()
    token = get_token()

    atm_strike, expiry = find_atm_strike()
    ce_sell = f"{UNDERLYING}{expiry}C{atm_strike+100}"
    pe_sell = f"{UNDERLYING}{expiry}P{atm_strike-100}"
    ce_buy  = f"{UNDERLYING}{expiry}C{atm_strike+300}"
    pe_buy  = f"{UNDERLYING}{expiry}P{atm_strike-300}"

    lot_size = 50  # NIFTY lot size
    qty = LOT_MULTIPLIER * lot_size
    margin = qty * get_live_price(token)
    target = margin * MTM_TARGET_PERCENT / 100

    # Buy legs first
    place_order(token, ce_buy, "BUY", qty)
    place_order(token, pe_buy, "BUY", qty)

    # Then sell legs
    place_order(token, ce_sell, "SELL", qty)
    place_order(token, pe_sell, "SELL", qty)

    print(f"[{datetime.now()}] Iron Condor placed. Monitoring MTM target of ₹{target:.2f}...")

    while True:
        mtm = get_mtm(token)
        print(f"[{datetime.now()}] MTM: ₹{mtm:.2f}")
        if mtm >= target:
            print(f"[{datetime.now()}] Target met. Exiting positions...")
            place_order(token, ce_sell, "BUY", qty)
            place_order(token, pe_sell, "BUY", qty)
            place_order(token, ce_buy, "SELL", qty)
            place_order(token, pe_buy, "SELL", qty)
            break
        time.sleep(30)

# Run
if __name__ == "__main__":
    run_strategy()
