import os
import time
import datetime
import requests
import pandas as pd
import numpy as np

# Import plotext for terminal ASCII charts
try:
    import plotext as plt
    HAS_PLOTEXT = True
except ImportError:
    HAS_PLOTEXT = False
    print("[WARN] 'plotext' library not installed. Run 'pip install plotext'.")

# Import pandas_ta
try:
    import pandas_ta as ta
    HAS_PANDAS_TA = True
except ImportError:
    HAS_PANDAS_TA = False

CHECK_INTERVAL_SECONDS = 300  # 5 minutes
CANDLE_LIMIT = 50              # Minimum historical candles required

# ==========================================
# TECHNICAL INDICATORS ENGINE
# ==========================================
def calculate_indicators(df):
    if len(df) < CANDLE_LIMIT:
        print(f"[WARN] Insufficient candles ({len(df)}). Need min {CANDLE_LIMIT}.")
        return df

    df = df.copy()

    if HAS_PANDAS_TA:
        try:
            macd = ta.macd(df['close'], fast=8, slow=17, signal=9)
            if macd is not None and not macd.empty:
                df['MACD'] = macd.iloc[:, 0]
                df['MACD_hist'] = macd.iloc[:, 1]
                df['MACD_signal'] = macd.iloc[:, 2]

            rsi = ta.rsi(df['close'], length=14)
            if rsi is not None:
                df['RSI'] = rsi

            st = ta.supertrend(df['high'], df['low'], df['close'], length=10, multiplier=3)
            if st is not None and not st.empty:
                df['SUPERTREND'] = st.iloc[:, 0]
                df['SUPERTREND_dir'] = st.iloc[:, 1]

            return df
        except Exception:
            pass

    # NATIVE FALLBACK CALCULATIONS
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
# PRINT ASCII CHART DIRECTLY ON TERMINAL
# ==========================================
def print_terminal_chart(symbol, pool_addr, df):
    """
    Renders 5-minute price charts and indicators directly inside SSH prompt.
    """
    if not HAS_PLOTEXT or 'SUPERTREND' not in df.columns:
        return

    plot_df = df.tail(30).reset_index(drop=True)
    x_axis = list(range(len(plot_df)))

    # Safe clear figure canvas for any plotext version
    try:
        plt.clf()
    except AttributeError:
        try:
            plt.clear_data()
        except AttributeError:
            pass

    plt.subplots(2, 1)

    # Subplot 1: Price & Supertrend
    plt.subplot(1, 1)
    plt.title(f"[{symbol}] Pool: {pool_addr[:6]}... - 5m Price & Supertrend")
    plt.plot(x_axis, plot_df['close'], label="Price", color="cyan")
    plt.plot(x_axis, plot_df['SUPERTREND'], label="Supertrend", color="magenta")
    plt.grid(True)

    # Subplot 2: RSI
    plt.subplot(2, 1)
    plt.title("RSI (14)")
    plt.plot(x_axis, plot_df['RSI'], label="RSI", color="yellow")
    plt.grid(True)

    plt.plotsize(80, 18)
    plt.show()


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
# GECKOTERMINAL OHLCV SYNC
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
# MAIN LOOP
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
                
                latest = df.iloc[-1]
                rsi_val = round(latest.get('RSI', 0), 2)
                
                macd_h_raw = latest.get('MACD_hist', 0)
                macd_h_str = f"{macd_h_raw:.4e}" if abs(macd_h_raw) < 0.0001 else f"{macd_h_raw:.6f}"
                
                st_dir = "BULLISH 🟢" if latest.get('SUPERTREND_dir', 1) == 1 else "BEARISH 🔴"
                
                print(f"\n==================================================================")
                print(f"► [{symbol}] Pool: {pool_addr[:6]}... | Price: ${coin['priceUsd']} | RSI: {rsi_val} | MACD Hist: {macd_h_str} | Supertrend: {st_dir}")
                print(f"==================================================================")
                
                print_terminal_chart(symbol, pool_addr, df)

        print(f"\n[SLEEP] Waiting {CHECK_INTERVAL_SECONDS // 60} minutes for next candle cycle...\n")
        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
