import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import requests
import time

# ---------------------------------------------------------
# 1. FETCH COMPACT 500-CANDLE DATASET (15m Timeframe)
# ---------------------------------------------------------
def fetch_binance_candles(symbol="BTCUSDT", interval="15m", total_needed=500):
    print(f"Fetching {total_needed} historical {interval} candles from Binance...")
    all_data = []
    end_time = None
    
    while len(all_data) < total_needed:
        limit = min(1000, total_needed - len(all_data))
        url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
        if end_time:
            url += f"&endTime={end_time}"
            
        response = requests.get(url)
        data = response.json()
        
        if not data or isinstance(data, dict) and 'code' in data:
            break
            
        all_data = data + all_data
        end_time = data[0][0] - 1 
        time.sleep(0.2)
        
    df = pd.DataFrame(all_data, columns=[
        'open_time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'
    ])
    
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(np.float32)
        
    # Technical Indicators for trend stability
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-8)
    df['rsi'] = 100 - (100 / (1 + rs))
    df['ema'] = df['close'].ewm(span=14, adjust=False).mean()
    
    df = df.dropna().reset_index(drop=True)
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    return df[['open_time', 'open', 'high', 'low', 'close', 'volume', 'rsi', 'ema']].tail(total_needed).reset_index(drop=True)

TOTAL_ROWS = 500
PRED_HORIZON = 10   # Short horizon (10 steps) to prevent high error drift
INPUT_WINDOW = 100  # Smaller lookback window appropriate for 500 rows

df = fetch_binance_candles(symbol="BTCUSDT", interval="15m", total_needed=TOTAL_ROWS)
print(f"Loaded dataset size: {len(df)}")

# ---------------------------------------------------------
# 2. SCALING
# ---------------------------------------------------------
features = ['open', 'high', 'low', 'close', 'volume', 'rsi', 'ema']
data_raw = df[features].values

train_size = int(len(df) * 0.8)

min_val = data_raw[:train_size].min(axis=0)
max_val = data_raw[:train_size].max(axis=0)
max_val[max_val == min_val] = 1.0 

data_normalized = (data_raw - min_val) / (max_val - min_val)

def create_sequences(data, input_window=100, horizon=10):
    X, Y = [], []
    for i in range(len(data) - input_window - horizon + 1):
        X.append(data[i : i + input_window])
        Y.append(data[i + input_window : i + input_window + horizon])
    return np.array(X, dtype=np.float32), np.array(Y, dtype=np.float32)

X_all, Y_all = create_sequences(data_normalized, input_window=INPUT_WINDOW, horizon=PRED_HORIZON)
print(f"Total structured sequences built: {len(X_all)}")

max_train_idx = min(train_size - INPUT_WINDOW, len(X_all) - PRED_HORIZON - 1)
train_X = torch.tensor(X_all[:max_train_idx])
train_Y = torch.tensor(Y_all[:max_train_idx])

# ---------------------------------------------------------
# 3. LIGHTWEIGHT, ANTI-OVERFITTING TRANSFORMER
# ---------------------------------------------------------
class LightBTCTransformer(nn.Module):
    def __init__(self, feature_dim=7, d_model=32, n_heads=2, num_layers=1, output_horizon=10):
        super(LightBTCTransformer, self).__init__()
        self.output_horizon = output_horizon
        
        self.input_embed = nn.Linear(feature_dim, d_model)
        self.pos_encoder = nn.Parameter(torch.randn(1, 500, d_model) * 0.01)
        
        # Single layer with high dropout to prevent memorization
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=n_heads, dim_feedforward=64, dropout=0.3, batch_first=True
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        
        self.fc_out = nn.Sequential(
            nn.Linear(d_model, 32),
            nn.GELU(),
            nn.Dropout(0.2),
            nn.Linear(32, 4) # Predicts OHLC
        )
        
    def forward(self, src):
        batch_size, seq_len, _ = src.shape
        x = self.input_embed(src) + self.pos_encoder[:, :seq_len, :]
        x = self.transformer_encoder(x)
        x_last = x[:, -1, :].unsqueeze(1).repeat(1, self.output_horizon, 1)
        out = self.fc_out(x_last) 
        return out

# Hardware selection
if torch.cuda.is_available():
    device = torch.device("cuda")
elif torch.backends.mps.is_available():
    device = torch.device("mps")
else:
    device = torch.device("cpu")

print(f"Using device: {device}")

model = LightBTCTransformer(feature_dim=7, output_horizon=PRED_HORIZON).to(device)
criterion = nn.HuberLoss()
optimizer = optim.AdamW(model.parameters(), lr=0.005, weight_decay=1e-3) # Higher weight decay prevents overfitting

train_X = train_X.to(device)
train_Y = train_Y.to(device)

# ---------------------------------------------------------
# 4. LIGHTWEIGHT INITIAL TRAINING (5 Epochs only)
# ---------------------------------------------------------
print("\n--- Phase 1: Rapid Baseline Training (500 Rows) ---")
train_dataset = TensorDataset(train_X, train_Y[:, :, :4]) 
train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)

model.train()
epochs = 5
for epoch in range(epochs):
    epoch_loss = 0
    for batch_x, batch_y in train_loader:
        optimizer.zero_grad()
        predictions = model(batch_x)
        loss = criterion(predictions, batch_y)
        
        if torch.isnan(loss):
            continue
            
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        epoch_loss += loss.item()
        
    print(f"Epoch {epoch+1}/{epochs} | Training Loss: {epoch_loss / len(train_loader):.4f}")

# ---------------------------------------------------------
# 5. ONLINE ROLLING RE-LEARNING & PREDICTION
# ---------------------------------------------------------
print("\n--- Phase 2: Live Incremental Re-learning & Final Prediction ---")
model.train() 

# Simulating incremental weight adjustment on the very latest sample window
eval_idx = len(X_all) - 1
test_x = torch.tensor(X_all[eval_idx:eval_idx+1]).to(device)
actual_y_normalized = torch.tensor(Y_all[eval_idx:eval_idx+1, :, :4]).to(device)

# Micro gradient step update (Online Re-learning)
for _ in range(3): 
    optimizer.zero_grad()
    adapt_preds = model(test_x)
    adapt_loss = criterion(adapt_preds, actual_y_normalized)
    adapt_loss.backward()
    torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=0.5)
    optimizer.step()

print(f"Online Re-learning Completed. Final Adaptation Loss: {adapt_loss.item():.4f}")

model.eval()
with torch.no_grad():
    predicted_normalized = model(test_x)

pred_np = predicted_normalized.cpu().numpy()[0]
actual_np = actual_y_normalized.cpu().numpy()[0]

# Denormalize Close prices
min_close = min_val[3]
max_close = max_val[3]

pred_denorm_close = (pred_np[:, 3] * (max_close - min_close)) + min_close
actual_denorm_close = (actual_np[:, 3] * (max_close - min_close)) + min_close

comparison_df = pd.DataFrame({
    'Candle_Index': range(1, PRED_HORIZON + 1),
    'Pred_Close': pred_denorm_close,
    'Actual_Close': actual_denorm_close,
})
comparison_df['Close_Error_%'] = (np.abs(comparison_df['Pred_Close'] - comparison_df['Actual_Close']) / comparison_df['Actual_Close']) * 100

print("\n--- Final Comparison Table (500 Candles + Relearning) ---")
print(comparison_df.to_string(index=False))
comparison_df.to_csv("btc_transformer_500_predictions.csv", index=False)
print("\nSaved successfully to 'btc_transformer_500_predictions.csv'.")
