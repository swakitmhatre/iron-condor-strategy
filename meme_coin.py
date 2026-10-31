import os
import time
import requests
import pandas as pd
import numpy as np

CHECK_INTERVAL_SECONDS = 300  # 5 minutes

# ANSI Color Codes
GREEN = "\033[92m"
RED = "\033[91m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
GRAY = "\033[90m"
RESET = "\033[0m"

# ==========================================
# TECHNICAL INDICATORS ENGINE
# ==========================================
def calculate_indicators(df):
    if len(df) < 14:
        df['MACD'] = 0.0
        df['MACD_signal'] = 0.0
        df['MACD_hist'] = 0.0
        df['RSI'] = 50.0
        df['SUPERTREND'] = df['close']
        df['SUPERTREND_dir'] = 1
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
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    df['RSI'] = 100 - (100 / (1 + rs))
    df['RSI'] = df['RSI'].fillna(50.0)

    # 3. Supertrend (10, 3)
    high_low = df['high'] - df['low']
    high_cp = (df['high'] - df['close'].shift(1)).abs()
    low_cp = (df['low'] - df['close'].shift(1)).abs()
    tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
    atr = tr.rolling(min(10, len(df))).mean()

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
# TRADINGVIEW TERMINAL DASHBOARD ENGINE
# ==========================================
def print_tradingview_terminal_dashboard(symbol, pool_addr, df):
    plot_df = df.tail(15).reset_index(drop=True)
    latest = df.iloc[-1]

    rsi_val = round(latest.get('RSI', 50.0), 2)
    macd_h_raw = latest.get('MACD_hist', 0.0)
    macd_h_str = f"{macd_h_raw:.4e}" if abs(macd_h_raw) < 0.0001 else f"{macd_h_raw:.6f}"
    st_dir = f"{GREEN}BULLISH 🟢{RESET}" if latest.get('SUPERTREND_dir', 1) == 1 else f"{RED}BEARISH 🔴{RESET}"

    print("\n" + "=" * 115)
    print(f"► [{CYAN}{symbol}{RESET}] Pool: {pool_addr[:8]}... | Price: ${latest['close']} | RSI: {rsi_val} | ST: {st_dir}")
    print(f"► MACD Hist: {macd_h_str}")
    print("=" * 115)

    # 1. OHLC & INDICATOR TABLE
    print(f"\n{YELLOW}  [OHLC & TECHNICAL INDICATOR METRICS]{RESET}")
    print(f"  {'TIMESTAMP (UTC)':<18} | {'OPEN':<12} | {'HIGH':<12} | {'LOW':<12} | {'CLOSE':<12} | {'RSI':<6} | {'MACD HIST':<12} | {'ST TREND'}")
    print("  " + "-" * 108)

    for _, row in plot_df.tail(5).iterrows():
        t_str = row['timestamp'].strftime('%Y-%m-%d %H:%M')
        o, h, l, c = row['open'], row['high'], row['low'], row['close']
        r = f"{row.get('RSI', 50.0):.1f}"
        mh = row.get('MACD_hist', 0.0)
        mh_str = f"{mh:.2e}" if abs(mh) < 0.0001 else f"{mh:.6f}"
        st_row = f"{GREEN}BULL{RESET}" if row.get('SUPERTREND_dir', 1) == 1 else f"{RED}BEAR{RESET}"
        
        c_color = GREEN if c >= o else RED
        print(f"  {t_str:<18} | {o:<12.6f} | {h:<12.6f} | {l:<12.6f} | {c_color}{c:<12.6f}{RESET} | {r:<6} | {mh_str:<12} | {st_row}")

    print("  " + "-" * 108)

    # 2. 2D CANDLESTICK CHART WITH WICKS
    print(f"\n{CYAN}  [MAIN PANEL: CANDLESTICK CHART (PRICE & WICKS)]{RESET}\n")

    grid_rows = 10
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

    char_matrix = [["   " for _ in range(num_candles)] for _ in range(grid_rows)]

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

        # Draw Wicks
        for r in range(r_high, r_low + 1):
            char_matrix[r][col] = f"{GRAY} │ {RESET}"

        # Draw Bodies over Wicks
        for r in range(r_body_top, r_body_bottom + 1):
            char_matrix[r][col] = f"{color} █ {RESET}"

    # Print Y-Axis Prices & Chart Rows
    for r in range(grid_rows):
        row_p = max_price - (r / (grid_rows - 1)) * price_range
        price_str = f"${row_p:.6f}" if row_p < 0.01 else f"${row_p:.4f}"
        row_content = "".join([char_matrix[r][c] for c in range(num_candles)])
        print(f"  {price_str:>10} | {row_content}")

    print("             " + "-" * (num_candles * 3))

    # Print Time Values per Candle Line
    time_strs = [plot_df.iloc[i]['timestamp'].strftime('%H:%M') for i in range(num_candles)]
    hh_line = "".join([f" {t[:2]} " for t in time_strs])
    mm_line = "".join([f" {t[3:]} " for t in time_strs])

    print(f"  Time (HH)  | {hh_line}")
    print(f"  Time (MM)  | {mm_line}")

    # 3. MACD & RSI SUBPANELS
    print(f"\n{CYAN}  [SUBPANEL 1: MACD HISTOGRAM]{RESET}")
    macd_bars = []
    for mh in plot_df.get('MACD_hist', [0] * num_candles):
        if mh >= 0:
            macd_bars.append(f"{GREEN} █ {RESET}")
        else:
            macd_bars.append(f"{RED} █ {RESET}")
    print(f"  MACD Hist  | " + "".join(macd_bars))

    print(f"\n{CYAN}  [SUBPANEL 2: RSI (14) OSCILLATOR]{RESET}")
    rsi_bars = []
    for r_val in plot_df.get('RSI', [50] * num_candles):
        if r_val >= 70:
            rsi_bars.append(f"{RED} ▲ {RESET}")
        elif r_val <= 30:
            rsi_bars.append(f"{GREEN} ▼ {RESET}")
        else:
            rsi_bars.append(f"{YELLOW} ░ {RESET}")
    print(f"  RSI Visual | " + "".join(rsi_bars))
    print(f"               ({GREEN}▼ <30 Oversold{RESET} | {YELLOW}░ 30-70 Neutral{RESET} | {RED}▲ >70 Overbought{RESET})")
    print("=" * 115 + "\n")


# ==========================================
# FETCHERS & MAIN LOOP
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

def main():
    print("[SYSTEM] Starting Solana Terminal Monitor...")
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
