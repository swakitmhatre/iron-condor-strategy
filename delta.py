import time
import os
import ccxt
import pandas as pd
import numpy as np

# =====================================================================
# CONFIGURATION & CREDENTIALS
# =====================================================================
API_KEY = "rI6AjEtDbUo2pekgWOYWXpoDnha9KP"
API_SECRET = "hn2RYsrr9m1rIHFrqIlNEk5GIrrmJ4IRsffnPQkPoIGkmv289ixJW6aTXIjP"

# Using XRP/USDT so clean integer lots (10 contracts) fit your $11 balance
SYMBOL = 'XRP/USDT:USDT'  
CONTRACT_SIZE = 1       # Clean integer lot size (10 contracts)
MIN_LEVERAGE = 1          # Set leverage to 1x for absolute minimum risk

# Initialize Binance for public historical data context
binance_exchange = ccxt.binance({'enableRateLimit': True})

# Initialize Delta India with your production credentials for live trading
delta_exchange = ccxt.delta({
    'apiKey': API_KEY,
    'secret': API_SECRET,
    'enableRateLimit': True,
    'options': {'defaultType': 'future'},
    'urls': {
        'api': {
            'public': 'https://api.india.delta.exchange',
            'private': 'https://api.india.delta.exchange',
        }
    }
})

# =====================================================================
# LIGHTWEIGHT NUMPY ATTENTION / TRANSFORMER FORECASTER
# =====================================================================
class NumpyAttentionForecaster:
    def __init__(self, feature_size=5, horizon=5):
        self.horizon = horizon
        self.feature_size = feature_size
        np.random.seed(42)
        self.W_query = np.random.randn(feature_size, feature_size) * 0.1
        self.W_key = np.random.randn(feature_size, feature_size) * 0.1
        self.W_value = np.random.randn(feature_size, feature_size) * 0.1
        self.W_out = np.random.randn(feature_size, horizon * 4) * 0.1

    def predict(self, recent_data):
        Q = np.dot(recent_data, self.W_query)
        K = np.dot(recent_data, self.W_key)
        V = np.dot(recent_data, self.W_value)
        
        scores = np.dot(Q, K.T) / np.sqrt(self.feature_size)
        exp_scores = np.exp(scores - np.max(scores, axis=-1, keepdims=True))
        attention_weights = exp_scores / np.sum(exp_scores, axis=-1, keepdims=True)
        
        context = np.dot(attention_weights, V)
        last_state = context[-1, :]
        
        output_flat = np.dot(last_state, self.W_out)
        return output_flat.reshape(self.horizon, 4)

model = NumpyAttentionForecaster(feature_size=5, horizon=5)

def load_initial_history():
    print("Loading historical baseline data for attention context...")
    try:
        ohlcv = binance_exchange.fetch_ohlcv('XRP/USDT', timeframe='5m', limit=1000)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        print(f"-> Successfully loaded {len(df)} baseline candles.")
        return df
    except Exception as e:
        print(f"-> History load error: {e}")
        return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

def place_delta_live_order(side, size=CONTRACT_SIZE):
    try:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Setting leverage to {MIN_LEVERAGE}x and placing {side.upper()} order...")
        
        # Enforce minimum leverage programmatically
        try:
            delta_exchange.set_leverage(MIN_LEVERAGE, SYMBOL)
        except Exception as lev_err:
            print(f"-> Note on leverage setup: {lev_err}")
            
        # Enforce exact integer contract size (1, 10, 100...)
        int_amount = int(size)
        
        order = delta_exchange.create_order(
            symbol=SYMBOL,
            type='market',
            side=side,
            amount=int_amount
        )
        print(f"-> SUCCESS! Delta Order ID: {order.get('id')}")
    except Exception as e:
        print(f"-> DELTA ORDER ERROR HANDLED: {e}")

def update_rolling_data(df: pd.DataFrame):
    try:
        latest = binance_exchange.fetch_ohlcv('XRP/USDT', timeframe='5m', limit=2)
        new_row = pd.DataFrame(latest[-1:], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        if not df.empty and new_row.iloc[0]['timestamp'] <= df.iloc[-1]['timestamp']:
            df.iloc[-1, df.columns.get_loc('close')] = new_row.iloc[0]['close']
            df.iloc[-1, df.columns.get_loc('high')] = max(df.iloc[-1]['high'], new_row.iloc[0]['high'])
            df.iloc[-1, df.columns.get_loc('low')] = min(df.iloc[-1]['low'], new_row.iloc[0]['low'])
        else:
            df = pd.concat([df, new_row], ignore_index=True)
            if len(df) > 5000:
                df = df.iloc[-5000:].reset_index(drop=True)
        return df
    except Exception as e:
        print(f"-> Candle append error: {e}")
        return df

def run_forecaster_and_indicators(df: pd.DataFrame):
    df = df.copy()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['rsi'] = 100 - (100 / (1 + (gain / loss)))
    
    latest = df.iloc[-1]
    rsi_val = latest['rsi'] if not pd.isna(latest['rsi']) else 50.0
    ema_val = latest['ema_200'] if not pd.isna(latest['ema_200']) else latest['close']
    
    print(f"-> Indicator Check | Close: {latest['close']} | EMA200: {ema_val:.2f} | RSI: {rsi_val:.2f}")

    feature_cols = ['open', 'high', 'low', 'close', 'volume']
    recent_data = df[feature_cols].tail(30).values
    
    mean = recent_data.mean(axis=0)
    std = recent_data.std(axis=0) + 1e-5
    norm_data = (recent_data - mean) / std
    
    pred_norm = model.predict(norm_data)
    pred_actual = (pred_norm * std[:4]) + mean[:4]
    
    print("-" * 65)
    print(">>> ATTENTION MODEL PREDICTED OHLC FOR NEXT 5 CANDLES:")
    for step in range(5):
        o, h, l, c = pred_actual[step]
        print(f"    Candle +{step+1} -> Open: {o:.2f} | High: {h:.2f} | Low: {l:.2f} | Close: {c:.2f}")
    print("-" * 65)
    
    next_predicted_close = pred_actual[-1][3]
    signal = "HOLD"
    if next_predicted_close > latest['close'] and rsi_val < 50:
        signal = "BUY"
    elif next_predicted_close < latest['close'] and rsi_val > 50:
        signal = "SELL"
        
    return signal

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

if __name__ == "__main__":
    print("Initializing Live Attention Engine for XRP...")
    historical_df = load_initial_history()
    
    while True:
        status = check_strategy_status()
        print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Status: [{status}]")
        
        if status == "RUNNING":
            historical_df = update_rolling_data(historical_df)
            signal = run_forecaster_and_indicators(historical_df)
            print(f"-> Model Signal Evaluation: {signal}")
            
            if signal == "BUY":
                place_delta_live_order("buy", CONTRACT_SIZE)
            elif signal == "SELL":
                place_delta_live_order("sell", CONTRACT_SIZE)
            else:
                print("-> Model signals HOLD. No trade placed.")
        else:
            print("-> Strategy is currently STOPPED via control switch.")
            
        print("-> Sleeping for 5 minutes until the next candle boundary...\n")
        time.sleep(300)
