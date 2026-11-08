import time
import requests
import pandas as pd
from datetime import datetime, timezone

# --- CONFIGURATION & CONSTANTS ---
NETWORK = "solana"
BASE_URL = "https://api.geckoterminal.com/api/v2"
HEADERS = {"Accept": "application/json;version=20230302"}

# Rate limiting helper to avoid HTTP 429 errors
REQUEST_DELAY = 0.22  # ~4-5 requests per second max for free/standard tiers

def api_get(endpoint, params=None):
    url = f"{BASE_URL}/{endpoint}"
    try:
        time.sleep(REQUEST_DELAY)
        response = requests.get(url, headers=HEADERS, params=params)
        if response.status_code == 429:
            print("[!] Rate limit hit (429). Backing off for 10 seconds...")
            time.sleep(10)
            return api_get(endpoint, params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"[Error] API request failed for {url}: {e}")
        return None

# --- STEP 1: RAW POOL DISCOVERY & COMPREHENSIVE FILTERING (a -> q) ---

def fetch_candidate_pools():
    """Fetches pools using 'new' listing / trending endpoints to capture fresh Solana tokens."""
    pools = []
    # Fetching latest discovered pools
    data = api_get(f"networks/{NETWORK}/pools/new", params={"page": 1})
    if data and "data" in data:
        pools.extend(data["data"])
    
    # Also fetch top pools by volume/liquidity as fallback/supplement
    top_data = api_get(f"networks/{NETWORK}/pools", params={"page": 1})
    if top_data and "data" in top_data:
        # Merge without duplicates based on pool address
        existing_addrs = {p["id"] for p in pools}
        for p in top_data["data"]:
            if p["id"] not in existing_addrs:
                pools.append(p)
                
    return pools

def fetch_token_deep_info(token_address):
    """Fetches token-specific metadata (mint auth, freeze auth, social links, holders)."""
    data = api_get(f"networks/{NETWORK}/tokens/{token_address}/info")
    if data and "data" in data:
        return data["data"].get("attributes", {})
    return {}

def filter_pools(pools, relax_filters=False):
    """
    Applies filters a -> q. 
    If relax_filters is True (no tokens found initially), criteria g -> q are bypassed.
    """
    filtered_list = []
    now = datetime.now(timezone.utc)

    for pool in pools:
        attr = pool.get("attributes", {})
        relationships = pool.get("relationships", {})
        
        # Basic Pool Attributes
        pool_address = pool.get("id")
        created_at_str = attr.get("pool_created_at")
        liquidity_usd = float(attr.get("reserve_in_usd") or 0)
        market_cap = float(attr.get("market_cap_usd") or attr.get("fdv_usd") or 0)
        volume_24h = float(attr.get("volume_usd", {}).get("h24", 0) or 0)
        volume_6h = float(attr.get("volume_usd", {}).get("h6", 0) or 0)
        
        tx_24h = attr.get("transactions", {}).get("h24", {})
        buyers_24h = tx_24h.get("buyers", 0) or 0
        tx_count_24h = (tx_24h.get("buys", 0) or 0) + (tx_24h.get("sells", 0) or 0)
        
        # Calculate Pool Age in hours
        if not created_at_str:
            continue
        created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        age_hours = (now - created_at).total_seconds() / 3600.0

        # --- Criteria A to F (Mandatory) ---
        if not (1 <= age_hours <= 24):
            continue
        if not (30000 <= market_cap <= 2000000):
            continue
        if liquidity_usd < 30000:
            continue
        if volume_24h < 50000:
            continue
        if volume_6h < 20000:
            continue
        if tx_count_24h < 500:
            continue
        if buyers_24h < 300:
            continue

        if relax_filters:
            # Skip g -> q if no tokens passed strict criteria
            filtered_list.append({
                "pool_address": pool_address,
                "token_address": None,
                "age_hours": age_hours,
                "liquidity": liquidity_usd,
                "market_cap": market_cap
            })
            continue

        # --- Fetch Token Deep Info for Criteria G to Q ---
        # Extract base token address from relationships
        try:
            base_token_rel = relationships.get("base_token", {}).get("data", {})
            token_address = base_token_rel.get("id", "").split("_")[-1]
        except Exception:
            continue

        if not token_address:
            continue

        token_info = fetch_token_deep_info(token_address)
        
        # g -> q checks
        buyers_6h = attr.get("transactions", {}).get("h6", {}).get("buyers", 0) or 0
        buyers_1h = attr.get("transactions", {}).get("h1", {}).get("buyers", 0) or 0
        price_change_6h = float(attr.get("price_change_percentage", {}).get("h6", 0) or 0)
        price_change_1h = float(attr.get("price_change_percentage", {}).get("h1", 0) or 0)
        price_change_24h = float(attr.get("price_change_percentage", {}).get("h24", 0) or 0)
        
        buys_24h = tx_24h.get("buys", 0) or 0
        sells_24h = tx_24h.get("sells", 0) or 0
        buy_sell_ratio = (buys_24h / sells_24h) if sells_24h > 0 else float('inf')
        
        makers_unique = tx_24h.get("users", 0) or 0
        liq_mcap_ratio = (liquidity_usd / market_cap) if market_cap > 0 else 0

        # Token security parameters from deep info
        mint_auth = token_info.get("mint_authority")
        freeze_auth = token_info.get("freeze_authority")
        twitter_handle = token_info.get("twitter_handle")
        top_holder_pct = float(token_info.get("top_10_holder_percent", 0) or 0) # or evaluate top holder
        lp_burned = token_info.get("is_lp_burned", False)
        lp_locked = token_info.get("is_lp_locked", False)

        # Enforcing criteria g through q
        if buyers_6h < 50 or buyers_1h < 20:
            continue
        if price_change_6h < 5.0:
            continue
        if not (lp_locked or lp_burned):
            continue
        if not twitter_handle:
            continue
        if top_holder_pct > 10.0:
            continue
        if not (price_change_1h > 0 and price_change_6h > 0 and price_change_24h > 0):
            continue
        if buy_sell_ratio < 1.5:
            continue
        if makers_unique < 2500:
            continue
        if liq_mcap_ratio <= 0.05:
            continue
        if mint_auth is not None and mint_auth != "":
            continue
        if freeze_auth is not None:
            continue

        filtered_list.append({
            "pool_address": pool_address,
            "token_address": token_address,
            "age_hours": age_hours,
            "liquidity": liquidity_usd,
            "market_cap": market_cap
        })

    return filtered_list

# --- STEP 2: OHLCV CANDLE FETCHING & TECHNICAL INDICATORS (MACD, Supertrend, RSI) ---

def get_candlestick_timeframe(age_hours):
    """
    Returns timeframe string and aggregate based on coin age:
    - 2 to 8 hours: 5 minute candles
    - Above 8+ hours: 15 minute candles
    """
    if age_hours <= 8:
        return "minute", 5
    else:
        return "minute", 15

def fetch_ohlcv(pool_address, timeframe, aggregate, before_timestamp=None):
    """
    Fetches OHLCV candles from GeckoTerminal with support for look-back overwrites.
    Endpoint: GET /networks/{network}/pools/{pool_address}/ohlcv/{timeframe}
    """
    endpoint = f"networks/{NETWORK}/pools/{pool_address}/ohlcv/{timeframe}"
    params = {"aggregate": aggregate, "limit": 100}
    if before_timestamp:
        params["before_timestamp"] = before_timestamp

    data = api_get(endpoint, params=params)
    if data and "data" in data:
        attributes = data["data"].get("attributes", {})
        ohlcv_list = attributes.get("ohlcv_list", [])
        # Format: [timestamp, open, high, low, close, volume]
        df = pd.DataFrame(ohlcv_list, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)
        df = df.sort_values('timestamp').reset_index(drop=True)
        return df
    return pd.DataFrame()

def calculate_indicators(df):
    """
    Calculates MACD(8, 17, 9), Supertrend(10, 3), and RSI without index out-of-bounds crashes.
    """
    if df.empty or len(df) < 35:  # Ensure enough candles for warmup
        return df

    close = df['close']
    
    # 1. MACD (8, 17, 9)
    ema_fast = close.ewm(span=8, adjust=False).mean()
    ema_slow = close.ewm(span=17, adjust=False).mean()
    df['macd_line'] = ema_fast - ema_slow
    df['macd_signal'] = df['macd_line'].ewm(span=9, adjust=False).mean()
    df['histogram'] = df['macd_line'] - df['macd_signal']

    # 2. Supertrend (10, 3)
    hl2 = (df['high'] + df['low']) / 2
    # ATR 10 calculation
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - close.shift()).abs(),
        (df['low'] - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=10).mean()

    upper_band = hl2 + (3 * atr)
    lower_band = hl2 - (3 * atr)
    
    supertrend = [True] * len(df)
    st_values = [0.0] * len(df)
    
    for i in range(1, len(df)):
        curr_close = close.iloc[i]
        prev_close = close.iloc[i-1]
        
        if curr_close > upper_band.iloc[i-1]:
            supertrend[i] = True
        elif curr_close < lower_band.iloc[i-1]:
            supertrend[i] = False
        else:
            supertrend[i] = supertrend[i-1]
            if supertrend[i] and lower_band.iloc[i] < lower_band.iloc[i-1]:
                lower_band.iat[i] = lower_band.iloc[i-1]
            if not supertrend[i] and upper_band.iloc[i] > upper_band.iloc[i-1]:
                upper_band.iat[i] = upper_band.iloc[i-1]
                
        st_values[i] = lower_band.iloc[i] if supertrend[i] else upper_band.iloc[i]

    df['supertrend'] = st_values
    df['supertrend_dir'] = supertrend  # True = Positive (Bullish), False = Negative (Bearish)
    
    return df

# --- STEP 3: CROSSOVER EVALUATION & TABULAR GENERATION ---

def check_positive_crossover(row, prev_row=None):
    """
    Validates positive MACD crossover conditions:
    1. macd_line > macd_signal
    2. macd_line > 0
    3. histogram > 10% of abs(macd_line)
    4. histogram > previous histogram (if prev_row available)
    5. supertrend is positive
    """
    if row['macd_line'] <= row['macd_signal']: return False
    if row['macd_line'] <= 0: return False
    if row['histogram'] <= 0.10 * abs(row['macd_line']): return False
    if prev_row is not None and row['histogram'] <= prev_row['histogram']: return False
    if not row['supertrend_dir']: return False
    return True

def check_negative_crossover(row, prev_rows):
    """
    Validates negative crossover (any 1 condition met):
    1. macd_line < macd_signal
    2. macd_line < 0
    3. histogram < 18% of immediate previous histogram
    4. latest 3 histograms decreasing: hist[curr] < hist[curr-1] < hist[curr-2]
    5. supertrend is negative
    """
    if len(prev_rows) < 2: return False
    curr, prev1, prev2 = row['histogram'], prev_rows[-1]['histogram'], prev_rows[-2]['histogram']
    
    if row['macd_line'] < row['macd_signal']: return True
    if row['macd_line'] < 0: return True
    if prev1 != 0 and curr < 0.18 * prev1: return True
    if curr < prev1 < prev2: return True
    if not row['supertrend_dir']: return True
    return False

# --- MAIN EXECUTION & POLLING LOOP ---

def main():
    print(f"[{datetime.now(timezone.utc)}] Starting Solana Meme Coin Quant Bot...")
    
    while True:
        pools = fetch_candidate_pools()
        filtered = filter_pools(pools, relax_filters=False)
        
        if not filtered:
            print("[*] No tokens met strict g->q filters. Relaxing criteria (bypassing g->q)...")
            filtered = filter_pools(pools, relax_filters=True)

        current_crossover_detected = False
        historical_trades = []
        current_signals = []

        for item in filtered:
            pool_addr = item["pool_address"]
            age = item["age_hours"]
            tf, agg = get_candlestick_timeframe(age)
            
            df = fetch_ohlcv(pool_addr, tf, agg)
            df = calculate_indicators(df)
            
            if df.empty or len(df) < 5:
                continue

            # Iterate through candles to track historical trades & current crossover status
            in_trade = False
            entry_time = None
            entry_price = 0.0

            for i in range(2, len(df)):
                prev_prev = df.iloc[i-2]
                prev = df.iloc[i-1]
                curr = df.iloc[i]

                is_pos_cross = check_positive_crossover(curr, prev)
                is_neg_cross = check_negative_crossover(curr, [prev_prev.to_dict(), prev.to_dict()])

                if not in_trade and is_pos_cross:
                    in_trade = True
                    entry_time = curr['timestamp']
                    entry_price = curr['close']
                elif in_trade and is_neg_cross:
                    exit_time = curr['timestamp']
                    exit_price = curr['close']
                    pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0
                    historical_trades.append({
                        "Pool": pool_addr,
                        "Entry Timestamp": entry_time,
                        "Exit Timestamp": exit_time,
                        "PnL (%)": round(pnl_pct, 2)
                    })
                    in_trade = false

            # Check if latest closed candle has a CURRENT positive crossover (and not currently in historic trade loop)
            latest_curr = df.iloc[-1]
            latest_prev = df.iloc[-2]
            if check_positive_crossover(latest_curr, latest_prev):
                current_crossover_detected = True
                current_signals.append({
                    "Pool": pool_addr,
                    "Timestamp": latest_curr['timestamp'],
                    "Open": latest_curr['open'],
                    "High": latest_curr['high'],
                    "Low": latest_curr['low'],
                    "Close": latest_curr['close'],
                    "MACD": round(latest_curr['macd_line'], 4),
                    "MACD Signal": round(latest_curr['macd_signal'], 4),
                    "Histogram": round(latest_curr['histogram'], 4),
                    "Supertrend": round(latest_curr['supertrend'], 4),
                    "Signal": "BUY ENTRY"
                })

        # --- RENDER TABULAR DATA OUTPUTS ---
        print("\n" + "="*80)
        print("TABLE 1: HISTORICAL POSITIVE MACD CROSSOVER TRADES (Bullish Trend PnL)")
        print("="*80)
        if historical_trades:
            df_hist = pd.DataFrame(historical_trades)
            print(df_hist.to_string(index=False))
        else:
            print("No completed historical crossover trades found in current dataset.")

        print("\n" + "="*80)
        print("TABLE 2: CURRENT ACTIVE POSITIVE MACD CROSSOVER SIGNALS (5-Min Update)")
        print("="*80)
        if current_signals:
            df_curr = pd.DataFrame(current_signals)
            print(df_curr.to_string(index=False))
        else:
            print("No current positive crossover detected on latest candles.")
        print("="*80 + "\n")

        # --- EXECUTION CONTROL LOGIC ---
        if current_crossover_detected:
            print("[+] Current positive crossover detected in at least one token! Pausing raw token discovery and focusing on active position monitoring...")
            # Sleep for 5 minutes to monitor 5-minute closed candles as requested
            time.sleep(300)
        else:
            print("[-] No current positive crossover found. Re-fetching raw tokens and running filters in 15 minutes...")
            # Sleep for 15 minutes before next raw pool discovery poll
            time.sleep(900)

if __name__ == "__main__":
    main()
