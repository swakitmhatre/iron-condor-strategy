import plotext as fig
import numpy as np

def main():
    print("=== INITIALIZING TERMINAL TRADING ENGINE (PLOTEXT 6.1.0) ===")
    
    # Mock data arrays converted cleanly to standard Python lists
    time_steps = [f"Step {i}" for i in range(1, 21)]
    opens = np.random.uniform(0.00001, 0.00002, 20).tolist()
    highs = [o + abs(np.random.normal(0, 0.000002)) for o in opens]
    lows = [o - abs(np.random.normal(0, 0.000002)) for o in opens]
    closes = np.random.uniform(0.00001, 0.00002, 20).tolist()
    
    macd = np.random.uniform(-0.000001, 0.000001, 20).tolist()
    signal = [m + np.random.uniform(-0.0000002, 0.0000002) for m in macd]
    rsi = np.random.uniform(20, 80, 20).tolist()

    # --- 1. Candlestick Chart (Using plotext dictionary data layout) ---
    plt = fig.figure
    plt.clear()
    plt.title("PEPEUSDT - Candlestick Price Action")
    
    # Pass a dictionary containing the required keys for plotext candlestick
    candle_data = {
        'time': time_steps,
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes
    }
    plt.candlestick(candle_data)
    plt.show()

    print("\n" + "="*50 + "\n")

    # --- 2. MACD Indicator ---
    plt.clear()
    plt.title("PEPEUSDT - MACD Indicator")
    plt.plot(time_steps, macd, label="MACD", color="cyan")
    plt.plot(time_steps, signal, label="Signal", color="orange")
    plt.show()

    print("\n" + "="*50 + "\n")

    # --- 3. RSI Curve ---
    plt.clear()
    plt.title("PEPEUSDT - RSI (14)")
    plt.plot(time_steps, rsi, label="RSI", color="magenta")
    plt.ylim(0, 100)
    plt.show()

    print("\nAll terminal charts rendered successfully.")

if __name__ == '__main__':
    main()
