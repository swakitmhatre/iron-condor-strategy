import os
import time
import requests
import pandas as pd
import numpy as np

CHECK_INTERVAL_SECONDS = 300  # 5 minutes
CANDLE_LIMIT = 50

# ANSI Color Codes for Terminal Printing
GREEN = "\033[92m"
RED = "\033[91m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
RESET = "\033[0m"

# ==========================================
# TECHNICAL INDICATORS
# ==========================================
def calculate_indicators(df):
    if len(df) < CANDLE_LIMIT:
        return df

    df = df.copy()
    ema_fast = df['close'].ewm(span=8, adjust=False).mean()
    ema_slow = df['close'].ewm(span=17, adjust=False).mean()
    df['MACD'] = ema_fast - ema_slow
    df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_hist'] = df['MACD'] - df['MACD_signal']

    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, np.nan)
    df['RSI'] = 100 - (100 / (1 + rs))
    df['RSI'] = df['RSI'].fillna(50)

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
# TRUE 2D TERMINAL GRID CHART RENDERER
# ==========================================
def print_2d_terminal_chart(symbol, pool_addr, df):
    plot_df = df.tail(30).reset_index(drop=True)
    closes = plot_df['close'].tolist()
    opens = plot_df['open'].tolist()
    
    latest = df.iloc[-1]
    rsi_val = round(latest.get('RSI', 0), 2)
    macd_h_raw = latest.get('MACD_hist', 0)
    macd_h_str = f"{macd_h_raw:.4e}" if abs(macd_h_raw) < 0.0001 else f"{macd_h_raw:.6f}"
    st_dir = f"{GREEN}BULLISH 🟢{RESET}" if latest.get('SUPERTREND_dir', 1) == 1 else f"{RED}BEARISH 🔴{RESET}"

    print("\n" + "=" * 78)
    print(f"► [{CYAN}{symbol}{RESET}] Pool: {pool_addr[:6]}... | Price: ${latest['close']} | RSI: {rsi_val} | ST: {st_dir}")
    print(f"► MACD Hist: {macd_h_str}")
    print("=" * 78)
    print(f"{CYAN}  [2D TIME vs PRICE GRID (Last 30 Candles)] {RESET}\n")

    min_p, max_p = min(closes), max(closes)
    if min_p == max_p:
        max_p += 1e-12
        
    grid_rows = 12
    grid = [[" " for _ in range(len(plot_df))] for _ in range(grid_rows)]

    # Map each candle to the 2D coordinate grid
    for col_idx, (o, c) in enumerate(zip(opens, closes)):
        normalized_row = int((c - min_p) / (max_p - min_p) * (grid_rows - 1))
        row_idx = (grid_rows - 1) - max(0, min(normalized_row, grid_rows - 1))
        
        color_char = f"{GREEN}▲{RESET}" if c >= o else f"{RED}▼{RESET}"
        grid[row_idx][col_idx] = color_char

    # Print grid with vertical price scale labels
    for r in range(grid_rows):
        row_price = max_p - (r / (grid_rows - 1)) * (max_p - min_p)
        if row_price < 0.01:
            price_label = f"${row_price:.6f}"
        else:
            price_label = f"${row_price:.4f}"
            
        row_str = "".join(grid[r])
        print(f"  {price_label:>10} | {row_str}")

    print("             " + "-" * len(plot_df))
    print(f"             {YELLOW}Time ➔ (Oldest to Newest 5m intervals){RESET}")
    print("=" * 78 + "\n")


# ==========================================
# DATA FETCHERS & MAIN LOOP
# ==========================================
def fetch_and_filter_solana_coins():
    keywords = ["PEPE", "WIF", "BONK", "CAT", "AI", "MEME"]
    all_pairs = []
    
    print("\n[INFO] Fetching diverse meme coin pairs from DexScreener...")
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
    print("[SYSTEM] Starting Solana 2D Grid Chart Bot...")
    while True:
        top_coins = fetch_and_filter_solana_coins()
        for coin in top_coins:
            df = fetch_geckoterminal_ohlcv(coin['pairAddress'])
            if not df.empty:
                df = calculate_indicators(df)
                print_2d_terminal_chart(coin['symbol'], coin['pairAddress'], df)

        print(f"[SLEEP] Waiting 5 minutes for next candle cycle...\n")
        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
