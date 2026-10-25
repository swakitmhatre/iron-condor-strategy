import time
import os
import ccxt
import pandas as pd
import numpy as np
import torch
import torch.nn as nn

# =====================================================================
# CONFIGURATION & CREDENTIALS
# =====================================================================
# YOUR ACTUAL DELTA INDIA API CREDENTIALS FOR TRADING
API_KEY = "SxgQK4eNLqtrF54umC4IjjbVUCnrh8"
API_SECRET = "Ivu3wUr71sn2dmca21VPI4W0dhiqOcnxpBvrVUAsFlKHj4qybWvT2WVaNA1S"

SYMBOL = 'BTC/USDT:USDT'  # Delta India futures contract symbol in CCXT
CONTRACT_SIZE = 1         # Minimum contract unit size

# 1. Initialize Binance (Public only - used for smooth historical context)
binance_exchange = ccxt.binance({'enableRateLimit': True})

# 2. Initialize Delta India (Authenticated with your keys for secure live trading)
delta_exchange = ccxt.delta({
    'apiKey': DELTA_API_KEY,
    'secret': DELTA_API_SECRET,
    'enableRateLimit': True,
    'options': {'defaultType': 'future'}
})

# =====================================================================
# TRANSFORMER MULTI-STEP OHLC FORECASTER MODEL
# =====================================================================
class OHLCTransformerForecaster(nn.Module):
    def __init__(self, feature_size=5, horizon=5, d_model=64, num_layers=2):
        super(OHLCTransformerForecaster, self).__init__()
        self.horizon = horizon
        self.input_embed = nn.Linear(feature_size, d_model)
        encoder_layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=4, dropout=0.1, batch_first=True)
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.decoder = nn.Linear(d_model, horizon * 4) # Predicts 5 future candles * 4 features (OHLC)

    def forward(self, src):
        x = self.input_embed(src)
        x = self.transformer_encoder(x)
        out = self.decoder(x[:, -1, :])
        return out.view(-1, self.horizon, 4)

# Initialize Model in Evaluation Mode
model = OHLCTransformerForecaster(feature_size=5, horizon=5)
model.eval()

def load_initial_history():
    """Loads baseline history once on startup so the Transformer has context."""
    print("Loading historical baseline data for Transformer context...")
    try:
        ohlcv = binance_exchange.fetch_ohlcv('BTC/USDT', timeframe='5m', limit=1000)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        print(f"-> Successfully loaded {len(df)} baseline candles.")
        return df
    except Exception as e:
        print(f"-> History load error: {e}")
        return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

def place_delta_live_order(side, size=CONTRACT_SIZE):
    """
    AUTHENTICATED ORDER PLACEMENT ON DELTA INDIA:
    Uses your Delta API key and secret to sign and execute market orders securely.
    """
    try:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S']}] Attempting to place {side.upper()} order on Delta Exchange...")
        order = delta_exchange.create_order(
            symbol=SYMBOL,
            type='market',
            side=side,
            amount=size
        )
        print(f"-> SUCCESS! Delta Order Executed. Order ID: {order.get('id')}")
    except Exception as e:
        print(f"-> DELTA ORDER ERROR HANDLED: {e}")

def update_rolling_data(df: pd.DataFrame):
    """Appends the newest closed 5-minute candle in-memory efficiently."""
    try:
        latest = binance_exchange.fetch_ohlcv('BTC/USDT', timeframe='5m', limit=2)
        new_row = pd.DataFrame(latest[-1:], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        if not df.empty and new_row.iloc[0]['timestamp'] <= df.iloc[-1]['timestamp']:
            df.iloc[-1, df.columns.get_loc('close')] = new_row.iloc[0]['close']
        else:
            df = pd.concat([df, new_row], ignore_index=True)
            if len(df) > 5000:
                df = df.iloc[-5000:].reset_index(drop=True)
        return df
    except Exception as e:
        print(f"-> Candle append error: {e}")
        return df

def run_transformer_and_indicators(df: pd.DataFrame):
    """Calculates indicators and runs Transformer inference to output upcoming 5 candle OHLC."""
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

    # Prepare features for Transformer input window (last 30 candles)
    feature_cols = ['open', 'high', 'low', 'close', 'volume']
    recent_data = df[feature_cols].tail(30).values
    
    mean = recent_data.mean(axis=0)
    std = recent_data.std(axis=0) + 1e-5
    norm_data = (recent_data - mean) / std
    
    tensor_input = torch.tensor(norm_data, dtype=torch.float32).unsqueeze(0)
    
    with torch.no_grad():
        pred_norm = model(tensor_input).squeeze(0).numpy() # Shape: (5, 4)
        
    pred_actual = (pred_norm * std[:4]) + mean[:4]
    
    # Print out upcoming 5 candles' predicted OHLC dynamically every loop
    print("-" * 55)
    print(">>> TRANSFORMER PREDICTED OHLC FOR NEXT 5 CANDLES:")
    for step in range(5):
        o, h, l, c = pred_actual[step]
        print(f"    Candle +{step+1} -> Open: {o:.2f} | High: {h:.2f} | Low: {l:.2f} | Close: {c:.2f}")
    print("-" * 55)
    
    next_predicted_close = pred_actual[-1][3]
    signal = "HOLD"
    if next_predicted_close > latest['close'] and rsi_val < 45:
        signal = "BUY"
    elif next_predicted_close < latest['close'] and rsi_val > 55:
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
    print("Initializing Live Delta Transformer Engine with Authentication...")
    historical_df = load_initial_history()
    
    while True:
        status = check_strategy_status()
        print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Status: [{status}]")
        
        if status == "RUNNING":
            historical_df = update_rolling_data(historical_df)
            signal = run_transformer_and_indicators(historical_df)
            print(f"-> Model Signal Evaluation: {signal}")
            
            # Execute real trades using authenticated Delta API client
            if signal == "BUY":
                print(">>> Executing BUY order on Delta Exchange...")
                place_delta_live_order("buy", CONTRACT_SIZE)
            elif signal == "SELL":
                print(">>> Executing SELL order on Delta Exchange...")
                place_delta_live_order("sell", CONTRACT_SIZE)
            else:
                print("-> Model signals HOLD. No trade placed.")
        else:
            print("-> Strategy is currently STOPPED via control switch.")
            
        print("-> Sleeping for 5 minutes until the next candle boundary...\n")
        time.sleep(300)
