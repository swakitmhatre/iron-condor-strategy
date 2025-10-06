import requests
import json
import time
import logging
import hashlib
import threading
import websocket

# ====== USER CONFIGURATION ======
API_KEY = "8a321b48cc3a48d2b3f4d52c4eb719be"
API_SECRET = "2025.c633e7fdb18949f391b4677ba9132e691f2d6c6dcd1ca276"
UID = "FT053224"
ACT_ID = "FT053224"
BASE_URL = "https://piconnect.flattrade.in/PiConnectTP/"

LOT_SIZE = 75
TARGET_PROFIT = 10
STOP_LOSS = -10

# Iron Condor legs: tsym is token from Flattrade symbol master
IRON_CONDOR_LEGS = [
    {"tsym": "42632", "side": "B", "entry": 15.95},
    {"tsym": "42705", "side": "B", "entry": 10.0},
    {"tsym": "42644", "side": "S", "entry": 21.45},
    {"tsym": "42695", "side": "S", "entry": 18.0},
]

TOKEN_FILE = "token.txt"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

# ====== TOKEN MANAGEMENT ======
def generate_hash(api_key, request_token, api_secret):
    return hashlib.sha256(f"{api_key}{request_token}{api_secret}".encode()).hexdigest()

def get_new_token():
    print("1. Open the following URL in your browser and log in:")
    print(f"https://auth.flattrade.in/?app_key={API_KEY}")
    request_code = input("2. Enter request_code from redirect URL: ").strip()
    hashed_secret = generate_hash(API_KEY, request_code, API_SECRET)
    payload = {"api_key": API_KEY, "request_code": request_code, "api_secret": hashed_secret}
    r = requests.post("https://authapi.flattrade.in/trade/apitoken", json=payload)
    r.raise_for_status()
    token = r.json().get("token")
    if token:
        with open(TOKEN_FILE, "w") as f:
            json.dump({"token": token, "timestamp": time.time()}, f)
        logging.info("✅ New token generated and saved.")
        return token
    raise Exception(f"Token generation failed: {r.text}")

def get_token():
    try:
        with open(TOKEN_FILE, "r") as f:
            data = json.load(f)
        if time.time() - data["timestamp"] < 23 * 3600:
            logging.info("Using saved token")
            return data["token"]
    except:
        pass
    return get_new_token()

# ====== MTM CALCULATION ======
ltp_map = {}

def calc_mtm():
    pnl = 0
    for leg in IRON_CONDOR_LEGS:
        tsym = leg["tsym"]
        if tsym not in ltp_map:
            continue
        entry = leg["entry"]
        ltp = ltp_map[tsym]
        qty = LOT_SIZE
        pnl += (ltp - entry) * qty if leg["side"] == "B" else (entry - ltp) * qty
    return pnl

# ====== EXIT FUNCTION ======
def exit_iron_condor(JKEY):
    for leg in IRON_CONDOR_LEGS:
        trantype = "S" if leg["side"] == "B" else "B"
        payload = {
            "uid": UID,
            "actid": ACT_ID,
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

# ====== WEBSOCKET HANDLERS ======
def on_message(ws, message):
    global ltp_map
    try:
        data = json.loads(message)
        # Tick messages have type 'tk'
        if data.get("t") == "tk":
            token = data.get("tk")
            ltp = float(data.get("lp", 0))
            ltp_map[token] = ltp
            pnl = calc_mtm()
            logging.info(f"LTP update {token}: {ltp}, MTM: {pnl}")

            if pnl >= TARGET_PROFIT or pnl <= STOP_LOSS:
                logging.info("Target/Stoploss hit. Exiting Iron Condor...")
                ws.close()
                exit_iron_condor(ws.jKey)  # pass token
    except Exception as e:
        logging.error(f"Error in message: {e}")

def start_ws():
    JKEY = get_token()
    url = "wss://piconnect.flattrade.in/PiConnectWSTp/"
    ws = websocket.WebSocketApp(
        url,
        header=[f"Authorization: {JKEY}"],
        on_message=on_message,
        on_error=lambda ws, err: logging.error(f"WebSocket error: {err}"),
        on_close=lambda ws, code, msg: logging.warning(f"WebSocket closed: {msg}")
    )

    def on_open(ws):
        logging.info("WebSocket connected ✅")
        ws.jKey = JKEY  # attach token to ws
        # Subscribe to all legs
        for leg in IRON_CONDOR_LEGS:
            token = leg["tsym"]
            sub_msg = {"t": "t", "k": f"NFO|{token}"}
            ws.send(json.dumps(sub_msg))
            logging.info(f"Subscribed: {token}")

        # Keepalive ping every 20s
        def ping_loop():
            while True:
                try:
                    ws.send('{"t":"h"}')
                    time.sleep(20)
                except:
                    break
        threading.Thread(target=ping_loop, daemon=True).start()

    ws.on_open = on_open

    while True:
        try:
            ws.run_forever(ping_interval=30, ping_timeout=10)
        except Exception as e:
            logging.error(f"WebSocket crashed, reconnecting: {e}")
            time.sleep(5)

if __name__ == "__main__":
    logging.info("Starting Iron Condor MTM Tracker (WebSocket only)...")
    start_ws()
