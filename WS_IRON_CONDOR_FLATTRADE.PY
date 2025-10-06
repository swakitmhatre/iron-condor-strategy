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

import websocket
import requests
import logging


# ====== USER CONFIGURATION ======
API_KEY = "8a321b48cc3a48d2b3f4d52c4eb719be"
API_SECRET = "2025.c633e7fdb18949f391b4677ba9132e691f2d6c6dcd1ca276"
U_ID = "FT053224"
ACT_ID="FT053224"
PASSWORD = "Swakit@123"
LOT_MULTIPLIER = 1
MTM_PERCENT = 0.0025     # 0.25%
UNDERLYING = "NIFTY"
BASE_URL = "https://piconnect.flattrade.in/PiConnectTP/"

LOT_SIZE = 75  # NIFTY lot size
TARGET_PROFIT = 10
STOP_LOSS     = -10

# Example Iron Condor legs with entry price (fetched when order is placed)
IRON_CONDOR_LEGS = [
    {"tsym": "NIFTY14OCT25P24350", "side": "B", "entry": 15.95},
    {"tsym": "NIFTY14OCT25C25450", "side": "B", "entry": 10.0},
    {"tsym": "NIFTY14OCT25P24450", "side": "S", "entry": 21.45},
    {"tsym": "NIFTY14OCT25C25350", "side": "S", "entry": 18.0},
]

# ===========================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
TOKEN_FILE = "token.txt"

#==============token generation process code=================
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

#==========token generation process code ends here========

# Store LTPs
ltp_map = {}

def calc_mtm():
    """Calculate MTM from LTPs vs entry price"""
    pnl = 0
    for leg in IRON_CONDOR_LEGS:
        tsym = leg["tsym"]
        if tsym not in ltp_map:
            continue
        entry = leg["entry"]
        ltp   = ltp_map[tsym]
        qty   = LOT_SIZE
        if leg["side"] == "B":   # Buy leg
            pnl += (ltp - entry) * qty
        else:  # Sell leg
            pnl += (entry - ltp) * qty
    return pnl


def exit_iron_condor():
    """Exit all 4 legs of iron condor"""
    for leg in IRON_CONDOR_LEGS:
        trantype = "S" if leg["side"] == "B" else "B"
        payload = {
            "uid": UID,
            "actid": ACTID,
            "exch": "NFO",
            "tsym": leg["tsym"],
            "qty": str(LOT_SIZE),
            "prc": "0",
            "prd": "NRML",
            "trantype": trantype,
            "prctyp": "MKT",
            "ret": "DAY"
        }
        jData = "jData=" + json.dumps(payload) + "&jKey=" + JKEY
        r = requests.post(BASE_URL + "PlaceOrder", data=jData)
        logging.info(f"Exit {trantype} {leg['tsym']}: {r.text}")
    logging.info("Iron Condor exited ✅")


def on_message(ws, message):
    global ltp_map
    try:
        data = json.loads(message)
        if "lp" in data:  # live price tick
            tsym = data["tsym"]
            ltp = float(data["lp"])
            ltp_map[tsym] = ltp

            pnl = calc_mtm()
            logging.info(f"LTP update {tsym}: {ltp}, MTM: {pnl}")

            if pnl >= TARGET_PROFIT or pnl <= STOP_LOSS:
                logging.info("Target/Stoploss hit. Exiting Iron Condor...")
                #exit_iron_condor()
                ws.close()
    except Exception as e:
        logging.error(f"Error in message handler: {e}")


def start_ws():
    JKEY = get_token()
    url = "wss://piconnect.flattrade.in/PiConnectTP/Websocket"
    ws = websocket.WebSocketApp(
        url,
        header=[f"jKey: {JKEY}"],
        on_message=on_message
    )

    def on_open(ws):
        logging.info("WebSocket connected ✅")
        # Subscribe to all legs
        for leg in IRON_CONDOR_LEGS:
            sub_msg = {"uid": UID, "exch": "NFO", "tsym": leg["tsym"]}
            ws.send(json.dumps(sub_msg))
            logging.info(f"Subscribed: {leg['tsym']}")

    ws.on_open = on_open
    ws.run_forever()


if __name__ == "__main__":
    logging.info("Starting Iron Condor MTM Tracker (WebSocket only)...")
    start_ws()
