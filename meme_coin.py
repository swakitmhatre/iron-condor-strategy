import os
import time
import requests
import pandas as pd
import numpy as np

CHECK_INTERVAL_SECONDS = 300  # 5 minutes
CANDLE_LIMIT = 50

# ANSI Color Codes
GREEN = "\033[92m"
RED = "\033[91m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
GRAY = "\033[90m"
RESET = "\033[0m"

# ==========================================
# TECHNICAL INDICATORS CALCULATOR
# ==========================================
def calculate_indicators(df):
    if len(df) < CANDLE_LIMIT:
        return df

    df = df.copy()

    # 1. MACD (8, 17, 9)
    ema_fast = df['close'].ewm(span=8, adjust=False).mean()
    ema_slow = df['close'].ewm(span=17, adjust=False).mean()
    df['MACD'] = ema_fast - ema_slow
    df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_hist'] = df['MACD'] - df['MACD_signal']

    # 2. RSI (14)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, np.nan)
    df['RSI'] = 100 - (100 / (1 + rs))
    df['RSI'] = df['RSI'].fillna(50)

    # 3. Supertrend (10, 3)
    high_low = df['high'] - df['low']
    high_cp = (df['high'] - df['close'].shift(1)).abs()
    low_cp = (df['low'] - df['close'].shift(1)).abs()
    tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
    atr = tr.rolling(10).mean()

    hl2 = (df['high'] + df['low']) / 2
    basic_upper = hl2 + (3 * atr)
    basic_lower = hl2 - (3 * atr)

    supertrend = np.zeros(len(df))
    direction = np.ones(len(df))

    for i in range(1, len(df)):
        if df['close'].iloc[i] > basic_upper.iloc[i-1]:
            direction[i] = 1
        elif df['close'].iloc[i] < basic_lower.iloc[i-1]:
            direction[i] = -1
        else:
            direction[i] = direction[i-1]
        supertrend[i] = basic_lower.iloc[i] if direction[i] == 1 else basic_upper.iloc[i]

    df['SUPERTREND'] = supertrend
    df['SUPERTREND_dir'] = direction
    return df


# ==========================================
# TRADINGVIEW-STYLE CANDLESTICK ENGINE
# ==========================================
def print_tradingview_terminal_dashboard(symbol, pool_addr, df):
    # Plot last 24 candles for clean prompt alignment
    plot_df = df.tail(24).reset_index(drop=True)
    latest = df.iloc[-1]

    rsi_val = round(latest.get('RSI', 0), 2)
    macd_h_raw = latest.get('MACD_hist', 0)
    macd_h_str = f"{macd_h_raw:.4e}" if abs(macd_h_raw) < 0.0001 else f"{macd_h_raw:.6f}"
    st_dir = f"{GREEN}BULLISH 🟢{RESET}" if latest.get('SUPERTREND_dir', 1) == 1 else f"{RED}BEARISH 🔴{RESET}"

    print("\n" + "=" * 108)
    print(f"► [{CYAN}{symbol}{RESET}] Pool: {pool_addr[:8]}... | Price: ${latest['close']} | RSI: {rsi_val} | ST: {st_dir}")
    print(f"► MACD Hist: {macd_h_str}")
    print("=" * 108)

    # -------------------------------------------------------------
    # SECTION 1: OHLC & INDICATOR DATA TABLE (LAST 5 CANDLES)
    # -------------------------------------------------------------
    print(f"\n{YELLOW}  [OHLC & TECHNICAL INDICATOR DATA TABLE]{RESET}")
    print(f"  {'TIMESTAMP (UTC)':<18} | {'OPEN':<12} | {'HIGH':<12} | {'LOW':<12} | {'CLOSE':<12} | {'RSI':<6} | {'MACD HIST':<12} | {'ST TREND'}")
    print("  " + "-" * 102)

    for _, row in plot_df.tail(5).iterrows():
        t_str = row['timestamp'].strftime('%Y-%m-%d %H:%M')
        o, h, l, c = row['open'], row['high'], row['low'], row['close']
        r = f"{row.get('RSI', 0):.1f}"
        mh = row.get('MACD_hist', 0)
        mh_str = f"{mh:.2e}" if abs(mh) < 0.0001 else f"{mh:.6f}"
        st_row = f"{GREEN}BULL{RESET}" if row.get('SUPERTREND_dir', 1) == 1 else f"{RED}BEAR{RESET}"
        
        c_color = GREEN if c >= o else RED
        print(f"  {t_str:<18} | {o:<12.6f} | {h:<12.6f} | {l:<12.6f} | {c_color}{c:<12.6f}{RESET} | {r:<6} | {mh_str:<12} | {st_row}")

    print("  " + "-" * 102)

    # -------------------------------------------------------------
    # SECTION 2: 2D CANDLESTICK CHART WITH WICKS & STEPPED TIMELINE
    # -------------------------------------------------------------
    print(f"\n{CYAN}  [TRADINGVIEW-STYLE CANDLESTICK CHART WITH WICKS (5m CANDLES)]{RESET}\n")

    grid_rows = 12
    num_candles = len(plot_df)

    min_price = plot_df['low'].min()
    max_price = plot_df['high'].max()
    if min_price == max_price:
        max_price += 1e-12

    price_range = max_price - min_price

    def price_to_row(p):
        norm = (p - min_price) / price_range
        r = int((1.0 - norm) * (grid_rows - 1))
        return max(0, min(r, grid_rows - 1))

    # Build 2D Character & Color Buffer
    char_matrix = [[" " for _ in range(num_candles)] for _ in range(grid_rows)]
    color_matrix = [[RESET for _ in range(num_candles)] for _ in range(grid_rows)]

    for col in range(num_candles):
        row_data = plot_df.iloc[col]
        o, h, l, c = row_data['open'], row_data['high'], row_data['low'], row_data['close']
        
        r_high = price_to_row(h)
        r_low = price_to_row(l)
        r_open = price_to_row(o)
        r_close = price_to_row(c)

        r_body_top = min(r_open, r_close)
        r_body_bottom = max(r_open, r_close)

        color = GREEN if c >= o else RED

        # Draw Wicks (Upper & Lower)
        for r in range(r_high, r_low + 1):
            char_matrix[r][col] = "│"
            color_matrix[r][col] = GRAY

        # Draw Real Candlestick Bodies over Wicks
        for r in range(r_body_top, r_body_bottom + 1):
            char_matrix[r][col] = "█"
            color_matrix[r][col] = color

    # Print Chart Lines with Y-Axis Price Scales
    for r in range(grid_rows):
        row_p = max_price - (r / (grid_rows - 1)) * price_range
        price_str = f"${row_p:.6f}" if row_p < 0.01 else f"${row_p:.4f}"

        line_chars = []
        for c in range(num_candles):
            line_chars.append(f"{color_matrix[r][c]}{char_matrix[r][c]}{RESET}")
        
        row_content = "".join(line_chars)
        print(f"  {price_str:>10} | {row_content}")

    # Print Horizontal Time Axis & Stepped Timestamps
    print("             " + "-" * num_candles)

    t_start = plot_df.iloc[0]['timestamp'].strftime('%H:%M')
    t_mid = plot_df.iloc[len(plot_df)//2]['timestamp'].strftime('%H:%M')
    t_end = plot_df.iloc[-1]['timestamp'].strftime('%H:%M UTC')

    step_gap = (num_candles // 2) - 5
    time_axis_line = f"{t_start}" + " " * max(1, step_gap) + f"{t_mid}" + " " * max(1, step_gap) + f"{t_end}"
    
    print(f"  Timestamp  | {time_axis_line}")
    print("=" * 108 + "\n")


# ==========================================
# DEXSCREENER & GECKOTERMINAL DATA ENGINE
# ==========================================
def fetch_and_filter_solana_coins():
    keywords = ["PEPE", "WIF", "BONK", "CAT", "AI", "MEME"]
    all_pairs = []

    print("\n[INFO] Fetching active Solana pairs from DexScreener...")
    for kw in keywords:
        url = f"https://api.dexscreener.com/latest/dex/search?q={kw}"
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                for p in res.json().get('pairs', []):
                    if p.get('chainId') == 'solana':
                        base_symbol = p.get('baseToken', {}).get('symbol', '').upper()
                        if base_symbol not in ['SOL', 'WSOL', 'USDC', 'USDT']:
                            all_pairs.append({
                                'pairAddress': p['pairAddress'],
                                'symbol': base_symbol,
                                'priceUsd': float(p.get('priceUsd', 0)),
                            })
        except Exception:
            continue

    unique_coins = {}
    for c in all_pairs:
        if c['pairAddress'] not in unique_coins:
            unique_coins[c['pairAddress']] = c
        if len(unique_coins) >= 3:
            break
    return list(unique_coins.values())

def fetch_geckoterminal_ohlcv(pool_address):
    url = f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool_address}/ohlcv/minute?aggregate=5"
    headers = {"Accept": "application/json;version=20230302"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            ohlcv_list = res.json().get('data', {}).get('attributes', {}).get('ohlcv_list', [])
            df = pd.DataFrame(ohlcv_list, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)
            return df.sort_values('timestamp').reset_index(drop=True)
    except Exception:
        pass
    return pd.DataFrame()


# ==========================================
# MAIN EXECUTION LOOP
# ==========================================
def main():
    print("[SYSTEM] Starting Solana TradingView Terminal Bot...")
    while True:
        top_coins = fetch_and_filter_solana_coins()
        for coin in top_coins:
            df = fetch_geckoterminal_ohlcv(coin['pairAddress'])
            if not df.empty:
                df = calculate_indicators(df)
                print_tradingview_terminal_dashboard(coin['symbol'], coin['pairAddress'], df)

        print(f"[SLEEP] Waiting 5 minutes for next candle cycle...\n")
        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
