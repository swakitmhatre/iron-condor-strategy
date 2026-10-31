import time
import requests
import pandas as pd
import numpy as np
import plotext as plt

# --- CONFIGURATION ---
SYMBOL = "PEPEUSDT"
INTERVAL_MINUTES = 5
FETCH_INTERVAL_SEC = 300  # 5 minutes


# --- 1. DATA FETCHING & INDICATOR ENGINE ---
def fetch_klines(symbol="PEPEUSDT", limit=50):
    """Fetches real OHLC historical candles from Binance public API."""
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=5m&limit={limit}"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "qav", "num_trades", "tbb", "tbq", "ignore"
        ])
        df["open_time"] = pd.to_datetime(df["open_time"], unit="ms").dt.strftime("%H:%M")
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
        return df
    except Exception as e:
        print(f"[ERROR] Data fetch failed: {e}. Generating fallback data...")
        return generate_dummy_df(limit)

def generate_dummy_df(limit=50):
    """Fallback data generator."""
    times = pd.date_range(end=pd.Timestamp.now(), periods=limit, freq="5min").strftime("%H:%M")
    base_price = 0.0000090
    closes = base_price + np.cumsum(np.random.normal(0, 0.0000001, limit))
    opens = closes - np.random.normal(0, 0.00000005, limit)
    highs = np.maximum(opens, closes) + abs(np.random.normal(0, 0.00000005, limit))
    lows = np.minimum(opens, closes) - abs(np.random.normal(0, 0.00000005, limit))
    return pd.DataFrame({"open_time": times, "open": opens, "high": highs, "low": lows, "close": closes})

def calculate_indicators(df):
    """Calculates Supertrend, RSI, and MACD."""
    # RSI (14)
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / (loss + 1e-10)
    df["rsi"] = 100 - (100 / (1 + rs))

    # MACD (12, 26, 9)
    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # Supertrend (10, 3)
    atr = (df["high"] - df["low"]).rolling(10).mean()
    hl2 = (df["high"] + df["low"]) / 2
    df["supertrend"] = hl2 - (3 * atr)
    
    return df.dropna().reset_index(drop=True)


# --- 2. UNIVERSAL PLOTEXT CLEANER & RENDERER ---
def clear_plotext_figure():
    """Universal reset method that prevents AttributeError on any version of plotext."""
    if hasattr(plt, "clear_figure"):
        plt.clear_figure()
    elif hasattr(plt, "clf"):
        plt.clf()
    elif hasattr(plt, "clear_data"):
        plt.clear_data()

def render_terminal_dashboard(df, symbol):
    """Renders multi-panel color candlestick and technical indicator plots."""
    clear_plotext_figure()
    plt.subplots(3, 1)

    dates = list(df["open_time"])
    dates_idx = list(range(len(dates)))

    # -------------------------------------------------------------
    # PANEL 1: CANDLESTICK CHART + SUPERTREND OVERLAY
    # -------------------------------------------------------------
    plt.subplot(1, 1)
    plt.title(f"{symbol} 5m | Candlesticks + Supertrend")
    
    # Universal Candlestick API (Works across plotext v4, v5, v6)
    try:
        plt.candlestick(dates_idx, {
            "open": df["open"].tolist(),
            "high": df["high"].tolist(),
            "low": df["low"].tolist(),
            "close": df["close"].tolist()
        })
    except Exception:
        plt.candlestick(dates_idx, df["open"].tolist(), df["high"].tolist(), 
                        df["low"].tolist(), df["close"].tolist())
    
    # Overlay Supertrend line
    plt.plot(dates_idx, df["supertrend"].tolist(), label="Supertrend", color="magenta")
    plt.xticks(dates_idx[::5], dates[::5])
    plt.ylabel("Price (USDT)")
    plt.theme("dark")

    # -------------------------------------------------------------
    # PANEL 2: RSI INDICATOR (30/70 BOUNDARIES)
    # -------------------------------------------------------------
    plt.subplot(2, 1)
    plt.title("Relative Strength Index (RSI 14)")
    plt.plot(dates_idx, df["rsi"].tolist(), color="cyan", label="RSI")
    
    # Reference boundary lines
    plt.plot(dates_idx, [70] * len(dates_idx), color="red")
    plt.plot(dates_idx, [30] * len(dates_idx), color="green")
    plt.ylim(0, 100)
    plt.xticks(dates_idx[::5], dates[::5])
    plt.ylabel("RSI Level")
    plt.theme("dark")

    # -------------------------------------------------------------
    # PANEL 3: MACD LINES & HISTOGRAM
    # -------------------------------------------------------------
    plt.subplot(3, 1)
    plt.title("MACD (12, 26, 9) & Histogram")
    plt.plot(dates_idx, df["macd"].tolist(), color="yellow", label="MACD")
    plt.plot(dates_idx, df["macd_signal"].tolist(), color="blue", label="Signal")
    
    # MACD Histogram
    plt.bar(dates_idx, df["macd_hist"].tolist(), label="Hist", color="white")
    plt.xticks(dates_idx[::5], dates[::5])
    plt.xlabel("Time (UTC)")
    plt.ylabel("Value")
    plt.theme("dark")

    # Render dashboard
    plt.show()


# --- 3. MAIN LOOP ---
def main():
    print("=== STARTING AUTONOMOUS TERMINAL TRADING ENGINE ===")
    while True:
        try:
            # Clear terminal console window before redrawing
            print("\033[H\033[J", end="")
            
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
            print(f"[{timestamp}] Updating technical market pattern cross-check for {SYMBOL}...")
            
            df = fetch_klines(SYMBOL)
            df_calculated = calculate_indicators(df)
            
            render_terminal_dashboard(df_calculated, SYMBOL)
            
            print(f"\n[ENGINE ACTIVE] Next cycle in {FETCH_INTERVAL_SEC // 60} minutes. Press Ctrl+C to stop.")
            time.sleep(FETCH_INTERVAL_SEC)
            
        except KeyboardInterrupt:
            print("\n[SHUTDOWN] Engine stopped cleanly.")
            break
        except Exception as e:
            print(f"[ERROR] Exception during execution: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
