import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
import requests

# ---------------------------------------------------------
# 1. FETCH HISTORICAL DATA FROM BINANCE (or synthetic simulation)
# ---------------------------------------------------------
def fetch_binance_candles(symbol="BTCUSDT", interval="5m", limit=25000):
    """
    Fetches historical OHLCV candles from Binance public API.
    """
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    response = requests.get(url)
    data = response.json()
    
    # Columns: Open time, Open, High, Low, Close, Volume, ...
    df = pd.DataFrame(data, columns=[
        'open_time', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'
    ])
    
    # Convert types to float
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
        
    df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
    return df[['open_time', 'open', 'high', 'low', 'close', 'volume']]

print("Fetching Binance BTC/USDT data...")
df = fetch_binance_candles(symbol="BTCUSDT", interval="5m", limit=25000)
print(f"Loaded {len(df)} candles successfully.")

# ---------------------------------------------------------
# 2. DATA PREPROCESSING & ROLLING WINDOW CREATION
# ---------------------------------------------------------
features = ['open', 'high', 'low', 'close', 'volume']
data_raw = df[features].values

# Normalize data (Z-score normalization based on training history to prevent lookahead leakage)
train_size = 24750
pred_horizon = 250

mean = data_raw[:train_size].mean(axis=0)
std = data_raw[:train_size].std(axis=0)
data_normalized = (data_raw - mean) / std

def create_sequences(data, input_window=500, horizon=250):
    X, Y = [], []
    for i in range(len(data) - input_window - horizon + 1):
        X.append(data[i : i + input_window])
        Y.append(data[i + input_window : i + input_window + horizon])
    return np.array(X), np.array(Y)

INPUT_WINDOW = 500  # Past candles used as context
X_all, Y_all = create_sequences(data_normalized, input_window=INPUT_WINDOW, horizon=pred_horizon)

# Split into Initial Train set (24,750 candles worth of sequences) and Real-time/Testing set
train_X = torch.tensor(X_all[:24000], dtype=torch.float32)
train_Y = torch.tensor(Y_all[:24000], dtype=torch.float32)

# ---------------------------------------------------------
# 3. TRANSFORMER MODEL ARCHITECTURE
# ---------------------------------------------------------
class BTCTransformer(nn.Module):
    def __init__(self, feature_dim=5, d_model=64, n_heads=4, num_layers=2, output_horizon=250):
        super(BTCTransformer, self).__init__()
        self.feature_dim = feature_dim
        self.output_horizon = output_horizon
        
        # Linear projection to model dimension
        self.input_embed = nn.Linear(feature_dim, d_model)
        
        # Positional Encoding
        self.pos_encoder = nn.Parameter(torch.randn(1, 2000, d_model) * 0.01)
        
        # Transformer Encoder Layers
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=n_heads, dim_feedforward=128, dropout=0.1, batch_first=True
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        
        # Output head mapping back to OHLC (4 features per candle * horizon)
        self.fc_out = nn.Sequential(
            nn.Linear(d_model, 64),
            nn.ReLU(),
            nn.Dropout(0.1),
            nn.Linear(64, 4) # Predicting Open, High, Low, Close
        )
        
    def forward(self, src):
        batch_size, seq_len, _ = src.shape
        x = self.input_embed(src) + self.pos_encoder[:, :seq_len, :]
        x = self.transformer_encoder(x)
        
        # Take the representation of the last token in the sequence to predict future path
        # Or decode iteratively. Here we project sequence output to match horizon steps.
        # For simplicity and multi-step direct forecast:
        x_last = x[:, -1, :].unsqueeze(1).repeat(1, self.output_horizon, 1)
        out = self.fc_out(x_last) # Shape: [Batch, Horizon, 4 (OHLC)]
        return out

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model = BTCTransformer(feature_dim=5, output_horizon=pred_horizon).to(device)
criterion = nn.MSELoss()
optimizer = optim.AdamW(model.parameters(), lr=0.001, weight_decay=1e-4) # Weight decay prevents overfitting

# ---------------------------------------------------------
# 4. INITIAL TRAINING ON HISTORICAL DATA
# ---------------------------------------------------------
print("\n--- Phase 1: Initial Training on Historical Data ---")
train_dataset = TensorDataset(train_X, train_Y[:, :, :4]) # Target OHLC (first 4 features)
train_loader = DataLoader(train_dataset, batch_size=32, shuffle=False) # Chronological order maintained

model.train()
for epoch in range(3): # Epochs kept low to prevent overfitting on historical noise
    epoch_loss = 0
    for batch_x, batch_y in train_loader:
        batch_x, batch_y = batch_x.to(device), batch_y.to(device)
        
        optimizer.zero_grad()
        predictions = model(batch_x)
        loss = criterion(predictions, batch_y)
        loss.backward()
        
        # Gradient clipping to stabilize Transformer weights
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()
        
        epoch_loss += loss.item()
    print(f"Epoch {epoch+1}/3 | Training Loss (MSE): {epoch_loss / len(train_loader):.4f}")

# ---------------------------------------------------------
# 5. CONTINUAL RE-LEARNING & EVALUATION (ONLINE BACKPROP)
# ---------------------------------------------------------
print("\n--- Phase 2: Live Incremental Re-learning & Evaluation on Next Candles ---")

model.train() # Keep in training mode to allow weight updates
results_log = []

# Simulate moving forward step-by-step through the remaining unseen 250 candles
start_idx = 24000
test_x = torch.tensor(X_all[start_idx:start_idx+1], dtype=torch.float32).to(device)
actual_y_normalized = torch.tensor(Y_all[start_idx:start_idx+1, :, :4], dtype=torch.float32).to(device)

# 1. Make Prediction before seeing the update feedback
predicted_normalized = model(test_x)

# 2. Perform Immediate Backpropagation / Weight Update using actual vs predicted feedback loop
optimizer.zero_grad()
loss = criterion(predicted_normalized, actual_y_normalized)
loss.backward()
torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
optimizer.step() # Weights updated based on error!
print(f"Online Re-learning Step Completed. Adaptation Loss: {loss.item():.4f}")

# 3. Denormalize Predictions and Actuals for Comparison Table
pred_np = predicted_normalized.detach().cpu().numpy()[0]
actual_np = actual_y_normalized.detach().cpu().numpy()[0]

# Unscale OHLC values back to original BTC price scale
mean_ohcl = mean[:4]
std_ohlc = std[:4]

pred_denorm = (pred_np * std_ohlc) + mean_ohcl
actual_denorm = (actual_np * std_ohlc) + mean_ohcl

# Construct Comparison Table for the 250 predicted candles
comparison_df = pd.DataFrame({
    'Candle_Index': range(1, pred_horizon + 1),
    'Pred_Open': pred_denorm[:, 0],
    'Actual_Open': actual_denorm[:, 0],
    'Pred_High': pred_denorm[:, 1],
    'Actual_High': actual_denorm[:, 1],
    'Pred_Low': pred_denorm[:, 2],
    'Actual_Low': actual_denorm[:, 2],
    'Pred_Close': pred_denorm[:, 3],
    'Actual_Close': actual_denorm[:, 3],
})

# Calculate Absolute & Percentage Differences
comparison_df['Close_Diff'] = comparison_df['Pred_Close'] - comparison_df['Actual_Close']
comparison_df['Close_Error_%'] = (np.abs(comparison_df['Close_Diff']) / comparison_df['Actual_Close']) * 100

print("\n--- Sample Comparison Table (First 10 of 250 Predicted Candles) ---")
print(comparison_df[['Candle_Index', 'Pred_Close', 'Actual_Close', 'Close_Error_%']].head(10).to_string(index=False))

# Save full results to CSV
comparison_df.to_csv("btc_transformer_predictions_vs_actuals.csv", index=False)
print("\nFull 250 candle comparison table saved to 'btc_transformer_predictions_vs_actuals.csv'.")
