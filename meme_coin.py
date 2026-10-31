import os
import time
import datetime
import requests
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Headless backend for AWS EC2 SSH sessions
import matplotlib.pyplot as plt

# Check for pandas_ta
try:
    import pandas_ta as ta
    HAS_PANDAS_TA = True
except ImportError:
    HAS_PANDAS_TA = False
    print("[WARN] 'pandas_ta' not found. Using native built-in technical indicators.")

CHECK_INTERVAL_SECONDS = 300  # 5 minutes
CANDLE_LIMIT = 50              # Minimum candles required for accurate indicators

CHARTS_DIR = "charts"
os.makedirs(CHARTS_DIR, exist_ok=True)


# ==========================================
# TECHNICAL INDICATORS ENGINE (SAFE COMPUTATION)
# ==========================================
def calculate_indicators(df):
    if len(df) < CANDLE_LIMIT:
        print(f"[WARN] Insufficient candles ({len(df)}). Need min {CANDLE_LIMIT}.")
        return df

    df = df.copy()

    if HAS_PANDAS_TA:
        try:
            # 1. MACD (8, 17, 9)
            macd = ta.macd(df['close'], fast=8, slow=17, signal=9)
            if macd is not None and not macd.empty:
                df['MACD'] = macd.iloc[:, 0]
                df['MACD_hist'] = macd.iloc[:, 1]
                df['MACD_signal'] = macd.iloc[:, 2]

            # 2. RSI (14)
            rsi = ta.rsi(df['close'], length=14)
            if rsi is not None:
                df['RSI'] = rsi

            # 3. Supertrend (10, 3)
            st = ta.supertrend(df['high'], df['low'], df['close'], length=10, multiplier=3)
            if st is not None and not st.empty:
                df['SUPERTREND'] = st.iloc[:, 0]
                df['SUPERTREND_dir'] = st.iloc[:, 1]

            return df
        except Exception as e:
            print(f"[WARN] pandas_ta error ({e}), using native fallback.")

    # NATIVE FALLBACK CALCULATIONS (No external TA library dependencies)
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
# RENDER ASCII DASHBOARD & SAVE PNG CHART
# ==========================================
def process_and_display_chart(symbol, pool_addr, df):
    """
    Prints a clean ASCII mini-chart dashboard on SSH prompt 
    and saves the full 5m visual PNG chart to disk.
    """
    if 'SUPERTREND' not in df.columns or df.dropna().empty:
        return

    latest = df.iloc[-1]
    rsi_val = round(latest.get('RSI', 0), 2)
    
    macd_h_raw = latest.get('MACD_hist', 0)
    macd_h_str = f"{macd_h_raw:.4e}" if abs(macd_h_raw) < 0.0001 else f"{macd_h_raw:.6f}"
    
    st_dir = "BULLISH 🟢" if latest.get('SUPERTREND_dir', 1) == 1 else "BEARISH 🔴"
    close_price = latest.get('close', 0)

    # Print Terminal Dashboard
    print(f"\n==================================================================")
    print(f"► [{symbol}] Pool: {pool_addr[:6]}... | Price: ${close_price} | RSI: {rsi_val}")
    print(f"► MACD Hist: {macd_h_str} | Supertrend: {st_dir}")
    print(f"------------------------------------------------------------------")
    
    # 5-candle terminal price sparkline display
    recent_5 = df.tail(5)['close'].tolist()
    sparkline = " ➔ ".join([f"${p:.6f}" if p < 0.01 else f"${p:.4f}" for p in recent_5])
    print(f" 5m Candle Trend (Last 5): [ {sparkline} ]")
    print(f"==================================================================")

    # Save PNG Chart File
    plt.close('all')
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 6), sharex=True, gridspec_kw={'height_ratios': [3, 1, 1]})

    ax1.plot(df['timestamp'], df['close'], label='Close Price', color='black', alpha=0.8)
    ax1.plot(df['timestamp'], df['SUPERTREND'], label='Supertrend (10,3)', color='purple', linestyle='--')
    ax1.set_title(f"Solana Meme: {symbol} ({pool_addr[:6]}) 5m Chart")
    ax1.legend(loc='upper left')
    ax1.grid(True, alpha=0.3)

    ax2.plot(df['timestamp'], df['RSI'], label='RSI (14)', color='blue')
    ax2.axhline(70, color='red', linestyle=':')
    ax2.axhline(30, color='green', linestyle=':')
    ax2.set_ylabel('RSI')
    ax2.legend(loc='upper left')
    ax2.grid(True, alpha=0.3)

    colors = ['green' if val >= 0 else 'red' for val in df['MACD_hist']]
    ax3.bar(df['timestamp'], df['MACD_hist'], color=colors, label='MACD Hist (8,17,9)')
    ax3.legend(loc='upper left')
    ax3.grid(True, alpha=0.3)

    plt.xticks(rotation=45)
    plt.tight_layout()

    file_path = os.path.join(CHARTS_DIR, f"{symbol}_{pool_addr[:6]}_5m.png")
    fig.savefig(file_path)
    plt.close(fig)
    print(f"  └─ 📊 Chart image updated: {file_path}")


# ==========================================
# DEXSCREENER PAIR SEARCH
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

    selected_coins = list(unique_coins.values())
    symbols_str = ", ".join([f"{c['symbol']} ({c['pairAddress'][:6]}...)" for c in selected_coins])
    print(f"[SUCCESS] Selected top 3 unique pools: {symbols_str}")
    return selected_coins


# ==========================================
# GECKOTERMINAL OHLCV FETCH
# ==========================================
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
                process_and_display_chart(symbol, pool_addr, df)

        print(f"\n[SLEEP] Waiting {CHECK_INTERVAL_SECONDS // 60} minutes for next candle cycle...\n")
        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
