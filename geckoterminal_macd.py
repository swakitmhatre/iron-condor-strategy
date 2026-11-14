import time
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta

# --- CONFIGURATION & CONSTANTS ---
NETWORK = "solana"
BASE_URL = "https://api.geckoterminal.com/api/v2"
HEADERS = {"Accept": "application/json;version=20230302"}

# Free tier rate-limit safeguard (~1.1 seconds between requests)
REQUEST_DELAY = 1.1  
IST_OFFSET = timedelta(hours=5, minutes=30)

def api_get(endpoint, params=None):
    url = f"{BASE_URL}/{endpoint}"
    try:
        time.sleep(REQUEST_DELAY)
        response = requests.get(url, headers=HEADERS, params=params)
        if response.status_code == 429:
            print("[!] Free tier rate limit hit (429). Backing off for 30 seconds...")
            time.sleep(30)
            return api_get(endpoint, params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"[Error] API request failed for {url}: {e}")
        return None

def convert_to_ist(utc_dt):
    """Converts a UTC datetime or pandas timestamp to IST string."""
    if pd.isna(utc_dt):
        return ""
    if isinstance(utc_dt, pd.Timestamp):
        utc_dt = utc_dt.to_pydatetime()
    ist_dt = utc_dt.astimezone(timezone(IST_OFFSET))
    return ist_dt.strftime('%Y-%m-%d %H:%M:%S IST')

def is_solana_sol_pair(attr):
    """
    Ensures the pool is explicitly paired against SOL (e.g. 'TOKEN / SOL')
    and ignores non-SOL quote pairs or cross-chain lookalikes.
    """
    name = attr.get("name", "").strip().upper()
    return "/ SOL" in name or name.endswith("SOL")

# --- STEP 1: ALL 4 RAW POOL DISCOVERY ENDPOINTS ---

def fetch_candidate_pools():
    pools = []
    seen_addresses = set()
    
    # 1. Trending Pools by Network
    print("[*] Fetching Trending Pools by Network...")
    for page in range(1, 4):
        data = api_get(f"networks/{NETWORK}/trending_pools", params={"page": page})
        if data and "data" in data:
            for p in data["data"]:
                if p["id"] not in seen_addresses:
                    seen_addresses.add(p["id"])
                    pools.append(p)
        time.sleep(REQUEST_DELAY)

    # 2. New Pools by Network
    print("[*] Fetching New Pools by Network...")
    for page in range(2, 5):
        data = api_get(f"networks/{NETWORK}/new_pools", params={"page": page})
        if data and "data" in data:
            for p in data["data"]:
                if p["id"] not in seen_addresses:
                    seen_addresses.add(p["id"])
                    pools.append(p)
        time.sleep(REQUEST_DELAY)

    # 3. Top Pools by Network
    print("[*] Fetching Top Pools by Network...")
    for page in range(1, 4):
        data = api_get(f"networks/{NETWORK}/pools", params={"page": page})
        if data and "data" in data:
            for p in data["data"]:
                if p["id"] not in seen_addresses:
                    seen_addresses.add(p["id"])
                    pools.append(p)
        time.sleep(REQUEST_DELAY)

    # 4. Top Pools by DEX (Raydium, Orca, Meteora)
    dex_list = ["raydium", "orca", "meteora"]
    for dex in dex_list:
        print(f"[*] Fetching Top Pools for DEX: {dex}...")
        for page in range(1, 3):
            data = api_get(f"networks/{NETWORK}/dexes/{dex}/pools", params={"page": page})
            if data and "data" in data:
                for p in data["data"]:
                    if p["id"] not in seen_addresses:
                        seen_addresses.add(p["id"])
                        pools.append(p)
            time.sleep(REQUEST_DELAY)

    print(f"[*] Total Unique Raw Pools Collected Across All 4 Endpoints: {len(pools)}")
    return pools

def fetch_token_deep_info(token_address):
    data = api_get(f"networks/{NETWORK}/tokens/{token_address}/info")
    if data and "data" in data:
        return data["data"].get("attributes", {})
    return {}

def filter_pools(pools, relax_filters=False):
    """
    Applies filters a -> q in exact sequence.
    If relax_filters is True (no tokens passed strict checks), criteria m -> q are bypassed.
    """
    filtered_list = []
    now = datetime.now(timezone.utc)
    passed_al_count = 0
    buyers=0
    lmc=0
    top_10=0
    buy_sell=0

    for pool in pools:
        attr = pool.get("attributes", {})
        # --- SOLANA PAIR GUARD ---
        if not is_solana_sol_pair(attr):
            continue
        relationships = pool.get("relationships", {})
        
        pool_address = pool.get("id")
        pool_name = attr.get("name", "Unknown Pool")
        created_at_str = attr.get("pool_created_at")
        liquidity_usd = float(attr.get("reserve_in_usd") or 0)
        market_cap = float(attr.get("market_cap_usd") or attr.get("fdv_usd") or 0)
        volume_24h = float(attr.get("volume_usd", {}).get("h24", 0) or 0)
        volume_6h = float(attr.get("volume_usd", {}).get("h6", 0) or 0)
        
        tx_24h = attr.get("transactions", {}).get("h24", {})
        buyers_24h = tx_24h.get("buyers", 0) or 0
        tx_count_24h = (tx_24h.get("buys", 0) or 0) + (tx_24h.get("sells", 0) or 0)
        
        if not created_at_str:
            continue
        created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        age_hours = (now - created_at).total_seconds() / 3600.0

        # --- Criteria a to l (Core Metric Gates) ---
        if not (1 <= age_hours <= 24): continue                         # a
        if not (30000 <= market_cap <= 5000000): continue               # b
        if liquidity_usd < 30000: continue                              # c
        if volume_24h < 50000 or volume_6h < 20000: continue            # d
        if tx_count_24h < 500: continue                                 # e
        
        buyers_6h = attr.get("transactions", {}).get("h6", {}).get("buyers", 0) or 0
        buyers_1h = attr.get("transactions", {}).get("h1", {}).get("buyers", 0) or 0
        if not (buyers_24h >= 300 and buyers_6h >= 50 and buyers_1h >= 20): continue # f
        buyers=buyers+1
        print("buyers---->",buyers)

        price_change_6h = float(attr.get("price_change_percentage", {}).get("h6", 0) or 0)
        if price_change_6h < 5.0: continue                              # g

        # Fetch Token Deep Info forHolder & Security Attributes (h -> q)
        try:
            base_token_rel = relationships.get("base_token", {}).get("data", {})
            token_address = base_token_rel.get("id", "").split("_")[-1]
        except Exception:
            continue

        if not token_address:
            continue

        token_info = fetch_token_deep_info(token_address)
        
        # Holder percentage parsing with robust null-checks
        holders_data = token_info.get("holders", {})
        top_holder_pct = 100.0  # default fallback if data is missing
        
        if isinstance(holders_data, dict):
            dist_pct = holders_data.get("distribution_percentage")
            if isinstance(dist_pct, dict):
                #top_10_str = dist_pct.get("top_10", "100")
                top_10_str = dist_pct.get("top_10")
                if top_10_str is not None:
                    top_holder_pct = float(top_10_str)
        else:
            # Fallback for alternative flat attributes if present
            alt_pct = token_info.get("top_10_holder_percent")
            if alt_pct is not None:
                top_holder_pct = float(alt_pct)

        #if top_holder_pct > 10.0: continue                       # h
        #top_10=top_10+1
        #print("top_holder_pct---->",top_10)

        price_change_1h = float(attr.get("price_change_percentage", {}).get("h1", 0) or 0)
        price_change_24h = float(attr.get("price_change_percentage", {}).get("h24", 0) or 0)
        #if not (price_change_1h > 0 and price_change_6h > 0 and price_change_24h > 0): continue # i
        #print("(price_change_1h > 0 and price_change_6h > 0 and price_change_24h > 0):")

        buys_24h = tx_24h.get("buys", 0) or 0
        sells_24h = tx_24h.get("sells", 0) or 0
        buy_sell_ratio = (buys_24h / sells_24h) if sells_24h > 0 else 0
        if buy_sell_ratio < 0.8: continue                               # j
        buy_sell=buy_sell+1
        print("buy_sell_ratio < 1.0:------->",buy_sell)

        makers_unique = tx_24h.get("users", 0) or 0
        #if makers_unique < 2500: continue                               # k

        liq_mcap_ratio = (liquidity_usd / market_cap) if market_cap > 0 else 0
        if liq_mcap_ratio <= 0.05: continue                             # l
        lmc=lmc+1
        print("liq_mcap_ratio----------->",lmc)

        passed_al_count += 1

        if relax_filters:
            filtered_list.append({
                "pool_address": pool_address,
                "pool_name": pool_name,
                "token_address": token_address,
                "age_hours": age_hours,
                "liquidity": liquidity_usd,
                "market_cap": market_cap
            })
            continue

        # --- Criteria m to q (Security & Social Gates) ---
        mint_auth = token_info.get("mint_authority")
        freeze_auth = token_info.get("freeze_authority")
        twitter_handle = token_info.get("twitter_handle")
        lp_burned = token_info.get("is_lp_burned", False)
        lp_locked = token_info.get("is_lp_locked", False)

        if not (lp_locked or lp_burned): continue                       # m & q (LP Lock / Burn)
        
        # Robust Twitter handle check (handling string 'none', None, or empty)
        if not twitter_handle or str(twitter_handle).lower() in ["none", "null", ""]: continue # n
        
        if mint_auth is not None and mint_auth != "": continue          # o
        if freeze_auth is not None and str(freeze_auth).lower() not in ["none", "null", ""]: continue # p

        filtered_list.append({
            "pool_address": pool_address,
            "pool_name": pool_name,
            "token_address": token_address,
            "age_hours": age_hours,
            "liquidity": liquidity_usd,
            "market_cap": market_cap
        })

    mode_label = "Relaxed (Bypassing M-Q)" if relax_filters else "Strict (M-Q Enforced)"
    print(f"[*] Filter Stats [{mode_label}] -> Passed A-L: {passed_al_count} | Final Filtered: {len(filtered_list)}")
    return filtered_list


# --- STEP 2: DYNAMIC CANDLE TIMEFRAMES & TECHNICAL INDICATORS (Market Cap Parity) ---

def get_candlestick_timeframe(age_hours):
    if 2 <= age_hours <= 8:
        return "minute", 5
    else:
        return "minute", 15

def fetch_ohlcv(pool_address, timeframe, aggregate, before_timestamp=None):
    clean_pool_addr = pool_address.split("_")[-1] if "_" in pool_address else pool_address
    endpoint = f"networks/{NETWORK}/pools/{clean_pool_addr}/ohlcv/{timeframe}"
    params = {"aggregate": aggregate, "limit": 100}
    if before_timestamp:
        params["before_timestamp"] = before_timestamp

    data = api_get(endpoint, params=params)
    if data and "data" in data:
        attributes = data["data"].get("attributes", {})
        ohlcv_list = attributes.get("ohlcv_list", [])
        if not ohlcv_list:
            return pd.DataFrame()
            
        df = pd.DataFrame(ohlcv_list, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)
        df = df.sort_values('timestamp').reset_index(drop=True)
        return df
    return pd.DataFrame()

def calculate_indicators(df, current_market_cap=None):
    """
    Calculates indicators on Market Cap USD series for 100% parity with DexScreener Mcap mode.
    """
    if df.empty or len(df) < 35:
        return df

    latest_close = df['close'].iloc[-1]
    if current_market_cap and current_market_cap > 0 and latest_close > 0:
        scaling_factor = current_market_cap / latest_close
        series = df['close'] * scaling_factor
        high_series = df['high'] * scaling_factor
        low_series = df['low'] * scaling_factor
    else:
        series = df['close']
        high_series = df['high']
        low_series = df['low']

    # 1. MACD (8, 17, 9)
    ema_fast = series.ewm(span=8, adjust=False).mean()
    ema_slow = series.ewm(span=17, adjust=False).mean()
    df['macd_line'] = ema_fast - ema_slow
    df['macd_signal'] = df['macd_line'].ewm(span=9, adjust=False).mean()
    df['histogram'] = df['macd_line'] - df['macd_signal']

    # 2. RSI (14)
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # 3. Robust Supertrend (10, 3) with safe initialization
    
    high=high_series
    low=low_series
    close=series
    hl2 = (high + low) / 2
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    
    # Use EMA for ATR to eliminate initial NaNs
    atr = tr.ewm(span=10, adjust=False).mean()

    basic_upper = hl2 + (3 * atr)
    basic_lower = hl2 - (3 * atr)
    
    final_upper = basic_upper.tolist()
    final_lower = basic_lower.tolist()
    supertrend = [True] * len(df)
    st_values = [0.0] * len(df)
    
    for i in range(1, len(df)):
        c_prev = close.iloc[i-1]
        c_curr = close.iloc[i]
        
        if basic_upper[i] < final_upper[i-1] or c_prev > final_upper[i-1]:
            final_upper[i] = basic_upper.iloc[i]
        else:
            final_upper[i] = final_upper[i-1]
            
        if basic_lower[i] > final_lower[i-1] or c_prev < final_lower[i-1]:
            final_lower[i] = basic_lower.iloc[i]
        else:
            final_lower[i] = final_lower[i-1]
            
        if c_curr <= final_upper[i]:
            supertrend[i] = False  # Bearish (Red)
        elif c_curr >= final_lower[i]:
            supertrend[i] = True   # Bullish (Green)
        else:
            supertrend[i] = supertrend[i-1]
            
        st_values[i] = final_lower[i] if supertrend[i] else final_upper[i]

    df['supertrend'] = st_values
    df['supertrend_dir'] = supertrend  # True = Bullish, False = Bearish
    return df
    '''

    hl2 = (high_series + low_series) / 2
    tr = pd.concat([
        high_series - low_series,
        (high_series - series.shift()).abs(),
        (low_series - series.shift()).abs()
    ], axis=1).max(axis=1)
    #atr = tr.rolling(window=10).mean()
    atr = tr.ewm(span=10, adjust=False).mean()

    basic_upper = hl2 + (3 * atr)
    basic_lower = hl2 - (3 * atr)
    
    final_upper = [0.0] * len(df)
    final_lower = [0.0] * len(df)
    supertrend = [True] * len(df)
    st_values = [0.0] * len(df)
    
    for i in range(len(df)):
        if i == 0:
            final_upper[i] = basic_upper.iloc[i]
            final_lower[i] = basic_lower.iloc[i]
            continue
            
        if basic_upper.iloc[i] < final_upper[i-1] or series.iloc[i-1] > final_upper[i-1]:
            final_upper[i] = basic_upper.iloc[i]
        else:
            final_upper[i] = final_upper[i-1]
            
        if basic_lower.iloc[i] > final_lower[i-1] or series.iloc[i-1] < final_lower[i-1]:
            final_lower[i] = basic_lower.iloc[i]
        else:
            final_lower[i] = final_lower[i-1]
            
        if series.iloc[i] <= final_upper[i]:
            supertrend[i] = False
        elif series.iloc[i] >= final_lower[i]:
            supertrend[i] = True
        else:
            supertrend[i] = supertrend[i-1]
            
        st_values[i] = final_lower[i] if supertrend[i] else final_upper[i]

    df['supertrend'] = st_values
    df['supertrend_dir'] = supertrend
    df['mcap_series'] = series
    return df
    '''
# --- STEP 3: CROSSOVER EVALUATION ---

def check_positive_crossover(curr, prev=None):
    if curr['macd_line'] <= curr['macd_signal']: return False
    if curr['macd_line'] <= 0: return False
    if curr['histogram'] <= 0.10 * abs(curr['macd_line']): return False
    if prev is not None and curr['histogram'] <= prev['histogram']: return False
    if not curr['supertrend_dir']: return False
    return True

def check_negative_crossover(row, prev_rows):
    if len(prev_rows) < 2: return False
    curr, prev1, prev2 = row['histogram'], prev_rows[-1]['histogram'], prev_rows[-2]['histogram']
    if row['macd_line'] < row['macd_signal']: return True
    if row['macd_line'] < 0: return True
    if prev1 != 0 and curr < (prev1 - (0.18 * prev1)):return True
    if curr < prev1 < prev2: return True
    if not row['supertrend_dir']: return True
    return False

# --- MAIN DUAL-SCHEDULE EXECUTION LOOP ---

def main():
    print(f"[{datetime.now(timezone.utc).astimezone(timezone(IST_OFFSET)).strftime('%Y-%m-%d %H:%M:%S IST')}] Starting Solana Meme Coin Quant Bot...")
    
    candidate_pools = []
    filtered_pools = []
    last_pool_fetch_time = 0
    POOL_FETCH_INTERVAL = 900       # 15 Minutes for raw pool discovery
    INDICATOR_CHECK_INTERVAL = 300  # 5 Minutes for active crossover monitoring

    while True:
        current_time = time.time()
        
        # 1. Refresh raw pool candidates every 15 minutes
        if current_time - last_pool_fetch_time >= POOL_FETCH_INTERVAL or not candidate_pools:
            print("\n[*] Running 15-Minute Raw Pool Discovery & Filtering Routine...")
            candidate_pools = fetch_candidate_pools()
            filtered_pools = filter_pools(candidate_pools, relax_filters=False)
            
            if not filtered_pools:
                print("[*] No tokens met strict M->Q filters. Activating relaxation fallback (bypassing M-Q)...")
                filtered_pools = filter_pools(candidate_pools, relax_filters=True)
            
            last_pool_fetch_time = current_time

        # 2. Check 5-Min Indicators and print active/historical signals
        print(f"\n[*] [{datetime.now(timezone.utc).astimezone(timezone(IST_OFFSET)).strftime('%H:%M:%S IST')}] Checking 5-Min MACD Crossovers for {len(filtered_pools)} filtered tokens...")

        historical_trades = []
        all_current_signals_detailed = []

        for item in filtered_pools:
            pool_addr = item["pool_address"]
            pool_name = item["pool_name"]
            age = item["age_hours"]
            tf, agg = get_candlestick_timeframe(age)
            
            df = fetch_ohlcv(pool_addr, tf, agg)
            if df.empty or len(df) < 35:
                continue
                
            df = calculate_indicators(df)

            in_trade = False
            entry_time = None
            entry_price = 0.0
            entry_idx = 0

            # Start checking crossovers only after index 20 to let MACD/Supertrend warm up
            start_idx = max(2, len(df) - len(df) + 20) if len(df) >= 20 else 2

            for i in range(start_idx, len(df)):
                prev_prev = df.iloc[i-2]
                prev = df.iloc[i-1]
                curr = df.iloc[i]

                is_pos_cross = check_positive_crossover(curr, prev)
                is_neg_cross = check_negative_crossover(curr, [prev_prev.to_dict(), prev.to_dict()])

                if not in_trade and is_pos_cross:
                    in_trade = True
                    entry_time = curr['timestamp']
                    entry_price = curr['close']
                    entry_idx = i
                elif in_trade and is_neg_cross:
                    exit_time = curr['timestamp']
                    exit_price = curr['close']
                    pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0
                    historical_trades.append({
                        "Pool Name": pool_name,
                        "DexScreener Address": pool_addr,
                        "Entry (IST)": convert_to_ist(entry_time),
                        "Exit (IST)": convert_to_ist(exit_time),
                        "PnL (%)": round(pnl_pct, 2)
                    })
                    in_trade = False

            # If the trade is STILL active on the latest candle, display the full sequence in Table 2
            if in_trade:
                active_df = df.iloc[entry_idx:]
                for _, row in active_df.iterrows():
                    candle_close = row['close']
                    live_pnl_pct = ((candle_close - entry_price) / entry_price) * 100.0
                    st_status = "BULLISH" if row.get('supertrend_dir', True) else "BEARISH"
                    
                    all_current_signals_detailed.append({
                        "Pool Name": pool_name,
                        "DexScreener Pool Address": pool_addr,
                        "Timestamp (IST)": convert_to_ist(row['timestamp']),
                        "Open": f"{row['open']:.8f}",
                        "High": f"{row['high']:.8f}",
                        "Low": f"{row['low']:.8f}",
                        "Close": f"{row['close']:.8f}",
                        "MACD": f"{row.get('macd_line', 0):.6f}",
                        "MACD Signal": f"{row.get('macd_signal', 0):.6f}",
                        "Histogram": f"{row.get('histogram', 0):.6f}",
                        "Supertrend": f"{row.get('supertrend', 0):.8f} ({st_status})",
                        "RSI": f"{row.get('rsi', 0):.1f}",
                        "Live PnL (%)": f"{live_pnl_pct:+.2f}%"
                    })
        # --- RENDER TABULAR DATA OUTPUTS WITH IST ---
        print("\n" + "="*130)
        print("TABLE 1: HISTORICAL POSITIVE MACD CROSSOVER TRADES & POOL ADDRESSES (IST Timestamps)")
        print("="*130)
        if historical_trades:
            df_hist = pd.DataFrame(historical_trades)
            print(df_hist.to_string(index=False))
        else:
            print("No completed historical crossover trades found in current dataset.")

        print("\n" + "="*130)
        print("TABLE 2: CURRENT ACTIVE POSITIVE MACD CROSSOVERS - LAST 5 TUPLES WITH LIVE PnL (%) [MCAP MODE]")
        print("="*130)
        if all_current_signals_detailed:
            df_curr = pd.DataFrame(all_current_signals_detailed)
            print(df_curr.to_string(index=False))
        else:
            print("No current positive crossover detected on latest candles for any token.")
        print("="*130 + "\n")

        print(f"[*] Indicator check completed. Sleeping for 5 minutes before next 5-min candle evaluation...")
        time.sleep(INDICATOR_CHECK_INTERVAL)

if __name__ == "__main__":
    main()
