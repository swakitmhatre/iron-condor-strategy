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
    for page in range(1, 4):
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
    Applies filters a -> q. 
    If relax_filters is True (no tokens passed strict checks), criteria g -> q are bypassed.
    """
    filtered_list = []
    now = datetime.now(timezone.utc)
    passed_af_count = 0

    for pool in pools:
        attr = pool.get("attributes", {})
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

        # --- Criteria A to F (Mandatory) ---
        if not (1 <= age_hours <= 24): continue
        if not (30000 <= market_cap <= 2000000): continue
        if liquidity_usd < 30000: continue
        if volume_24h < 50000: continue
        if volume_6h < 20000: continue
        if tx_count_24h < 500: continue
        if buyers_24h < 300: continue

        passed_af_count += 1

        if relax_filters:
            filtered_list.append({
                "pool_address": pool_address,
                "pool_name": pool_name,
                "token_address": None,
                "age_hours": age_hours,
                "liquidity": liquidity_usd,
                "market_cap": market_cap
            })
            continue

        # --- Fetch Token Deep Info for Criteria G to Q ---
        try:
            base_token_rel = relationships.get("base_token", {}).get("data", {})
            token_address = base_token_rel.get("id", "").split("_")[-1]
        except Exception:
            continue

        if not token_address:
            continue

        token_info = fetch_token_deep_info(token_address)
        
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

        mint_auth = token_info.get("mint_authority")
        freeze_auth = token_info.get("freeze_authority")
        twitter_handle = token_info.get("twitter_handle")
        top_holder_pct = float(token_info.get("top_10_holder_percent", 0) or 0)
        lp_burned = token_info.get("is_lp_burned", False)
        lp_locked = token_info.get("is_lp_locked", False)

        # Enforcing criteria g through q
        if buyers_6h < 50 or buyers_1h < 20: continue
        if price_change_6h < 5.0: continue
        if not (lp_locked or lp_burned): continue
        if not twitter_handle: continue
        if top_holder_pct > 10.0: continue
        if not (price_change_1h > 0 and price_change_6h > 0 and price_change_24h > 0): continue
        if buy_sell_ratio < 1.5: continue
        if makers_unique < 2500: continue
        if liq_mcap_ratio <= 0.05: continue
        if mint_auth is not None and mint_auth != "": continue
        if freeze_auth is not None: continue

        filtered_list.append({
            "pool_address": pool_address,
            "pool_name": pool_name,
            "token_address": token_address,
            "age_hours": age_hours,
            "liquidity": liquidity_usd,
            "market_cap": market_cap
        })

    mode_label = "Relaxed (Bypassing G-Q)" if relax_filters else "Strict (G-Q Enforced)"
    print(f"[*] Filter Stats [{mode_label}] -> Passed A-F: {passed_af_count} | Final Filtered: {len(filtered_list)}")
    return filtered_list

# --- STEP 2: DYNAMIC CANDLE TIMEFRAMES & TECHNICAL INDICATORS ---

def get_candlestick_timeframe(age_hours):
    """
    - 2 to 8 hours: 5 minute candles (timeframe='minute', aggregate=5)
    - Above 8+ hours: 15 minute candles (timeframe='minute', aggregate=15)
    """
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

def calculate_indicators(df):
    if df.empty or len(df) < 35:
        return df

    close = df['close']
    ema_fast = close.ewm(span=8, adjust=False).mean()
    ema_slow = close.ewm(span=17, adjust=False).mean()
    df['macd_line'] = ema_fast - ema_slow
    df['macd_signal'] = df['macd_line'].ewm(span=9, adjust=False).mean()
    df['histogram'] = df['macd_line'] - df['macd_signal']

    # RSI (14)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    hl2 = (df['high'] + df['low']) / 2
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
    df['supertrend_dir'] = supertrend
    return df

# --- STEP 3: CROSSOVER EVALUATION ---

def check_positive_crossover(row, prev_row=None):
    if row['macd_line'] <= row['macd_signal']: return False
    if row['macd_line'] <= 0: return False
    if row['histogram'] <= 0.15 * abs(row['macd_line']): return False
    if prev_row is not None and row['histogram'] <= prev_row['histogram']: return False
    if not row['supertrend_dir']: return False
    if 'rsi' in row and not pd.isna(row['rsi']):
        if not (45 <= row['rsi'] <= 75): return False
    return True

def check_negative_crossover(row, prev_rows):
    if len(prev_rows) < 2: return False
    curr, prev1, prev2 = row['histogram'], prev_rows[-1]['histogram'], prev_rows[-2]['histogram']
    if row['macd_line'] < row['macd_signal']: return True
    if row['macd_line'] < 0: return True
    if prev1 != 0 and curr < 0.18 * prev1: return True
    if curr < prev1 < prev2: return True
    if not row['supertrend_dir']: return True
    return False

# --- MAIN EXECUTION LOOP ---

def main():
    print(f"[{datetime.now(timezone.utc).astimezone(timezone(IST_OFFSET)).strftime('%Y-%m-%d %H:%M:%S IST')}] Starting Solana Meme Coin Quant Bot...")
    
    while True:
        pools = fetch_candidate_pools()
        filtered = filter_pools(pools, relax_filters=False)
        
        # Adaptive Fallback: Relax filters if strict G-Q yields no matches
        if not filtered:
            print("[*] No tokens met strict G->Q filters. Activating relaxation fallback (bypassing G->Q)...")
            filtered = filter_pools(pools, relax_filters=True)

        current_crossover_detected = False
        historical_trades = []
        current_signals_detailed = []

        print(f"[*] Processing indicators for {len(filtered)} filtered token(s)...")
        for item in filtered:
            pool_addr = item["pool_address"]
            pool_name = item["pool_name"]
            age = item["age_hours"]
            tf, agg = get_candlestick_timeframe(age)
            
            df = fetch_ohlcv(pool_addr, tf, agg)
            df = calculate_indicators(df)
            
            if df.empty or len(df) < 5:
                continue

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
                        "Pool Name": pool_name,
                        "Entry (IST)": convert_to_ist(entry_time),
                        "Exit (IST)": convert_to_ist(exit_time),
                        "PnL (%)": round(pnl_pct, 2)
                    })
                    in_trade = False

            latest_curr = df.iloc[-1]
            latest_prev = df.iloc[-2]
            if check_positive_crossover(latest_curr, latest_prev):
                current_crossover_detected = True
                
                # Last 5 tuples for active crossover token
                last_5_df = df.tail(5)
                for _, row in last_5_df.iterrows():
                    st_status = "BULLISH" if row.get('supertrend_dir', True) else "BEARISH"
                    current_signals_detailed.append({
                        "Pool Name": pool_name,
                        "Timestamp (IST)": convert_to_ist(row['timestamp']),
                        "Open": f"{row['open']:.8f}",
                        "High": f"{row['high']:.8f}",
                        "Low": f"{row['low']:.8f}",
                        "Close": f"{row['close']:.8f}",
                        "MACD": f"{row.get('macd_line', 0):.6f}",
                        "MACD Signal": f"{row.get('macd_signal', 0):.6f}",
                        "Histogram": f"{row.get('histogram', 0):.6f}",
                        "Supertrend": f"{row.get('supertrend', 0):.8f} ({st_status})",
                        "RSI": f"{row.get('rsi', 0):.1f}"
                    })

        # --- RENDER TABULAR DATA OUTPUTS WITH IST ---
        print("\n" + "="*120)
        print("TABLE 1: HISTORICAL POSITIVE MACD CROSSOVER TRADES (IST Timestamps)")
        print("="*120)
        if historical_trades:
            df_hist = pd.DataFrame(historical_trades)
            print(df_hist.to_string(index=False))
        else:
            print("No completed historical crossover trades found in current dataset.")

        print("\n" + "="*120)
        print("TABLE 2: CURRENT ACTIVE POSITIVE MACD CROSSOVER - LAST 5 CANDLES (IST Timestamps)")
        print("="*120)
        if current_signals_detailed:
            df_curr = pd.DataFrame(current_signals_detailed)
            print(df_curr.to_string(index=False))
        else:
            print("No current positive crossover detected on latest candles.")
        print("="*120 + "\n")

        # --- EXECUTION CONTROL LOGIC ---
        if current_crossover_detected:
            print("[+] Current positive crossover detected! Pausing for 5 minutes...")
            time.sleep(300)
        else:
            print("[-] No current positive crossover found. Re-fetching raw tokens in 15 minutes...")
            time.sleep(900)

if __name__ == "__main__":
    main()
