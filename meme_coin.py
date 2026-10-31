import plotext as fig
import numpy as np

def main():
    print("=== INITIALIZING TERMINAL TRADING ENGINE (PLOTEXT 6.1.0) ===")
    
    # Mock data arrays
    time_steps = [f"Step {i}" for i in range(1, 21)]
    opens = np.random.uniform(0.00001, 0.00002, 20)
    highs = opens + np.random.uniform(0.000001, 0.000005, 20)
    lows = opens - np.random.uniform(0.000001, 0.000005, 20)
    closes = opens + np.random.uniform(-0.000002, 0.000002, 20)
    
    macd = np.random.uniform(-0.000001, 0.000001, 20)
    signal = macd + np.random.uniform(-0.0000005, 0.0000005, 20)
    rsi = np.random.uniform(20, 80, 20)

    # --- 1. Candlestick Chart (Convert NumPy arrays to lists via .tolist()) ---
    plt = fig.figure
    plt.clear()
  
    plt.title("PEPEUSDT - Candlestick Price Action")
    plt.candlestick(
        time_steps, 
        opens.tolist(), 
        highs.tolist(), 
        lows.tolist(), 
        closes.tolist()
    )
    plt.show()

    print("\n" + "="*50 + "\n")

    # --- 2. MACD Indicator ---
    plt.clf()
    plt.title("PEPEUSDT - MACD Indicator")
    plt.plot(time_steps, macd.tolist(), label="MACD", color="cyan")
    plt.plot(time_steps, signal.tolist(), label="Signal", color="orange")
    plt.show()

    print("\n" + "="*50 + "\n")

    # --- 3. RSI Curve ---
    plt.clf()
    plt.title("PEPEUSDT - RSI (14)")
    plt.plot(time_steps, rsi.tolist(), label="RSI", color="magenta")
    plt.ylim(0, 100)
    plt.show()

    print("\nAll terminal charts rendered successfully.")

if __name__ == '__main__':
    main()
