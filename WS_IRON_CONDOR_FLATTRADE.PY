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
TARGET_PROFIT = 30
STOP_LOSS = -30
FALLBACK_AGE = 30  # ✅ if no tick for 30 s, reconnect
WATCHDOG_INTERVAL = 10     # How often to check tick freshness
PING_INTERVAL = 20         # How often to send ping for heartbeat


# Iron Condor legs: tsym is token from Flattrade symbol master
IRON_CONDOR_LEGS = [
    {"tsym": "42632", "side": "B", "entry": 3.00},
    {"tsym": "42705", "side": "B", "entry": 35.0},
    {"tsym": "42644", "side": "S", "entry": 3.60},
    {"tsym": "42695", "side": "S", "entry": 77.0},
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
last_tick_time = {}  # ✅ Initialize this dictionary globally

def calc_mtm():
    pnl = 0
    for leg in IRON_CONDOR_LEGS:
        tsym = leg["tsym"]
        if tsym not in ltp_map:
            continue
        entry = leg["entry"]
        ltp = ltp_map[tsym]
        print("symbol,entry,ltp---->",tsym,entry,ltp)
        qty = LOT_SIZE
        pnl += (ltp - entry) * qty if leg["side"] == "B" else (entry - ltp) * qty
        print("pnl--->",pnl)
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
        # log every raw message (short-term; remove or lower level later)
        logging.debug(f"RAW_WS_MSG: {message}")

        data = json.loads(message)

        # accept multiple tick types — handle 'tk' and 'tf' and 'tkf' etc.
        t = data.get("t")
        if t in ("tk", "tf", "tkf", "tfk"):   # cover variants
            token = data.get("tk") or data.get("tk") or data.get("token") or data.get("k")
            if not token:
                # sometimes token is in 'k' as "NFO|42632"
                k = data.get("k")
                if k and "|" in k:
                    token = k.split("|")[-1]

            ltp_raw = data.get("lp") or data.get("ltp") or data.get("last_price")
            if ltp_raw is None:
                logging.debug(f"No lp in tick: {data}")
                return

            try:
                ltp = float(ltp_raw)
            except:
                logging.debug(f"Couldn't parse lp: {ltp_raw}")
                return

            # update LTP and timestamp
            ltp_map[token] = ltp
            last_tick_time[token] = time.time()

            # human-friendly logging
            pnl = calc_mtm()
            logging.info(f"LTP update {token}: {ltp:.2f}, MTM: {pnl:.2f}, last_tick_age: 0s")

            # exit if threshold hit
            if pnl >= TARGET_PROFIT or pnl <= STOP_LOSS:
                logging.info("Target/Stoploss hit. Exiting Iron Condor...")
                ws.close()
                # exit_iron_condor(JKEY)   # careful: pass valid JKEY here
                time.sleep(2)
                logging.info("✅ Strategy stopped after target/stoploss hit.")
                sys.exit(0)

        else:
            # show other server messages for debugging
            logging.debug(f"Non-tick message: {data}")

    except Exception as e:
        logging.error(f"Error in message: {e}")

# call only rarely and as fallback; needs JKEY which your main function obtains
def get_quote_snapshot(token, JKEY):
    """
    Fetch latest LTP for the token using GetQuotes endpoint as fallback.
    Returns float or None.
    """
    try:
        # Build jData: example expects uid, exch and token (string)
        jdata = {"uid": UID, "exch": "NFO", "token": token}
        payload = f"jData={json.dumps(jdata)}&jKey={JKEY}"
        url = BASE_URL + "GetQuotes"
        r = requests.post(url, data=payload, timeout=2)
        r.raise_for_status()
        resp = r.json()

        # Inspect structure (it can vary). We try common places:
        # e.g., resp.get('lp') or resp.get('data')[0].get('lp'), etc.
        if isinstance(resp, dict):
            # try few patterns
            if 'lp' in resp:
                return float(resp['lp'])
            if 'data' in resp and isinstance(resp['data'], list) and resp['data']:
                d0 = resp['data'][0]
                if 'lp' in d0:
                    return float(d0['lp'])
        logging.debug(f"Snapshot unexpected format: {resp}")
    except Exception as e:
        logging.debug(f"Snapshot fetch failed for {token}: {e}")
    return None

def watchdog_thread(JKEY):
    """
    Periodically checks tokens; if token hasn't updated for FALLBACK_AGE seconds,
    fetch a single snapshot via REST and update ltp_map so calc_mtm can continue.
    """
    while True:
        now = time.time()
        for leg in IRON_CONDOR_LEGS:
            token = leg["tsym"]
            last = last_tick_time.get(token, 0)
            age = now - last
            if age > FALLBACK_AGE:
                logging.info(f"Watchdog: token {token} last update {age:.1f}s ago -> snapshot")
                snapshot = get_quote_snapshot(token, JKEY)
                if snapshot is not None:
                    ltp_map[token] = snapshot
                    last_tick_time[token] = time.time()
                    pnl = calc_mtm()
                    logging.info(f"Watchdog refreshed {token} -> {snapshot}, MTM: {pnl:.2f}")
                else:
                    logging.debug(f"Watchdog snapshot failed for {token}")
        time.sleep(WATCHDOG_INTERVAL)


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
        logging.info("WebSocket connected ✅")

        # Step 1: Send connection payload (important)
        conn_msg = {
            "t": "c",
            "uid": UID,
            "actid": ACT_ID,
            "source": "API",
            "susertoken": JKEY
        }
        ws.send(json.dumps(conn_msg))
        logging.info("Connection payload sent")
    
        time.sleep(1)
        # Subscribe to all legs
        for leg in IRON_CONDOR_LEGS:
            token = leg["tsym"]
            sub_msg = {
                        "t": "t",             # touchline subscription
                        "k": f"NFO|{token}",  # exchange + token
                        "uid": UID
                    }
            ws.send(json.dumps(sub_msg))
            logging.info(f"Subscribed: {token}")
      
        # Keepalive ping every 20s
        def ping_loop():
            while True:
                try:
                    #print("hi")
                    ws.send('{"t":"h"}')
                    time.sleep(20)
                except:
                    break
        threading.Thread(target=ping_loop, daemon=True).start()
        threading.Thread(target=watchdog_thread, args=(JKEY,), daemon=True).start()
       
    ws.on_open = on_open
    
    while True:
        try:
            print("forever")
            ws.run_forever(ping_interval=30, ping_timeout=10)
        except SystemExit:
            raise  # clean stop on target/stoploss
        except Exception as e:
            logging.error(f"WebSocket crashed, reconnecting: {e}")
            time.sleep(5)
    
if __name__ == "__main__":
    logging.info("Starting Iron Condor MTM Tracker (WebSocket only)...")
    start_ws()
