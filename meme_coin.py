import plotext as fig
import numpy as np

def main():
    print("=== INITIALIZING TERMINAL TRADING ENGINE (PLOTEXT 6.1.0) ===")
    
    # Date strings and numeric indices
    time_steps = [f"2026-10-{i:02d}" for i in range(1, 21)]
    indices = list(range(len(time_steps)))
    
    opens = np.random.uniform(0.00001, 0.00002, 20).tolist()
    highs = [o + abs(np.random.normal(0, 0.000002)) for o in opens]
    lows = [o - abs(np.random.normal(0, 0.000002)) for o in opens]
    closes = np.random.uniform(0.00001, 0.00002, 20).tolist()
    
    macd = np.random.uniform(-0.000001, 0.000001, 20).tolist()
    signal = [m + np.random.uniform(-0.0000002, 0.0000002) for m in macd]
    rsi = np.random.uniform(20, 80, 20).tolist()

    plt = fig.figure

    # --- 1. Candlestick Chart (Using numeric indices for 'date' + xticks) ---
    plt.clear()
    plt.title("PEPEUSDT - Candlestick Price Action")
    
    candle_data = {
        'date': indices,  # Must be numbers
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes
    }
    plt.candlestick(candle_data)
    #plt.xticks(indices[::3], time_steps[::3])  # Show every 3rd date label to avoid clutter
    plt.draw()

    print("\n" + "="*50 + "\n")

    # --- 2. MACD Indicator ---
    plt.clear()
    plt.title("PEPEUSDT - MACD Indicator")
    plt.draw(indices, macd, label="MACD", color="cyan")
    plt.draw(indices, signal, label="Signal", color="orange")
    #plt.xticks(indices[::3], time_steps[::3])
    plt.show()

    print("\n" + "="*50 + "\n")

    # --- 3. RSI Curve ---
    plt.clear()
    plt.title("PEPEUSDT - RSI (14)")
    plt.draw(indices, rsi, label="RSI", color="magenta")
    plt.ylim(0, 100)
    #plt.xticks(indices[::3], time_steps[::3])
    plt.show()

    print("\nAll terminal charts rendered successfully.")

if __name__ == '__main__':
    main()
