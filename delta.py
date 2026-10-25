import time
import os
import hmac
import hashlib
import json
import requests
import pandas as pd
import numpy as np

# =====================================================================
# CONFIGURATION & CREDENTIALS
# =====================================================================
API_KEY = "YOUR_DELTA_INDIA_API_KEY"
API_SECRET = "YOUR_DELTA_INDIA_API_SECRET"
BASE_URL = "https://india.delta.exchange"  # Delta India Production REST endpoint
SYMBOL = "BTCUSD"                          # BTC Perpetual contract symbol
CONTRACT_SIZE = 0.001                      # Minimum order size requested (0.001 BTC)

# =====================================================================
# 1. AUTHENTICATION & API REQUEST HANDLERS
# =====================================================================
def generate_signature(secret, method, endpoint, payload=''):
    """
    Generates the HMAC SHA256 signature required by Delta India API 
    for secure authenticated REST requests.
    """
    message = method + str(int(time.time())) + endpoint + str(payload)
    signature = hmac.new(
        secret.encode('utf-8'), 
        message.encode('utf-8'), 
        hashlib.sha256
    ).hexdigest()
    return signature

def place_live_order(side, size=CONTRACT_SIZE):
    """
    Executes a market order (Buy/Sell) on Delta India for the 0.001 BTC perpetual.
    Includes full try-except exception handling to prevent crashes.
    """
    endpoint = "/v2/orders"
    url = BASE_URL + endpoint
    timestamp = str(int(time.time()))
    
    payload = {
        "product_id": 2, # Update to match Delta India BTC product ID if needed
        "size": size,
        "side": side,     # "buy" or "sell"
        "order_type": "market",
        "time_in_force": "ioc"
    }
    
    payload_str = json.dumps(payload)
    signature = generate_signature(API_SECRET, "POST", endpoint, payload_str)
    
    headers = {
        "api-key": API_KEY,
        "signature": signature,
        "timestamp": timestamp,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, data=payload_str, headers=headers, timeout=5)
        response_data = response.json()
        if response.status_code == 200 and response_data.get('success'):
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] SUCCESS: {side.upper()} order executed successfully!")
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ORDER REJECTED BY EXCHANGE: {response_data}")
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] NETWORK EXCEPTION during order placement: {e}")

# =====================================================================
# 2. TECHNICAL INDICATOR ENGINE
# =====================================================================
def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes EMA 200, MACD, and RSI on candle arrays.
    """
    df = df.copy()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    return df

# =====================================================================
# 3. CONTROL SWITCH & STRATEGY EVALUATION LOOP
# =====================================================================
def check_strategy_status():
    """
    Reads local 'control.txt' file to check if strategy is RUNNING or STOPPED.
    """
    if not os.path.exists("control.txt"):
        with open("control.txt", "w") as f:
            f.write("STOPPED")
        return "STOPPED"
    
    try:
        with open("control.txt", "r") as f:
            status = f.read().strip().upper()
        return status
    except Exception:
        return "STOPPED"

def fetch_latest_candles():
    """
    Fetches recent 5-minute candles via Delta REST API to build our working dataframe.
    """
    endpoint = f"/v2/history/candles?symbol={SYMBOL}&resolution=5m&limit=300"
    url = BASE_URL + endpoint
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if response.status_code == 200 and 'result' in data:
            candles = data['result']
            df = pd.DataFrame(candles)
            # Standardize column names based on Delta API response format
            df = df.rename(columns={0: 'time', 1: 'open', 2: 'high', 3: 'low', 4: 'close', 5: 'volume'})
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])
            df = df.sort_values('time').reset_index(drop=True)
            return df
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Error fetching candles from Delta: {e}")
    return None

def run_trading_loop():
    """
    Main execution loop: Checks status, fetches candles, evaluates strategy, 
    and sleeps safely between 5-minute intervals.
    """
    print("Strategy engine started. Entering polling loop...")
    
    while True:
        status = check_strategy_status()
        current_time = time.strftime('%Y-%m-%d %H:%M:%S')
        
        if status != "RUNNING":
            print(f"[{current_time}] Status: [STOPPED]. To start, type: echo 'RUNNING' > control.txt")
            time.sleep(10) # Check every 10 seconds if user turned it on
            continue
            
        print(f"\n[{current_time}] Status: [RUNNING]. Fetching latest market data...")
        df = fetch_latest_candles()
        
        if df is not None and not df.empty:
            df = calculate_indicators(df)
            latest = df.iloc[-1]
            current_price = latest['close']
            ema_val = latest['ema_200']
            rsi_val = latest['rsi']
            
            print(f"-> BTC Price: {current_price} | EMA200: {ema_val:.2f} | RSI: {rsi_val:.2f}")
            
            # Strategy Execution Rules
            is_uptrend = current_price > ema_val
            if is_uptrend and rsi_val < 40:
                print(">>> Signal Triggered: Long Setup! Placing order...")
                place_live_order("buy", CONTRACT_SIZE)
            elif not is_uptrend and rsi_val > 60:
                print(">>> Signal Triggered: Short Setup! Placing order...")
                place_live_order("sell", CONTRACT_SIZE)
            else:
                print("-> No trade setup met. Waiting for next candle check...")
        else:
            print("-> Warning: Could not fetch candle data. Retrying shortly...")
            
        # Sleep for 5 minutes (300 seconds) before checking the next candle update
        print("-> Sleeping for 5 minutes until next candle cycle...")
        time.sleep(300)

if __name__ == "__main__":
    print("Initializing Live Trading Program Structure...")
    if not os.path.exists("control.txt"):
        with open("control.txt", "w") as f:
            f.write("STOPPED")
        print("Created 'control.txt' set to STOPPED by default.")
        
    run_trading_loop()
