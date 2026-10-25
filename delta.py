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
API_KEY = "YOUR_DELTA_INDIA_API_KEY"
API_SECRET = "YOUR_DELTA_INDIA_API_SECRET"
BASE_URL = "https://india.delta.exchange"  
WS_URL = "wss://socket.india.delta.exchange"  
SYMBOL = "BTCUSD"                          
CONTRACT_SIZE = 0.001                      

def generate_signature(secret, method, endpoint, payload=''):
    message = method + str(int(time.time())) + endpoint + str(payload)
    return hmac.new(secret.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()

def place_live_order(side, size=CONTRACT_SIZE):
    endpoint = "/v2/orders"
    url = BASE_URL + endpoint
    timestamp = str(int(time.time()))
    payload = {"product_id": 2, "size": size, "side": side, "order_type": "market", "time_in_force": "ioc"}
    payload_str = json.dumps(payload)
    signature = generate_signature(API_SECRET, "POST", endpoint, payload_str)
    headers = {"api-key": API_KEY, "signature": signature, "timestamp": timestamp, "Content-Type": "application/json"}
    
    try:
        response = requests.post(url, data=payload_str, headers=headers, timeout=5)
        res_data = response.json()
        if response.status_code == 200 and res_data.get('success'):
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] SUCCESS: {side.upper()} order executed!")
        else:
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ORDER REJECTED: {res_data}")
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ORDER EXCEPTION: {e}")

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
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
    status = check_strategy_status()
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S সিস্ট')}] Status: [{status}]")
    if status != "RUNNING":
        print("-> Strategy is STOPPED via control.txt. Change to RUNNING to trade.")
        return

    latest = df.iloc[-1]
    print(f"-> Processing 5m Candle | Close: {latest['close']} | EMA200: {latest['ema_200']:.2f} | RSI: {latest['rsi']:.2f}")
    
    is_uptrend = latest['close'] > latest['ema_200']
    if is_uptrend and latest['rsi'] < 40:
        print(">>> Signal: Long Setup. Placing order...")
        place_live_order("buy", CONTRACT_SIZE)
    elif not is_uptrend and latest['rsi'] > 60:
        print(">>> Signal: Short Setup. Placing order...")
        place_live_order("sell", CONTRACT_SIZE)
    else:
        print("-> No trade setup matched. Holding.")

def start_websocket_stream(df_historical):
    def on_open(ws):
        print(f"\n[SUCCESS] Connected to Delta India WebSocket Server! Handshake established.")
        # Subscribe to 5-minute candlestick channel for BTC
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
            # Print heartbeats or ping acknowledgments to prove data is flowing
            if "candlestick_5m" in data.get("channel", ""):
                candle = data.get('data', {})
                if candle.get('closed'):
                    print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Closed 5m Candle Received!")
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
            print(f"Error parsing message: {err}")

    def on_error(ws, error):
        print(f"WebSocket error: {error}")

    def on_close(ws, code, msg):
        print("Connection lost. Reconnecting in 5 seconds...")
        time.sleep(5)
        start_websocket_stream(df_historical)

    ws_app = websocket.WebSocketApp(WS_URL, on_open=on_open, on_message=on_message, on_error=on_error, on_close=on_close)
    ws_app.run_forever(ping_interval=30, ping_timeout=10)

if __name__ == "__main__":
    print("Initializing Live Trading Program Structure...")
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
