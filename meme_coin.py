import os
import time
import datetime
import requests
import pandas as pd
import numpy as np

CHECK_INTERVAL_SECONDS = 300  # 5 minutes
CANDLE_LIMIT = 50

# ==========================================
# INDICATORS ENGINE (NATIVE NUMPY/PANDAS)
# ==========================================
def calculate_indicators(df):
    if len(df) < CANDLE_LIMIT:
        return df

    df = df.copy()

    # MACD (8, 17, 9)
    ema_fast = df['close'].ewm(span=8, adjust=False).mean()
    ema_slow = df['close'].ewm(span=17, adjust=False).mean()
    df['MACD'] = ema_fast - ema_slow
    df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_hist'] = df['MACD'] - df['MACD_signal']

    # RSI (14)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, np.nan)
    df['RSI'] = 100 - (100 / (1 + rs))
    df['RSI'] = df['RSI'].fillna(50)

    # Supertrend (10, 3)
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
# ASCII PROMPT CHART PRINTER
# ==========================================
def print_prompt_chart(symbol, pool_addr, df):
    """
    Prints a clean ASCII chart directly inside the SSH text prompt.
    Does not rely on Matplotlib, Plotext, or desktop GUI components.
    """
    plot_df = df.tail(20).reset_index(drop=True)
    prices = plot_df['close'].tolist()
    rsi_vals = plot_df['RSI'].tolist()
    
    min_p, max_p = min(prices), max(prices)
    span = max_p - min_p if max_p != min_p else 1

    latest = df.iloc[-1]
    rsi_val = round(latest.get('RSI', 0), 2)
    macd_h_raw = latest.get('MACD_hist', 0)
    macd_h_str = f"{macd_h_raw:.4e}" if abs(macd_h_raw) < 0.0001 else f"{macd_h_raw:.6f}"
    st_dir = "BULLISH 🟢" if latest.get('SUPERTREND_dir', 1) == 1 else "BEARISH 🔴"

    print("\n" + "=" * 75)
    print(f"► [{symbol}] Pool: {pool_addr[:6]}... | Price: ${latest['close']} | RSI: {rsi_val}")
    print(f"► MACD Hist: {macd_h_str} | Supertrend: {st_dir}")
    print("=" * 75)

    # 1. Price Visual Graph
    print("\n  [PRICE TREND - LAST 20 CANDLES (5m)]")
    for i, p in enumerate(prices):
        bar_len = int(((p - min_p) / span) * 30)
        bar = "█" * max(1, bar_len)
        price_str = f"${p:.6f}" if p < 0.01 else f"${p:.4f}"
        print(f"  {price_str} | {bar}")

    # 2. RSI Level Visual Bar
    print("\n  [RSI (14) VISUAL GAUGE]")
    rsi_bar_len = int((rsi_val / 100.0) * 30)
    rsi_bar = "█" * rsi_bar_len
    print(f"  RSI: {rsi_val} | [0 {rsi_bar:<30} 100]")
    print("=" * 75 + "\n")


# ==========================================
# DEXSCREENER & GECKOTERMINAL FETCHERS
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

    selected = list(unique_coins.values())
    symbols_str = ", ".join([f"{c['symbol']} ({c['pairAddress'][:6]}...)" for c in selected])
    print(f"[SUCCESS] Selected top 3 unique pools: {symbols_str}")
    return selected

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
    except Exception as e:
        print(f"[ERROR] Candle fetch error: {e}")
    return pd.DataFrame()


# ==========================================
# MAIN EXECUTION LOOP
# ==========================================
def main():
    print("[SYSTEM] Starting Solana Meme Trading Bot...")
    
    while True:
        top_coins = fetch_and_filter_solana_coins()

        for coin in top_coins:
            symbol = coin['symbol']
            pool_addr = coin['pairAddress']

            df = fetch_geckoterminal_ohlcv(pool_addr)
            
            if not df.empty:
                df = calculate_indicators(df)
                print_prompt_chart(symbol, pool_addr, df)

        print(f"[SLEEP] Waiting {CHECK_INTERVAL_SECONDS // 60} minutes for next candle cycle...\n")
        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
