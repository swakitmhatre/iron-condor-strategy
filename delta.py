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
    """
    Executes a market order on Delta India. 
    Wrapped in robust try-except blocks so order rejections or network errors 
    CANNOT crash or stop your AWS program.
    """
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
            print("-> Safety Shield Active: Program will NOT crash. Continuing 24/7 loop...")
            
    except requests.exceptions.Timeout:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] WARNING: Order request timed out. Continuing execution safely...")
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] CRITICAL EXCEPTION CAUGHT IN ORDER PLACEMENT: {e}")
        print("-> Safety Shield Active: Program is keeping execution alive.")

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
    """Manages continuous WebSocket connection and sends the required candle subscription payload."""
    def on_open(ws):
        print(f"\n[SUCCESS] Connected to Delta India WebSocket Server!")
        
        # FIXED: Explicitly send subscription payload so Delta server streams 5m candles to us
        sub_payload = {
            "type": "subscribe",
            "payload": {
                "channels": [{"name": "candlestick_5m", "symbols": [SYMBOL]}]
            }
        }
        ws.send(json.dumps(sub_payload))
        print(f"-> Sent subscription request for live 5-minute candles on {SYMBOL}.")

    def on_message(ws, message):
        try:
            data = json.loads(message)
            # Print a subtle message when heartbeats or messages arrive so you know it's active
            if "candlestick_5m" in data.get("channel", ""):
                candle = data.get('data', {})
                if candle.get('closed'):
                    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Closed 5m Candle Event Received from Delta!")
                    new_row = pd.DataFrame([{
                        'timestamp': candle['time'],
                        'open': float(candle['open']),
                        'high': float(candle['high']),
                        'low': float(candle['low']),
                        'close': float(candle['close']),
                        'volume': float(candle['volume'])
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

    mock_history = pd.DataFrame({
        'timestamp': pd.date_range(end=pd.Timestamp.now(), periods=300, freq='5min'),
        'open': np.linspace(60000, 61000, 300),
        'high': np.linspace(60100, 61100, 300),
        'low': np.linspace(59900, 60900, 300),
        'close': np.linspace(60050, 60950, 300),
        'volume': np.ones(300) * 10
    })
    mock_history = calculate_indicators(mock_history)
    
    print("Connecting to Delta India WebSocket endpoint...")
    start_websocket_stream(mock_history)
