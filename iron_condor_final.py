import requests
import pandas as pd
import time
from datetime import datetime, timedelta
import requests
import json

# === CONFIGURATION === #
ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzU0OTI0MTYyLCJ0b2tlbkNvbnN1bWVyVHlwZSI6IlNFTEYiLCJ3ZWJob29rVXJsIjoiIiwiZGhhbkNsaWVudElkIjoiMTEwMDkyMjIyNiJ9.YcY7_aIOuhDBQ9VD3yyfz9eIMnDcD3o3aEgwfR38q4ZRJ2Vkdl44103dIZIdibk0kilRUeA451LH9mBHQjra4A"
CLIENT_ID = "1100922226"
ACCOUNT_ID = "your_account_id"

NUM_CONDORS = 1                     # Number of Iron Condors
TARGET_PCT = 0.25                   # Target profit (% of total margin)
BUY_OFFSET = 11                    # Buy legs further OTM
SELL_OFFSET = 9                    # Sell legs closer to ATM
STRIKE_INTERVAL = 50
MTM_POLL_INTERVAL = 0.05           # 50ms MTM polling
ENTRY_TIMEOUT = 0.8                # Max allowed entry delay (seconds)

# === CONSTANTS === #
BASE = "https://api.dhan.co"
SYMBOL_MASTER_URL = "https://images.dhan.co/api-data/api-scrip-master.csv"
LOG_FILE = "iron_condor_log.txt"

HEADERS = {
    "access-token": ACCESS_TOKEN,
    "client-id": CLIENT_ID,
    "Content-Type": "application/json"
}


# === UTILITY FUNCTIONS === #

def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    with open(LOG_FILE, "a") as f:
        f.write(f"[{timestamp}] {message}\n")
    print(f"[{timestamp}] {message}")


def get_next_thursday():
    today = datetime.today()
    offset = (3 - today.weekday()) % 7
    offset = offset if offset > 0 else 7
    next_expiry = today + timedelta(days=offset)
    return next_expiry.strftime("%d%b%y").upper()


def fetch_symbol_master():
    return pd.read_csv(SYMBOL_MASTER_URL,low_memory=False)


def fetch_nifty_spot():
    url = f"{BASE}/market/quote/NIFTY"
    try:
        res = requests.get(url, headers=HEADERS, timeout=0.5)
        return float(res.json().get("last_traded_price", 22500))
    except:
        return 22500


def round_to_strike(price):
    return round(price / STRIKE_INTERVAL) * STRIKE_INTERVAL


def resolve_option_tokens(df, atm_strike):
    expiry = get_next_thursday()
    strike_map = {
        "PE_BUY": atm_strike - BUY_OFFSET * STRIKE_INTERVAL,
        "PE_SELL": atm_strike - SELL_OFFSET * STRIKE_INTERVAL,
        "CE_SELL": atm_strike + SELL_OFFSET * STRIKE_INTERVAL,
        "CE_BUY": atm_strike + BUY_OFFSET * STRIKE_INTERVAL
    }

    resolved = {}
    for leg, strike in strike_map.items():
        ts = f"NIFTY{expiry}{strike}{'PE' if 'PE' in leg else 'CE'}"
        #print("expiry---->",expiry)
        #print("strike---->",strike)
        #print("token symbol---->",ts)
        s = expiry
        converted = f"{s[:2]} {s[2:5]}"
        #print("converted----->",converted)
        ts="NIFTY "+converted+" "+str(strike)+" "
        ts = f"{ts}{'PUT' if 'PE' in leg else 'CALL'}"
        #print("FINAL token symbol---->",ts)
        #print("column names--->",df.columns)
        
        row = df[df["SEM_CUSTOM_SYMBOL"] == ts]
        #print("row----->",row["SEM_SMST_SECURITY_ID"])
        if row.empty:
            log(f"[ERROR] Token not found for {ts}")
            return None
        resolved[leg] = row.iloc[0]["SEM_SMST_SECURITY_ID"]
        resolved["LOT_SIZE"] = int(row.iloc[0]["SEM_LOT_UNITS"])
    return resolved


def get_margin_requirement(resolved):
    total = 0
    count=0
    for key in ['PE_BUY', 'PE_SELL', 'CE_SELL', 'CE_BUY']:
        sec_id = int(resolved[key])
        my_actions = ["BUY", "SELL", "SELL", "BUY"]
        print("resolved---->",resolved)
        print("sec_id----->",sec_id)
        try:
            url = "https://api.dhan.co/v2/margincalculator/"  # <-- ✅ Fixed endpoint
            headers = {
                  "access-token": ACCESS_TOKEN,
                  "client-id": CLIENT_ID,
                  "Content-Type": "application/json",
                  "Accept": "application/json",
                      }
            payload = {
                "dhanClientId": CLIENT_ID,
                "exchangeSegment": "NSE_FNO",
                "securityId": str(int(resolved[key])),
                "transactionType": my_actions[count],
                "quantity": int(resolved["LOT_SIZE"] * NUM_CONDORS),
                "orderType": "MARKET",
                "productType": "INTRADAY",
                "price": 0,
                "triggerPrice": 0,
            }
            log("Sending legs to margin API:\n" + json.dumps(payload, indent=2))
            res = requests.post(url, headers=headers, json=json.dumps(payload), timeout=1)
            #res = requests.post(url, headers=headers, payload=json.dumps(payload))
            #margin = get_margin_for_strategy(access_token, instrument, quantity, order_type)
            count=count+1
            print("res----->",res.json())
            

            total += float(res.json()[0].get("margin", 0))
            
       #except:
            #log(f"[ERROR] Failed margin fetch for {key}")
            #return 0
        except requests.exceptions.Timeout:
            print("Request timed out. Please try again later.")
            return 0
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            return 0
    print("total margin needed---->",total)
    return total
'''

def get_margin_requirement(resolved):
    keys = ['PE_BUY', 'PE_SELL', 'CE_SELL', 'CE_BUY']
    actions = ["BUY", "SELL", "SELL", "BUY"]

    legs = []

    for i, key in enumerate(keys):
        legs.append({
            "dhanClientId": CLIENT_ID,
            "exchangeSegment": "NSE_FNO",
            "securityId": str(int(resolved[key])),
            "transactionType": actions[i],
            "quantity": int(resolved["LOT_SIZE"] * NUM_CONDORS),
            "orderType": "MARKET",
            "productType": "INTRADAY",
            "price": 0,
            "triggerPrice": 0
        })

    log("Sending legs to margin API:\n" + json.dumps(legs, indent=2))

    try:
        res = requests.post(
            "https://api.dhan.co/margin/calculator",  # <-- ✅ Fixed endpoint
            headers={
                "access-token": ACCESS_TOKEN,
                "client-id": CLIENT_ID,
                "Content-Type": "application/json",
                "Accept": "application/json"
            },
            json={"legs": legs},  # <-- ✅ Wrapped in a dict
            timeout=5
        )

        if res.status_code != 200:
            log(f"[ERROR] Margin API failed: {res.status_code} {res.text}")
            return 0

        data = res.json()
        margin = float(data.get("totalMargin", 0))
        log(f"[MARGIN] Total required margin: ₹{margin}")
        return margin

    except Exception as e:
        log(f"[EXCEPTION] Margin fetch error: {e}")
        return 0
'''
def place_order(security_id, side, qty):
    payload = {
        "account_id": ACCOUNT_ID,
        "exchange_segment": "NSEFO",
        "product_type": "INTRADAY",
        "order_type": "MARKET",
        "transaction_type": side,
        "security_id": security_id,
        "quantity": qty,
        "validity": "DAY"
    }
    start = time.perf_counter()
    res = requests.post(f"{BASE}/orders", headers=HEADERS, json=payload)
    delay = round((time.perf_counter() - start) * 1000, 2)
    log(f"ORDER | {side} | {security_id} | qty={qty} | delay={delay}ms | code={res.status_code}")
    return delay


def get_mtm():
    try:
        res = requests.get(f"{BASE}/positions", headers=HEADERS, timeout=0.5)
        positions = res.json()
        return sum(float(p.get("pnl", 0)) for p in positions if p["account_id"] == ACCOUNT_ID)
    except Exception as e:
        log(f"[ERROR] MTM fetch failed: {e}")
        return 0


# === STRATEGY EXECUTION === #

def main():
    log("🚀 Starting Iron Condor Strategy")

    # Fetch spot and symbol master
    spot_price = fetch_nifty_spot()
    atm_strike = round_to_strike(spot_price)
    df = fetch_symbol_master()
    log(f"Spot = {spot_price}, ATM = {atm_strike}")

    # Resolve tokens
    tokens = resolve_option_tokens(df, atm_strike)
    if not tokens:
        log("❌ Exiting due to token resolution failure")
        return

    qty = tokens["LOT_SIZE"] * NUM_CONDORS
    margin = get_margin_requirement(tokens)
    if margin <= 0:
        log("❌ Exiting due to margin fetch failure")
        return

    target_profit = margin * TARGET_PCT / 100
    log(f"✅ Margin = ₹{margin:.2f}, Target Profit = ₹{target_profit:.2f}, Qty per leg = {qty}")

    # === ENTRY (Buy Legs → Sell Legs) ===
    entry_start = time.perf_counter()
    place_order(tokens["PE_BUY"], "BUY", qty)
    place_order(tokens["CE_BUY"], "BUY", qty)
    place_order(tokens["PE_SELL"], "SELL", qty)
    place_order(tokens["CE_SELL"], "SELL", qty)
    entry_delay = round(time.perf_counter() - entry_start, 3)

    entry_time = datetime.now()
    log(f"✅ ENTRY COMPLETE | Time = {entry_time} | Delay = {entry_delay}s")

    if entry_delay > ENTRY_TIMEOUT:
        log("⚠️ Entry delay exceeded recommended threshold!")

    # === MTM MONITOR LOOP ===
    condition_met_time = None
    while True:
        start = time.perf_counter()
        mtm = get_mtm()
        log(f"📈 MTM = ₹{mtm:.2f}")

        if mtm >= target_profit:
            condition_met_time = datetime.now()
            log(f"🎯 TARGET HIT at {condition_met_time}")

            # Exit Sell Legs First
            place_order(tokens["PE_SELL"], "BUY", qty)
            place_order(tokens["CE_SELL"], "BUY", qty)

            # Small delay to ensure broker processes sell exits first
            time.sleep(0.1)

            # Exit Buy Legs
            place_order(tokens["PE_BUY"], "SELL", qty)
            place_order(tokens["CE_BUY"], "SELL", qty)
            break

        elapsed = time.perf_counter() - start
        sleep_time = max(0, MTM_POLL_INTERVAL - elapsed)
        time.sleep(sleep_time)

    exit_time = datetime.now()
    log(f"🏁 Strategy Exit Time = {exit_time}")
    log("✅ All legs exited. Strategy complete.\n")


if __name__ == "__main__":
    main()
