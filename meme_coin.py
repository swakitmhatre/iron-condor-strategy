import os
import time
import datetime
import requests
import pandas as pd
import numpy as np
import matplotlib
# Set headless backend for AWS EC2 SSH CLI environment
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ==========================================
# DEPENDENCY & CONFIGURATION SETUP
# ==========================================
try:
    import pandas_ta as ta
    HAS_PANDAS_TA = True
except ImportError:
    HAS_PANDAS_TA = False
    print("[WARN] 'pandas_ta' not found. Using native built-in technical indicators.")

CHECK_INTERVAL_SECONDS = 300  # 5 minutes
LOOKBACK_CANDLES = 3           # Overwrite last 2-3 candles for accuracy
CANDLE_LIMIT = 50              # Minimum historical candles required for indicators

SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"
CHARTS_DIR = "charts"
COIN_DATABASE = {}
TRADE_LOG = []

# Ensure chart directory exists
os.makedirs(CHARTS_DIR, exist_ok=True)


# ==========================================
# SAFE TECHNICAL INDICATORS ENGINE
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
            print(f"[WARN] pandas_ta error ({e}), using native calculation fallback.")

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
# SAVE 5m CHART IMAGE FOR AWS AWS EC2
# ==========================================
def save_5m_chart(symbol, df):
    """
    Renders and saves the 5-minute price chart with MACD, RSI, and Supertrend 
    to disk (`charts/{symbol}_5m.png`).
    """
    if 'SUPERTREND' not in df.columns or df.dropna().empty:
        return

    plt.close('all')
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 8), sharex=True, gridspec_kw={'height_ratios': [3, 1, 1]})

    # Subplot 1: Price & Supertrend
    ax1.plot(df['timestamp'], df['close'], label='Close Price', color='black', alpha=0.8)
    ax1.plot(df['timestamp'], df['SUPERTREND'], label='Supertrend (10,3)', color='purple', linestyle='--')
    ax1.set_title(f"Solana Meme Coin: {symbol} - 5m Chart")
    ax1.legend(loc='upper left')
    ax1.grid(True, alpha=0.3)

    # Subplot 2: RSI
    ax2.plot(df['timestamp'], df['RSI'], label='RSI (14)', color='blue')
    ax2.axhline(70, color='red', linestyle=':')
    ax2.axhline(30, color='green', linestyle=':')
    ax2.set_ylabel('RSI')
    ax2.legend(loc='upper left')
    ax2.grid(True, alpha=0.3)

    # Subplot 3: MACD Histogram
    colors = ['green' if val >= 0 else 'red' for val in df['MACD_hist']]
    ax3.bar(df['timestamp'], df['MACD_hist'], color=colors, label='MACD Hist (8,17,9)')
    ax3.legend(loc='upper left')
    ax3.grid(True, alpha=0.3)

    plt.xticks(rotation=45)
    plt.tight_layout()

    # Save PNG chart file to disk
    file_path = os.path.join(CHARTS_DIR, f"{symbol}_5m.png")
    fig.savefig(file_path)
    plt.close(fig)
    print(f"  └─ 📊 Chart image saved to disk: {file_path}")


# ==========================================
# DEXSCREENER FILTERING & DIAGNOSTICS
# ==========================================
def fetch_and_filter_solana_coins():
    # Search keywords targeted toward active meme tokens on Solana
    keywords = ["PEPE", "WIF", "BONK", "CAT", "AI", "MEME", "SOL"]
    all_pairs = []
    
    print("\n[INFO] Fetching diverse meme coin pairs from DexScreener...")
    
    for kw in keywords:
        url = f"https://api.dexscreener.com/latest/dex/search?q={kw}"
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                pairs = res.json().get('pairs', [])
                for p in pairs:
                    # Filter strictly for Solana chain and exclude native/wrapped SOL itself
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

    # Deduplicate by pair address to ensure unique coins
    unique_coins = {c['pairAddress']: c for c in all_pairs}.values()
    selected_coins = list(unique_coins)[:3]  # Grab top 3 distinct coins

    symbols_str = ", ".join([c['symbol'] for c in selected_coins]) if selected_coins else "None"
    print(f"[SUCCESS] Selected top 3 unique meme coins: {symbols_str}")
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
                
                # Terminal output dashboard line
                latest = df.iloc[-1]
                rsi_val = round(latest.get('RSI', 0), 2)
                macd_h = round(latest.get('MACD_hist', 0), 6)
                st_dir = "BULLISH 🟢" if latest.get('SUPERTREND_dir', 1) == 1 else "BEARISH 🔴"
                
                print(f"\n► [{symbol}] Price: ${coin['priceUsd']} | RSI: {rsi_val} | MACD Hist: {macd_h} | Supertrend: {st_dir}")
                
                # Save visual chart PNG for EC2
                save_5m_chart(symbol, df)

        print(f"\n[SLEEP] Waiting {CHECK_INTERVAL_SECONDS // 60} minutes for next candle cycle...\n")
        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
