
import time
import os
import ccxt
import pandas as pd

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

def get_real_market_data():
    try:
        exchange.load_markets()
        
        # 1. Grab the instant, raw live ticker price right now (changes every second!)
        ticker = exchange.fetch_ticker(SYMBOL)
        current_live_price = ticker['last']
        
        # 2. Grab historical 5m candles for indicators
        ohlcv = exchange.fetch_ohlcv(SYMBOL, timeframe='5m', limit=300)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        print(f"-> REAL-TIME TICKER PRICE: {current_live_price} | Last 5m Candle Close: {df.iloc[-1]['close']}")
        return df
    except Exception as e:
        print(f"-> Fetch Error: {e}. Retrying next cycle...")
        return None

def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
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
    
    print(f"-> Indicator Check | Close: {latest['close']} | EMA200: {ema_val:.2f} | RSI: {rsi_val:.2f}")
    
    if latest['close'] > ema_val and rsi_val < 40:
        print(">>> Signal Triggered: Long Setup. Placing order...")
        place_live_order("buy", CONTRACT_SIZE)
    elif latest['close'] < ema_val and rsi_val > 60:
        print(">>> Signal Triggered: Short Setup. Placing order...")
        place_live_order("sell", CONTRACT_SIZE)
    else:
        print("-> No trade setup matched. Holding position.")

if __name__ == "__main__":
    print("Initializing Live Volatility Ticker Engine...")
    while True:
        df = get_real_market_data()
        if df is not None and not df.empty:
            df = calculate_indicators(df)
            evaluate_and_trade(df)
        print("-> Sleeping for 5 minutes...\n")
        time.sleep(300)
EOF
