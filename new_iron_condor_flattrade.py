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
import threading
import websocket
import sys
import os

# ====== USER CONFIGURATION ======
API_KEY = "8a321b48cc3a48d2b3f4d52c4eb719be"
API_SECRET = "2025.c633e7fdb18949f391b4677ba9132e691f2d6c6dcd1ca276"
CLIENT_ID = "FT053224"
UID = "FT053224"
ACT_ID = "FT053224"
BASE_URL = "https://piconnect.flattrade.in/PiConnectTP/"
PASSWORD = "Swakit@123"
LOT_MULTIPLIER = 1
MTM_PERCENT = 0.0025     # 0.25%
UNDERLYING = "NIFTY"

LOT_SIZE = 75
TARGET_PROFIT = 15
STOP_LOSS = -15
FALLBACK_AGE = 15          # ✅ if no tick for 30 s, reconnect
WATCHDOG_INTERVAL = 5     # How often to check tick freshness
PING_INTERVAL = 10         # How often to send ping for heartbeat

IRON_CONDOR_LEGS=[]
exit_flag = threading.Event()
ltp_map = {}
last_tick_time = {}  # ✅ Initialize this dictionary globally
watchdog_running = True
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

def get_margin(token):
    try:
        r = requests.get("https://api.flattrade.in/trade/margin", headers={"Authorization": f"Bearer {token}"})
        return float(r.json()["total_margin"])
    except Exception as e:
        logging.warning(f"Margin fetch failed: {e}")
        return 150000  # fallback default

def place_order(JKEY, symbol, qty, SIDE):
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
        payload = f"jData={json.dumps(jData_dict)}&jKey={JKEY}"

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
                    #return line.split(",")[4]
                    return [line.split(",")[1],line.split(",")[4]]
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

#=========returns entry of placed order=======================
def get_order_book(JKEY):
    try:
        jData_dict = {
            "uid": "FT053224"
        }
        payload = f"jData={json.dumps(jData_dict)}&jKey={JKEY}"

        headers = {
            "Content-Type": "application/json"
        }
        print("orderbook paylod---->",payload)
       
        r = requests.post("https://piconnect.flattrade.in/PiConnectTP/OrderBook", data=payload,headers=headers)
        #print("Orderbook API raw response:", r.text)
        res = r.json()
        return res
    except Exception as e:
        logging.error(f"Order failed: {e}")
        
#=========get entry price from OrderBook api==================

def get_entry_price(data,tsym):

    #print("data===========>>>>",data)
    for order in data:
        
        if order.get("tsym") == tsym:
            return float(order.get("avgprc")) / 100  # divide by 100 if price is in paise
    return None

def run_strategy():
    download_symbol_master()
    token = get_token()
    #HERE TOKEN IS LOGIN_TOKEN I.E JKey ,NOT SYMBOL TOKEN.
    live_price = get_live_price(token,CLIENT_ID)
    #margin = get_margin(token)
    margin = 125000
    mtm_target = margin * MTM_PERCENT
    LOT_SIZE = 75 * LOT_MULTIPLIER

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

    # Entry - Buy first
    JKEY=token
    entry_start = time.perf_counter()
    place_order(JKEY, symbols["buy_pe"][1], LOT_SIZE, "B")
    place_order(JKEY, symbols["buy_ce"][1], LOT_SIZE, "B")
    place_order(JKEY, symbols["sell_pe"][1], LOT_SIZE, "S")
    place_order(JKEY, symbols["sell_ce"][1], LOT_SIZE, "S")

    entry_delay = round(time.perf_counter() - entry_start, 3)
    entry_time = datetime.now()
    logging.info(f"✅ ENTRY COMPLETE | Time = {entry_time} | Delay = {entry_delay}s")
    logging.info("Iron Condor entered. Monitoring MTM...")

    entry_price=get_order_book(JKEY)
    # Iron Condor legs: tsym is token from Flattrade symbol master
    global IRON_CONDOR_LEGS
    IRON_CONDOR_LEGS = [
        {"tsym": symbols["buy_pe"][0], "side": "B", "entry": get_entry_price(entry_price,symbols["buy_pe"][1])},
        {"tsym": symbols["buy_ce"][0], "side": "B", "entry": get_entry_price(entry_price,symbols["buy_ce"][1])},
        {"tsym": symbols["sell_pe"][0], "side": "S", "entry":get_entry_price(entry_price,symbols["sell_pe"][1])},
        {"tsym": symbols["sell_ce"][0], "side": "S", "entry": get_entry_price(entry_price,symbols["sell_ce"][1])},
    ]
    print("IRON_CONDOR_LEGS initialised----->",IRON_CONDOR_LEGS)

#======start websocket and open(ws)===================
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
        print("IRON_CONDOR_LEGS---->",IRON_CONDOR_LEGS)
        time.sleep(1)
        # Subscribe to all legs
        for leg in IRON_CONDOR_LEGS:
            token = leg["tsym"]
            print("token---->",token)
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

# ====== MTM CALCULATION ======
def calc_mtm():
    pnl = 0
    for leg in IRON_CONDOR_LEGS:
        tsym = leg["tsym"]
        if tsym not in ltp_map:
            continue
        entry = leg["entry"] * LOT_SIZE
        ltp = ltp_map[tsym]
        print("symbol,entry,ltp---->",tsym,entry,ltp)
        qty = LOT_SIZE
        pnl += (ltp - entry)  if leg["side"] == "B" else (entry - ltp) 
        #pnl += (ltp - entry) * qty if leg["side"] == "B" else (entry - ltp) * qty
        print("pnl--->",pnl)
    return pnl

# ====== EXIT(order) FUNCTION ======
def exit_iron_condor(JKEY):
    print("in exit_iron_condor()IRON_CONDOR_LEGS---->",IRON_CONDOR_LEGS)
    for leg in IRON_CONDOR_LEGS:
        trantype = "S" if leg["side"] == "B" else "B"
        jData_dict = {
            "uid": "FT053224",
            "actid": "FT053224",
            "exch": "NFO",
            "tsym": leg["tsym"],
            "qty": str(LOT_SIZE),
            "prc": "0",
            "prd": "I",
            "trantype": trantype,
            "prctyp": "MKT",
            "ret": "DAY"
        }

        payload = f"jData={json.dumps(jData_dict)}&jKey={JKEY}"

        headers = {
            "Content-Type": "application/json"
        }
        print("order paylod---->",payload)
        #jData = "jData=" + json.dumps(payload) + "&jKey=" + JKEY
        #r = requests.post(BASE_URL + "PlaceOrder", data=jData)
        r = requests.post("https://piconnect.flattrade.in/PiConnectTP/PlaceOrder", data=payload,headers=headers)
        logging.info(f"Exit {trantype} {leg['tsym']}: {r.text}")
    
    logging.info("Iron Condor exited ✅")
    
#========immediate exit(thread)===========

def trigger_exit(reason="Target/Stoploss hit"):
    if not exit_flag.is_set():
        logging.warning(f"{reason}. Exiting Iron Condor NOW ⚡")
        exit_flag.set()

        # Immediately close WebSocket (forces disconnection)
        try:
            ws.close()
        except Exception:
            pass

        # Force immediate process termination (within 50 ms)
        threading.Thread(target=lambda: (time.sleep(0.05), os._exit(0))).start()


# ====== WEBSOCKET HANDLERS ======
def on_message(ws, message):
    if exit_flag.is_set():
        return
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
                trigger_exit()
                logging.info("Target/Stoploss hit. Exiting Iron Condor...")
                ws.close()
                exit_iron_condor(JKEY)   # careful: pass valid JKEY here
                time.sleep(2)
                logging.info("✅ Strategy stopped after target/stoploss hit.")
                sys.exit(0)

        else:
            # show other server messages for debugging
            logging.debug(f"Non-tick message: {data}")

    except Exception as e:
        logging.error(f"Error in message: {e}")

def on_error(ws, error):
    if not exit_flag.is_set():
        logger.error(f"WebSocket error: {error}")

def on_close(ws, close_status_code, close_msg):
    logger.info(f"WebSocket closed: {close_msg}")


#======== call only rarely and as fallback; needs JKEY which your main function obtains=====
def get_quote_snapshot(token, JKEY):
    """
    Fetch latest LTP for the token using GetQuotes endpoint as fallback.
    Returns float or None.
    """
    
    try:
        if exit_flag.is_set():
            return
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

#=========watchdog loop===========

def watchdog_thread(JKEY):
    """
    Periodically checks tokens; if token hasn't updated for FALLBACK_AGE seconds,
    fetch a single snapshot via REST and update ltp_map so calc_mtm can continue.
    """
    while True:
        if exit_flag.is_set():
            return
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

if __name__ == "__main__":
    run_strategy()
    logging.info("Starting Iron Condor MTM Tracker (WebSocket only)...")
    start_ws()
