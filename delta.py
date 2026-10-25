
import time
import os
import ccxt
import pandas as pd

# =====================================================================
# CONFIGURATION & CREDENTIALS
# =====================================================================
API_KEY = "SxgQK4eNLqtrF54umC4IjjbVUCnrh8"
API_SECRET = "Ivu3wUr71sn2dmca21VPI4W0dhiqOcnxpBvrVUAsFlKHj4qybWvT2WVaNA1S"
SYMBOL = 'BTC/USDT:USDT'  
CONTRACT_SIZE = 0.001   

exchange = ccxt.delta({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

def place_live_order(side, size=CONTRACT_SIZE):
    try:
        order = exchange.create_order(symbol=SYMBOL, type='market', side=side, amount=size)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] SUCCESS: {side.upper()} order executed! Order ID: {order.get('id')}")
    except Exception as e:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] ORDER ERROR HANDLED: {e}")

def get_real_ohlcv_data():
    """Fetches real 5-minute historical candles directly from Delta Exchange via CCXT."""
    try:
        exchange.load_markets()
        # Fetch last 300 candles of 5-minute timeframe
        ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe='5m', limit=300)
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        latest_close = df.iloc[-1]['close']
        print(f"-> LIVE OHLC SUCCESS! Latest BTC Close: {latest_close}")
        return df
    except Exception as e:
        print(f"-> CCXT OHLC Fetch Error: {e}. Retrying next cycle...")
        return None

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
            f.write("RUNNING")
        return "RUNNING"
    try:
        with open("control.txt", "r") as f:
            return f.read().strip().upper()
    except:
        return "RUNNING"

def evaluate_and_trade(df: pd.DataFrame):
    status = check_strategy_status()
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Status Check: [{status}]")
    
    if status != "RUNNING":
        print("-> Strategy is currently STOPPED via control switch.")
        return

    latest = df.iloc[-1]
    rsi_val = latest['rsi'] if not pd.isna(latest['rsi']) else 50.0
    ema_val = latest['ema_200'] if not pd.isna(latest['ema_200']) else latest['close']
    
    print(f"-> Processing Real 5m Candle | Close: {latest['close']} | EMA200: {ema_val:.2f} | RSI: {rsi_val:.2f}")
    
    is_uptrend = latest['close'] > ema_val
    if is_uptrend and rsi_val < 40:
        print(">>> Signal Triggered: Long Setup. Placing order...")
        place_live_order("buy", CONTRACT_SIZE)
    elif not is_uptrend and rsi_val > 60:
        print(">>> Signal Triggered: Short Setup. Placing order...")
        place_live_order("sell", CONTRACT_SIZE)
    else:
        print("-> No trade setup matched. Holding position.")

def run_polling_loop():
    print("Starting CCXT Real-OHLC Polling Engine...")
    while True:
        df = get_real_ohlcv_data()
        if df is not None and not df.empty:
            df = calculate_indicators(df)
            evaluate_and_trade(df)
        
        print("-> Sleeping for 5 minutes until the next candle check...\n")
        time.sleep(300)

if __name__ == "__main__":
    print("Initializing CCXT Production Trading Script...")
    run_polling_loop()
EOF
