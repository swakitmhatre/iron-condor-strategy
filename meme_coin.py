import time
import requests
import pandas as pd
import numpy as np
from lightweight_charts import Chart

# --- CONFIGURATION ---
SYMBOL = "PEPEUSDT"
FETCH_INTERVAL_SEC = 300  # 5 minutes


# --- 1. DATA FETCHING & INDICATOR ENGINE ---
def fetch_and_calculate_data(symbol=SYMBOL, limit=120):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=5m&limit={limit}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        df = pd.DataFrame(data, columns=[
            "time", "open", "high", "low", "close", "volume",
            "close_time", "qav", "num_trades", "tbb", "tbq", "ignore"
        ])
        df["time"] = pd.to_datetime(df["time"], unit="ms")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
    except Exception as e:
        print(f"[WARN] Fetch failed ({e}), using fallback generator...")
        times = pd.date_range(end=pd.Timestamp.now(), periods=limit, freq="5min")
        base = 0.0000090
        close = base + np.cumsum(np.random.normal(0, 0.0000001, limit))
        open_p = close - np.random.normal(0, 0.00000005, limit)
        high = np.maximum(open_p, close) + abs(np.random.normal(0, 0.00000005, limit))
        low = np.minimum(open_p, close) - abs(np.random.normal(0, 0.00000005, limit))
        vol = np.random.randint(10000, 100000, limit)
        df = pd.DataFrame({"time": times, "open": open_p, "high": high, "low": low, "close": close, "volume": vol})

    # --- Indicators ---
    # 1. Supertrend (10, 3)
    atr = (df["high"] - df["low"]).rolling(10).mean()
    hl2 = (df["high"] + df["low"]) / 2
    df["supertrend"] = hl2 - (3 * atr)

    # 2. RSI (14)
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    df["rsi"] = 100 - (100 / (1 + rs))

    # 3. MACD (12, 26, 9)
    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    return df.dropna().reset_index(drop=True)


# --- 2. MAIN APPLICATION ---
def main():
    print(f"=== INITIALIZING TRADINGVIEW ENGINE FOR {SYMBOL} ===")
    
    # Create Main Chart Layout (Candlesticks)
    chart = Chart(inner_width=1, inner_height=0.6)
    
    # Correct API call for title/watermark overlay
    chart.watermark(f"{SYMBOL} 5m Engine", color="rgba(180, 180, 240, 0.6)")
    chart.legend(visible=True)
    chart.time_scale(visible=False)

    # Create Sub-pane for RSI (Synchronized timescale)
    rsi_sub = chart.create_subchart(width=1, height=0.2, sync=True)
    rsi_sub.legend(visible=True)
    rsi_sub.time_scale(visible=False)

    # Create Sub-pane for MACD (Synchronized timescale)
    macd_sub = chart.create_subchart(width=1, height=0.2, sync=True)
    macd_sub.legend(visible=True)

    # Setup Indicator Lines
    st_line = chart.create_line(name="supertrend", color="magenta", width=2)
    rsi_line = rsi_sub.create_line(name="rsi", color="cyan", width=2)
    macd_line = macd_sub.create_line(name="macd", color="yellow", width=2)
    signal_line = macd_sub.create_line(name="Signal", color="blue", width=2)

    # Fetch and assign initial data
    df = fetch_and_calculate_data()
    
    chart.set(df[["time", "open", "high", "low", "close"]])
    st_line.set(df[["time", "supertrend"]])
    rsi_line.set(df[["time", "rsi"]])
    macd_line.set(df[["time", "macd"]])
    signal_line.set(df[["time", "macd_signal"]])

    print("[READY] Interactive TradingView window rendering...")
    chart.show(block=True)


if __name__ == "__main__":
    main()
