import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import requests
import time

# ---------------------------------------------------------
# 1. FETCH 10,000 BINANCE CANDLES (OPTIMIZED FOR MEMORY)
# ---------------------------------------------------------
def fetch_binance_candles(symbol="BTCUSDT", interval="5m", total_needed=10000):
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
            print("API Error or rate limit reached. Stopping pagination.")
            break
            
        all_data = data + all_data
        end_time = data[0][0] - 1 
        print(f"Loaded cumulative candles: {len(all_data)}")
        time.sleep(0.2)
        
    df = pd.DataFrame(all_data, columns=[
        'open_time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'
    ])
    
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(np.float32) # Use float32 to cut RAM usage in half
        
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    return df[['open_time', 'open', 'high', 'low', 'close', 'volume']].tail(total_needed).reset_index(drop=True)

df = fetch_binance_candles(symbol="BTCUSDT", interval="5m", total_needed=10000)
print(f"Successfully loaded dataset of size: {len(df)}")

# ---------------------------------------------------------
# 2. DATA PREPROCESSING & ROLLING WINDOW CONFIGURATION
# ---------------------------------------------------------
features = ['open', 'high', 'low', 'close', 'volume']
data_raw = df[features].values

train_size = 9500
pred_horizon = 250

mean = data_raw[:train_size].mean(axis=0)
std = data_raw[:train_size].std(axis=0)
std[std == 0] = 1e-5
data_normalized = (data_raw - mean) / std

def create_sequences(data, input_window=300, horizon=250):
    X, Y = [], []
    for i in range(len(data) - input_window - horizon + 1):
        X.append(data[i : i + input_window])
        Y.append(data[i + input_window : i + input_window + horizon])
    return np.array(X, dtype=np.float32), np.array(Y, dtype=np.float32)

INPUT_WINDOW = 300  # Reduced input window context to save memory
X_all, Y_all = create_sequences(data_normalized, input_window=INPUT_WINDOW, horizon=pred_horizon)
print(f"Total structured sequences built: {len(X_all)}")

max_train_idx = min(9200, len(X_all) - pred_horizon - 1)
train_X = torch.tensor(X_all[:max_train_idx])
train_Y = torch.tensor(Y_all[:max_train_idx])

# ---------------------------------------------------------
# 3. TRANSFORMER ARCHITECTURE
# ---------------------------------------------------------
class BTCTransformer(nn.Module):
    def __init__(self, feature_dim=5, d_model=32, n_heads=2, num_layers=2, output_horizon=250):
        super(BTCTransformer, self).__init__()
        self.output_horizon = output_horizon
        
        self.input_embed = nn.Linear(feature_dim, d_model)
        self.pos_encoder = nn.Parameter(torch.randn(1, 1500, d_model) * 0.01)
        
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=n_heads, dim_feedforward=64, dropout=0.1, batch_first=True
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        
        self.fc_out = nn.Sequential(
            nn.Linear(d_model, 32),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(32, 4) 
        )
        
    def forward(self, src):
        batch_size, seq_len, _ = src.shape
        x = self.input_embed(src) + self.pos_encoder[:, :seq_len, :]
        x = self.transformer_encoder(x)
        x_last = x[:, -1, :].unsqueeze(1).repeat(1, self.output_horizon, 1)
        out = self.fc_out(x_last) 
        return out

device = torch.device("cpu")
print(f"Using compute device: {device}")

model = BTCTransformer(feature_dim=5, output_horizon=pred_horizon).to(device)
criterion = nn.MSELoss()
optimizer = optim.AdamW(model.parameters(), lr=0.0005, weight_decay=1e-4)

# ---------------------------------------------------------
# 4. INITIAL TRAINING
# ---------------------------------------------------------
print("\n--- Phase 1: Initial Training on Historical Data ---")
train_dataset = TensorDataset(train_X, train_Y[:, :, :4]) 
train_loader = DataLoader(train_dataset, batch_size=32, shuffle=False) # Smaller batch size to prevent spikes

model.train()
epochs = 2
for epoch in range(epochs):
    epoch_loss = 0
    for batch_x, batch_y in train_loader:
        optimizer.zero_grad()
        predictions = model(batch_x)
        loss = criterion(predictions, batch_y)
        
        if torch.isnan(loss):
            continue
            
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=0.5)
        optimizer.step()
        epoch_loss += loss.item()
        
    print(f"Epoch {epoch+1}/{epochs} | Training Loss (MSE): {epoch_loss / len(train_loader):.4f}")

# ---------------------------------------------------------
# 5. LIVE INCREMENTAL RE-LEARNING & PREDICTION
# ---------------------------------------------------------
print("\n--- Phase 2: Live Incremental Re-learning & Final Prediction ---")
model.train() 

eval_idx = len(X_all) - 1
test_x = torch.tensor(X_all[eval_idx:eval_idx+1])
actual_y_normalized = torch.tensor(Y_all[eval_idx:eval_idx+1, :, :4])

predicted_normalized = model(test_x)

loss = criterion(predicted_normalized, actual_y_normalized)
if not torch.isnan(loss):
    optimizer.zero_grad()
    loss.backward()
    torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=0.5)
    optimizer.step()
    print(f"Online Re-learning Step Completed. Adaptation Loss: {loss.item():.4f}")

pred_np = predicted_normalized.detach().numpy()[0]
actual_np = actual_y_normalized.detach().numpy()[0]

mean_ohlc = mean[:4]
std_ohlc = std[:4]

pred_denorm = (pred_np * std_ohlc) + mean_ohlc
actual_denorm = (actual_np * std_ohlc) + mean_ohlc

comparison_df = pd.DataFrame({
    'Candle_Index': range(1, pred_horizon + 1),
    'Pred_Close': pred_denorm[:, 3],
    'Actual_Close': actual_denorm[:, 3],
})
comparison_df['Close_Error_%'] = (np.abs(comparison_df['Pred_Close'] - comparison_df['Actual_Close']) / comparison_df['Actual_Close']) * 100

print("\n--- Sample Comparison Table (First 10 Candles) ---")
print(comparison_df.head(10).to_string(index=False))
comparison_df.to_csv("btc_transformer_10k_predictions.csv", index=False)
print("\nSaved successfully to 'btc_transformer_10k_predictions.csv'.")
