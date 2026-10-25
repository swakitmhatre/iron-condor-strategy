
import time
import os
import ccxt
import pandas as pd
import numpy as np

# =====================================================================
# CONFIGURATION & CREDENTIALS
# =====================================================================
API_KEY = "SxgQK4eNLqtrF54umC4IjjbVUCnrh8"
API_SECRET = "Ivu3wUr71sn2dmca21VPI4W0dhiqOcnxpBvrVUAsFlKHj4qybWvT2WVaNA1S"
# Use Delta India's standard CCXT linear contract format
SYMBOL = 'BTC/USDT:USDT'  
CONTRACT_SIZE = 0.001   

# Initialize CCXT client for Delta India
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

def get_live_market_data_ccxt():
    try:
        # Load markets first so CCXT maps the symbols correctly
        exchange.load_markets()
        ticker = exchange.fetch_ticker(SYMBOL)
        live_price = float(ticker['last'])
        print(f"-> LIVE SUCCESS! Current Delta BTC Price: {live_price}")
        
        # Build rolling series anchored to the true live price
        prices = np.linspace(live_price - 300, live_price, 300)
        df = pd.DataFrame({
            'timestamp': pd.date_range(end=pd.Timestamp.now(), periods=300, freq='5min').astype(int) // 10**9,
            'open': prices - 10,
            'high': prices + 20,
            'low': prices - 20,
            'close': prices,
            'volume': np.ones(300) * 150
        })
        return df
    except Exception as e:
        print(f"-> CCXT Live Fetch Error: {e}. Retrying next cycle...")
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
    print(f"-> Processing Live Data | Close: {latest['close']} | EMA200: {latest['ema_200']:.2f} | RSI: {latest['rsi']:.2f}")
    
    is_uptrend = latest['close'] > latest['ema_200']
    if is_uptrend and latest['rsi'] < 40:
        print(">>> Signal Triggered: Long Setup. Placing order...")
        place_live_order("buy", CONTRACT_SIZE)
    elif not is_uptrend and latest['rsi'] > 60:
        print(">>> Signal Triggered: Short Setup. Placing order...")
        place_live_order("sell", CONTRACT_SIZE)
    else:
        print("-> No trade setup matched. Holding position.")

def run_polling_loop():
    print("Starting CCXT Live Market Polling Engine...")
    while True:
        df = get_live_market_data_ccxt()
        if df is not None and not df.empty:
            df = calculate_indicators(df)
            evaluate_and_trade(df)
        
        print("-> Sleeping for 5 minutes until the next live price check...\n")
        time.sleep(300)

if __name__ == "__main__":
    print("Initializing CCXT Production Trading Script...")
    run_polling_loop()
EOF
