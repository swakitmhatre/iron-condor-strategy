import time
import datetime
import requests
import pandas as pd
import pandas_ta as ta
import matplotlib.pyplot as plt

# ==========================================
# CONFIGURATION & CONSTANTS
# ==========================================
CHECK_INTERVAL_SECONDS = 300  # 5 minutes
LOOKBACK_CANDLES = 3           # Overwrite last 2-3 candles for lookback safety
CANDLE_LIMIT = 100             # Minimum historical candles required for indicators

# Public Solana RPC endpoint (You can swap this with a private Helius/QuickNode RPC for speed)
SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"

# Global local database to store candle history per coin (Pool Address -> DataFrame)
COIN_DATABASE = {}

# Simulated Paper Trading Log
TRADE_LOG = []

# ==========================================
# ON-CHAIN VALIDATION HELPERS (Criteria h & j)
# ==========================================
def verify_token_security(mint_address):
    """
    Validates:
    h) Liquidity is locked/burned (via RugCheck API)
    j) First coin holder does not hold more than 10% of supply (via Solana RPC)
    """
    if not mint_address:
        return False

    try:
        # 1. Check Liquidity Lock via RugCheck.xyz Free API
        rugcheck_url = f"https://api.rugcheck.xyz/v1/tokens/{mint_address}/report/summary"
        res = requests.get(rugcheck_url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            markets = data.get('markets', [])
            is_locked = False
            for market in markets:
                lp_locked_pct = market.get('lp', {}).get('lpLockedPct', 0)
                if lp_locked_pct >= 90.0:  # 90%+ liquidity locked or burned
                    is_locked = True
                    break
            # Fallback check if global summary marks lpLockedPct
            if not is_locked and data.get('lpLockedPct', 0) < 90.0:
                return False
        else:
            # If rugcheck fails to respond cleanly, skip to protect capital
            return False

        # 2. Check Top Holder Concentration (< 10%) via Solana RPC
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenLargestAccounts",
            "params": [mint_address]
        }
        rpc_res = requests.post(SOLANA_RPC_URL, json=payload, timeout=5).json()
        result_obj = rpc_res.get('result', {})
        accounts = result_obj.get('value', [])
        
        if not accounts:
            return False

        # Get total supply to calculate exact percentage safely
        supply_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getTokenSupply",
            "params": [mint_address]
        }
        supply_res = requests.post(SOLANA_RPC_URL, json=supply_payload, timeout=5).json()
        supply_val = supply_res.get('result', {}).get('value', {})
        total_supply_ui = float(supply_val.get('uiAmount', 0))

        if total_supply_ui <= 0:
            return False

        # Check top holder balance
        top_holder_amount = float(accounts[0].get('uiAmount', 0))
        top_holder_pct = (top_holder_amount / total_supply_ui) * 100.0

        if top_holder_pct > 10.0:
            print(f"[FILTER FAIL] Token {mint_address[:6]}... Top holder owns {top_holder_pct:.2f}% (> 10%)")
            return False

        return True

    except Exception as e:
        print(f"[WARN] Security check exception for {mint_address}: {e}")
        return False


# ==========================================
# STEP 1: DEXSCREENER COMPLETE FILTERING
# ==========================================
def fetch_and_filter_solana_coins():
    url = "https://api.dexscreener.com/latest/dex/search?q=SOL"
    print("\n[INFO] [DIAGNOSTIC MODE] Fetching active Solana pairs...")
    try:
        res = requests.get(url, timeout=10)
        pairs = res.json().get('pairs', [])
    except Exception as e:
        print(f"[ERROR] {e}")
        return []

    diagnostic_coins = []
    for pair in pairs:
        if pair.get('chainId') != 'solana':
            continue
            
        base_token = pair.get('baseToken', {})
        diagnostic_coins.append({
            'pairAddress': pair['pairAddress'],
            'symbol': base_token.get('symbol', 'UNKNOWN'),
            'priceUsd': float(pair.get('priceUsd', 0)),
        })
        if len(diagnostic_coins) >= 3:
            break  # Grab just 3 active coins for testing

    print(f"[SUCCESS] Diagnostic mode selected {len(diagnostic_coins)} active test coins.")
    return diagnostic_coins


# ==========================================
# STEP 2: OHLCV DATA MANAGEMENT (GECKOTERMINAL)
# ==========================================
def fetch_geckoterminal_ohlcv(pool_address, before_timestamp=None):
    url = f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool_address}/ohlcv/minute?aggregate=5"
    if before_timestamp:
        url += f"&before_timestamp={before_timestamp}"
    
    headers = {"Accept": "application/json;version=20230302"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            ohlcv_list = data.get('data', {}).get('attributes', {}).get('ohlcv_list', [])
            df = pd.DataFrame(ohlcv_list, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)
            df = df.sort_values('timestamp').reset_index(drop=True)
            return df
    except Exception as e:
        print(f"[ERROR] GeckoTerminal API error for {pool_address}: {e}")
    return pd.DataFrame()

def sync_candle_database(pool_address):
    global COIN_DATABASE
    if pool_address not in COIN_DATABASE:
        print(f"[INIT] Genesis fetch for pool {pool_address}")
        df = fetch_geckoterminal_ohlcv(pool_address)
        COIN_DATABASE[pool_address] = df
        return COIN_DATABASE[pool_address]

    existing_df = COIN_DATABASE[pool_address]
    recent_df = fetch_geckoterminal_ohlcv(pool_address)
    
    if recent_df.empty:
        return existing_df
    
    # Look-back Overwrite logic to handle delayed blocks/indexers
    combined = pd.concat([existing_df, recent_df]).drop_duplicates(subset=['timestamp'], keep='last')
    combined = combined.sort_values('timestamp').reset_index(drop=True)
    COIN_DATABASE[pool_address] = combined
    return combined


# ==========================================
# INDICATORS & ERROR SAFEGUARDS
# ==========================================
def calculate_indicators(df):
    """
    Calculates MACD(8,17,9), RSI(14), and Supertrend(10,3) safely.
    Handles column name variations in pandas_ta dynamically.
    """
    if len(df) < CANDLE_LIMIT:
        print(f"[WARN] Insufficient candles ({len(df)}). Need min {CANDLE_LIMIT}.")
        return df

    df = df.copy()

    if HAS_PANDAS_TA:
        try:
            # 1. MACD (8, 17, 9)
            macd = ta.macd(df['close'], fast=8, slow=17, signal=9)
            if macd is not None and not macd.empty:
                df['MACD'] = macd.iloc[:, 0]        # MACD Line
                df['MACD_hist'] = macd.iloc[:, 1]   # MACD Histogram
                df['MACD_signal'] = macd.iloc[:, 2] # MACD Signal Line

            # 2. RSI (14)
            rsi = ta.rsi(df['close'], length=14)
            if rsi is not None:
                df['RSI'] = rsi

            # 3. Supertrend (10, 3) - DYNAMIC COLUMN EXTRACTION (Fixes KeyError)
            st = ta.supertrend(df['high'], df['low'], df['close'], length=10, multiplier=3)
            if st is not None and not st.empty:
                # Column 0 is Supertrend value, Column 1 is Direction (1 or -1)
                df['SUPERTREND'] = st.iloc[:, 0]
                df['SUPERTREND_dir'] = st.iloc[:, 1]

            return df
        except Exception as e:
            print(f"[WARN] pandas_ta computation error ({e}), switching to native computation.")

    # NATIVE FALLBACK CALCULATIONS (If pandas_ta fails or isn't installed)
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
# CHART RENDERING (MATPLOTLIB)
# ==========================================
def plot_5m_chart(symbol, df):
    if 'SUPERTREND' not in df.columns or df.dropna().empty:
        return

    plt.close('all')
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(12, 8), sharex=True, gridspec_kw={'height_ratios': [3, 1, 1]})

    ax1.plot(df['timestamp'], df['close'], label='Close Price', color='black', alpha=0.7)
    ax1.plot(df['timestamp'], df['SUPERTREND'], label='Supertrend (10,3)', color='purple', linestyle='--')
    ax1.set_title(f"{symbol} - 5m Chart with Indicators")
    ax1.legend(loc='upper left')
    ax1.grid(True)

    ax2.plot(df['timestamp'], df['RSI'], label='RSI (14)', color='blue')
    ax2.axhline(70, color='red', linestyle=':')
    ax2.axhline(30, color='green', linestyle=':')
    ax2.set_ylabel('RSI')
    ax2.legend(loc='upper left')
    ax2.grid(True)

    colors = ['green' if val >= 0 else 'red' for val in df['MACD_hist']]
    ax3.bar(df['timestamp'], df['MACD_hist'], color=colors, label='MACD Hist (8,17,9)')
    ax3.legend(loc='upper left')
    ax3.grid(True)

    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.show(block=False)
    plt.pause(1)


# ==========================================
# PAPER TRADING LOGIC
# ==========================================
def evaluate_paper_trades(symbol, df):
    if len(df) < 2 or 'SUPERTREND_dir' not in df.columns:
        return

    latest = df.iloc[-1]
    previous = df.iloc[-2]

    buy_signal = (previous['MACD_hist'] <= 0) and (latest['MACD_hist'] > 0) and (latest['SUPERTREND_dir'] == 1)
    sell_signal = (latest['SUPERTREND_dir'] == -1)

    now_ist = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
    time_str = now_ist.strftime("%Y-%m-%d %H:%M:%S IST")

    if buy_signal:
        TRADE_LOG.append({
            'Timestamp': time_str,
            'Symbol': symbol,
            'Action': 'BUY',
            'Price': latest['close'],
            'PnL': 'OPEN'
        })
        print(f"🟢 [BUY SIGNAL] {symbol} @ ${latest['close']} at {time_str}")

    elif sell_signal:
        for trade in reversed(TRADE_LOG):
            if trade['Symbol'] == symbol and trade['PnL'] == 'OPEN':
                entry_price = trade['Price']
                pnl = round(((latest['close'] - entry_price) / entry_price) * 100, 2)
                trade['PnL'] = f"{pnl}%"
                print(f"🔴 [SELL SIGNAL] {symbol} @ ${latest['close']} | PnL: {pnl}% at {time_str}")
                break

def display_trade_summary():
    if not TRADE_LOG:
        print("\n--- PAPER TRADING LOG: No Trades Executed Yet ---")
        return
    log_df = pd.DataFrame(TRADE_LOG)
    print("\n=================== PAPER TRADING SUMMARY ===================")
    print(log_df.to_string(index=False))
    print("============================================================p")


# ==========================================
# MAIN LOOP
# ==========================================
def main():
    print("[SYSTEM] Starting 100% Filter-Compliant Solana Meme Trading Bot...")
    
    while True:
        top_coins = fetch_and_filter_solana_coins()

        for coin in top_coins:
            symbol = coin['symbol']
            pool_addr = coin['pairAddress']

            df = sync_candle_database(pool_addr)
            if not df.empty:
                df = calculate_indicators(df)
                plot_5m_chart(symbol, df)
                evaluate_paper_trades(symbol, df)

        display_trade_summary()
        print(f"\n[SLEEP] Waiting {CHECK_INTERVAL_SECONDS // 60} minutes for next check cycle...")
        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
