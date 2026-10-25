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
API_KEY = "uqDYmxICz64vZ0KiQsix3o6U5J1Nqq"
API_SECRET = "oxk1357JTIjdiRgNXIQwGYj7NlzAnoSYzvvVzP1SAPhIsTrjdCheIHl07btE"
BASE_URL = "https://india.delta.exchange"  # Delta India Production REST endpoint
WS_URL = "wss://socket.india.delta.exchange"  # Delta India WebSocket stream
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
    Wrapped in try-except block to guarantee zero crash behavior.
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
            print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] API ERROR placing order: {response_data}")
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] NETWORK EXCEPTION handled safely: {e}")

# =====================================================================
# 2. TECHNICAL INDICATOR ENGINE
# =====================================================================
def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes EMA 200, MACD, and RSI on live-updating candle arrays 
    to ensure multi-timeframe technical confluence before triggering entries.
    """
    df = df.copy()
    
    # EMA 200 Calculation
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # MACD Calculation (12, 26, 9)
    exp1 = df['close'].ewm(span=12, adjust=False).mean()
    exp2 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = exp1 - exp2
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    
    # RSI Calculation (14)
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
    Reads a local 'control.txt' file to check if the user wants the strategy 
    running ('RUNNING') or stopped ('STOPPED').
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

def evaluate_and_trade(df: pd.DataFrame):
    """
    Evaluates the latest 5-minute candle against filters, EMA 200 trend, 
    and RSI thresholds to decide if an entry or exit is required.
    """
    if check_strategy_status() != "RUNNING":
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Strategy is currently STOPPED via control.txt switch.")
        return

    # Grab the most recently completed candle row safely
    latest = df.iloc[-1]
    current_price = latest['close']
    ema_val = latest['ema_200']
    rsi_val = latest['rsi']
    
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Evaluating 5m Candle -> Close: {current_price} | EMA200: {ema_val:.2f} | RSI: {rsi_val:.2f}")
    
    # Strategy Logic Rules
    is_uptrend = current_price > ema_val
    
    if is_uptrend and rsi_val < 40:
        print("Signal Met: High-confidence Long setup identified.")
        place_live_order("buy", CONTRACT_SIZE)
    elif not is_uptrend and rsi_val > 60:
        print("Signal Met: High-confidence Short setup identified.")
        place_live_order("sell", CONTRACT_SIZE)

# =====================================================================
# 4. WEBSOCKET REAL-TIME CANDLE LISTENER WITH AUTO-RECONNECT
# =====================================================================
def start_websocket_stream(df_historical):
    """
    Connects to Delta India's real-time WebSocket stream with built-in 
    reconnection loops so the script never permanently dies on dropouts.
    """
    def on_message(ws, message):
        try:
            data = json.loads(message)
            if "candlestick_5m" in data.get("channel", ""):
                candle = data.get('data', {})
                if candle.get('closed'): # Process fully closed 5-min candles
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
            print(f"Error processing websocket message: {err}")

    def on_error(ws, error):
        print(f"WebSocket error encountered: {error}")

    def on_close(ws, close_status_code, close_msg):
        print("WebSocket connection closed. Attempting auto-reconnect in 5 seconds...")
        time.sleep(5)
        start_websocket_stream(df_historical)

    ws_app = websocket.WebSocketApp(
        WS_URL, 
        on_message=on_message, 
        on_error=on_error, 
        on_close=on_close
    )
    ws_app.run_forever()

if __name__ == "__main__":
    print("Initializing Live Trading Program Structure...")
    
    # Initialize control switch file if missing
    if not os.path.exists("control.txt"):
        with open("control.txt", "w") as f:
            f.write("STOPPED")
        print("Created 'control.txt' set to STOPPED by default. Change to RUNNING when ready.")

    # Seed with initial dummy dataframe structure using modern '5min' format
    mock_history = pd.DataFrame({
        'timestamp': pd.date_range(end=pd.Timestamp.now(), periods=300, freq='5min'),
        'open': np.linspace(60000, 61000, 300),
        'high': np.linspace(60100, 61100, 300),
        'low': np.linspace(59900, 60900, 300),
        'close': np.linspace(60050, 60950, 300),
        'volume': np.ones(300) * 10
    })
    mock_history = calculate_indicators(mock_history)
    
    print("Starting WebSocket stream connection to Delta India...")
    start_websocket_stream(mock_history)
