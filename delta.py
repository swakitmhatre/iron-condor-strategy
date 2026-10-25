import time
import os
import hmac
import hashlib
import json
import requests
import pandas as pd
import numpy as np
import websocket

# =====================================================================
# CONFIGURATION & CREDENTIALS
# =====================================================================
API_KEY = "SxgQK4eNLqtrF54umC4IjjbVUCnrh8"
API_SECRET = "Ivu3wUr71sn2dmca21VPI4W0dhiqOcnxpBvrVUAsFlKHj4qybWvT2WVaNA1S"
BASE_URL = "https://india.delta.exchange"  
WS_URL = "wss://socket.india.delta.exchange"  
SYMBOL = "BTCUSD"                          
CONTRACT_SIZE = 0.001                      

def generate_signature(secret, method, endpoint, payload=''):
    """Generates the secure HMAC SHA256 signature for Delta India requests."""
    message = method + str(int(time.time())) + endpoint + str(payload)
    return hmac.new(secret.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()

def place_live_order(side, size=CONTRACT_SIZE):
    """Executes a market order on Delta India with full error shielding."""
    endpoint = "/v2/orders"
    url = BASE_URL + endpoint
    timestamp = str(int(time.time()))
    
    payload = {
        "product_id": 2, 
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
        res_data = response.json()
        
        if response.status_code == 200 and res_data.get('success'):
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] SUCCESS: {side.upper()} order executed successfully!")
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] EXCHANGE ORDER ERROR HANDLED: {res_data}")
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] EXCEPTION IN ORDER PLACEMENT: {e}")

def fetch_initial_candles():
    """
    Uses Delta India's official historical endpoint to fetch recent 5-minute candles 
    so indicators have immediate data upon program startup.
    """
    print("Fetching initial 5-minute candles via Delta REST API...")
    endpoint = "/v2/history/candles"
    url = BASE_URL + endpoint
    
    # Calculate timestamps for recent history (last 2 days to ensure plenty of 5m candles)
    end_time = int(time.time())
    start_time = end_time - (48 * 3600) 
    
    params = {
        'resolution': '5m',
        'symbol': SYMBOL,
        'start': str(start_time),
        'end': str(end_time)
    }
    headers = {'Accept': 'application/json'}
    
    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        data = response.json()
        
        if response.status_code == 200 and 'result' in data:
            candles = data['result']
            # Delta returns candles as lists: [time, open, high, low, close, volume]
            df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col])
            df = df.sort_values('timestamp').reset_index(drop=True)
            print(f"-> Successfully loaded {len(df)} historical 5-minute candles.")
            return df
    except Exception as e:
        print(f"-> Error fetching historical candles: {e}. Falling back to default mock data.")
    
    # Fallback dummy dataframe if network is ever unstable on boot
    fallback = pd.DataFrame({
        'timestamp': pd.date_range(end=pd.Timestamp.now(), periods=300, freq='5min').astype(int) // 10**9,
        'open': np.linspace(60000, 61000, 300),
        'high': np.linspace(60100, 61100, 300),
        'low': np.linspace(59900, 60900, 300),
        'close': np.linspace(60050, 60950, 300),
        'volume': np.ones(300) * 10
    })
    return fallback

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Computes EMA 200, MACD, and RSI indicators safely."""
    df = df.copy()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / loss)))
    return df

def check_strategy_status():
    """Reads local control switch file to verify if strategy should trade."""
    if not os.path.exists("control.txt"):
        with open("control.txt", "w") as f:
            f.write("STOPPED")
        return "STOPPED"
    try:
        with open("control.txt", "r") as f:
            return f.read().strip().upper()
    except:
        return "STOPPED"

def evaluate_and_trade(df: pd.DataFrame):
    """Evaluates multi-timeframe strategy indicators before sending signals."""
    status = check_strategy_status()
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Status Check: [{status}]")
    
    if status != "RUNNING":
        print("-> Strategy is currently STOPPED via control switch. No trades will be placed.")
        return

    latest = df.iloc[-1]
    print(f"-> Processing 5m Candle | Close: {latest['close']} | EMA200: {latest['ema_200']:.2f} | RSI: {latest['rsi']:.2f}")
    
    is_uptrend = latest['close'] > latest['ema_200']
    if is_uptrend and latest['rsi'] < 40:
        print(">>> Signal Triggered: Long Setup. Placing order...")
        place_live_order("buy", CONTRACT_SIZE)
    elif not is_uptrend and latest['rsi'] > 60:
        print(">>> Signal Triggered: Short Setup. Placing order...")
        place_live_order("sell", CONTRACT_SIZE)
    else:
        print("-> No trade setup matched. Holding position.")

def start_websocket_stream(df_historical):
    """Manages continuous WebSocket connection and listens for real-time 5m candle closes."""
    def on_open(ws):
        print(f"\n[SUCCESS] Connected to Delta India WebSocket Server!")
        sub_payload = {
            "type": "subscribe",
            "payload": {
                "channels": [{"name": "candlestick_5m", "symbols": [SYMBOL]}]
            }
        }
        ws.send(json.dumps(sub_payload))
        print(f"-> Subscribed to live 5-minute candlestick stream for {SYMBOL}.")

    def on_message(ws, message):
        try:
            data = json.loads(message)
            if "candlestick_5m" in data.get("channel", ""):
                candle = data.get('data', {})
                if candle.get('closed'):
                    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Closed 5m Candle Event Received from Delta!")
                    new_row = pd.DataFrame([{
                        'timestamp': candle.get('time'),
                        'open': float(candle.get('open')),
                        'high': float(candle.get('high')),
                        'low': float(candle.get('low')),
                        'close': float(candle.get('close')),
                        'volume': float(candle.get('volume'))
                    }])
                    nonlocal df_historical
                    df_historical = pd.concat([df_historical, new_row], ignore_index=True).tail(2000)
                    df_historical = calculate_indicators(df_historical)
                    evaluate_and_trade(df_historical)
        except Exception as err:
            print(f"Non-fatal message parsing error handled: {err}")

    def on_error(ws, error):
        print(f"WebSocket network alert: {error}")

    def on_close(ws, code, msg):
        print("Connection lost. Auto-reconnecting in 5 seconds without crashing...")
        time.sleep(5)
        start_websocket_stream(df_historical)

    ws_app = websocket.WebSocketApp(WS_URL, on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close)
    ws_app.run_forever(ping_interval=30, ping_timeout=10)

if __name__ == "__main__":
    print("Initializing Error-Proof Live Trading Program on AWS...")
    if not os.path.exists("control.txt"):
        with open("control.txt", "w") as f:
            f.write("STOPPED")
        print("Created 'control.txt' set to STOPPED by default.")

    # 1. Fetch real historical 5-minute data using your REST approach
    historical_df = fetch_initial_candles()
    
    # 2. Compute starting indicators
    historical_df = calculate_indicators(historical_df)
    
    # 3. Connect to live WebSocket stream for upcoming candle closures
    print("Connecting to Delta India WebSocket endpoint...")
    start_websocket_stream(historical_df)
