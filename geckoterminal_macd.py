import time
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta

# --- CONFIGURATION & CONSTANTS ---
NETWORK = "solana"
BASE_URL = "https://api.geckoterminal.com/api/v2"
HEADERS = {"Accept": "application/json;version=20230302"}

# Safe delay to remain within GeckoTerminal free tier limits (~30 req/min)
REQUEST_DELAY = 1.8  
IST_OFFSET = timedelta(hours=5, minutes=30)

def api_get(endpoint, params=None):
    url = f"{BASE_URL}/{endpoint}"
    try:
        time.sleep(REQUEST_DELAY)
        response = requests.get(url, headers=HEADERS, params=params)
        if response.status_code == 429:
            print("[!] Rate limit hit (429). Pausing for 30 seconds...")
            time.sleep(30)
            return api_get(endpoint, params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"[Error] Request failed for {url}: {e}")
        return None

def convert_to_ist(utc_dt):
    if pd.isna(utc_dt):
        return ""
    if isinstance(utc_dt, pd.Timestamp):
        utc_dt = utc_dt.to_pydatetime()
    ist_dt = utc_dt.astimezone(timezone(IST_OFFSET))
    return ist_dt.strftime('%Y-%m-%d %H:%M:%S IST')

def is_solana_sol_pair(attr):
    name = attr.get("name", "").strip().upper()
    return "/ SOL" in name or name.endswith("SOL")

# --- STEP 1: POOL DISCOVERY & FILTERING ---

def fetch_candidate_pools():
    pools = []
    seen_addresses = set()
    
    endpoints = [
        f"networks/{NETWORK}/trending_pools",
        f"networks/{NETWORK}/new_pools",
        f"networks/{NETWORK}/pools"
    ]
    
    for ep in endpoints:
        print(f"[*] Fetching: {ep}...")
        for page in range(1, 3):
            data = api_get(ep, params={"page": page})
            if data and "data" in data:
                for p in data["data"]:
                    if p["id"] not in seen_addresses:
                        seen_addresses.add(p["id"])
                        pools.append(p)
            time.sleep(REQUEST_DELAY)

    dex_list = ["raydium", "orca", "meteora"]
    for dex in dex_list:
        print(f"[*] Fetching DEX Pools: {dex}...")
        data = api_get(f"networks/{NETWORK}/dexes/{dex}/pools", params={"page": 1})
        if data and "data" in data:
            for p in data["data"]:
                if p["id"] not in seen_addresses:
                    seen_addresses.add(p["id"])
                    pools.append(p)
        time.sleep(REQUEST_DELAY)

    print(f"[*] Total Unique Raw Pools Collected: {len(pools)}")
    return pools

def fetch_token_deep_info(token_address):
    endpoint = f"networks/{NETWORK}/tokens/{token_address}/info"
    data = api_get(endpoint)
    if data and "data" in data:
        return data["data"].get("attributes", {})
    return {}

def filter_pools(pools, relax_filters=False):
    filtered_list = []
    now = datetime.now(timezone.utc)
    passed_al_count = 0

    for pool in pools:
        attr = pool.get("attributes", {})
        
        # Ensure pool is paired against SOL
        if not is_solana_sol_pair(attr):
            continue

        relationships = pool.get("relationships", {})
        pool_address = pool.get("id").split("_")[-1]
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

        # --- Criteria a to l ---
        if not (1 <= age_hours <= 24): continue
        if not (30000 <= market_cap <= 20000000): continue
        if liquidity_usd < 30000: continue
        if volume_24h < 50000 or volume_6h < 20000: continue
        if tx_count_24h < 500: continue
        
        buyers_6h = attr.get("transactions", {}).get("h6", {}).get("buyers", 0) or 0
        buyers_1h = attr.get("transactions", {}).get("h1", {}).get("buyers", 0) or 0
        if not (buyers_24h >= 300 and buyers_6h >= 50 and buyers_1h >= 20): continue

        price_change_6h = float(attr.get("price_change_percentage", {}).get("h6", 0) or 0)
        if price_change_6h < 5.0: continue

        try:
            base_token_rel = relationships.get("base_token", {}).get("data", {})
            token_address = base_token_rel.get("id", "").split("_")[-1]
        except Exception:
            continue

        if not token_address:
            continue

        token_info = fetch_token_deep_info(token_address)
        
        # Holder check with safe fallbacks
        holders_data = token_info.get("holders", {})
        top_holder_pct = 100.0
        if isinstance(holders_data, dict):
            dist_pct = holders_data.get("distribution_percentage")
            if isinstance(dist_pct, dict):
                top_10_str = dist_pct.get("top_10", "100")
                if top_10_str is not None:
                    top_holder_pct = float(top_10_str)
        
        if top_holder_pct > 10.0: continue

        price_change_1h = float(attr.get("price_change_percentage", {}).get("h1", 0) or 0)
        price_change_24h = float(attr.get("price_change_percentage", {}).get("h24", 0) or 0)
        #if not (price_change_1h > 0 and price_change_6h > 0 and price_change_24h > 0): continue

        buys_24h = tx_24h.get("buys", 0) or 0
        sells_24h = tx_24h.get("sells", 0) or 0
        buy_sell_ratio = (buys_24h / sells_24h) if sells_24h > 0 else 0
        if buy_sell_ratio < 0.8: continue

       # makers_unique = tx_24h.get("users", 0) or 0
        #if makers_unique < 2500: continue

        liq_mcap_ratio = (liquidity_usd / market_cap) if market_cap > 0 else 0
        if liq_mcap_ratio <= 0.05: continue

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

        # --- Criteria m to q ---
        mint_auth = token_info.get("mint_authority")
        freeze_auth = token_info.get("freeze_authority")
        twitter_handle = token_info.get("twitter_handle")
        lp_burned = token_info.get("is_lp_burned", False)
        lp_locked = token_info.get("is_lp_locked", False)

        if not (lp_locked or lp_burned) and (lp_locked is not False): 
            pass
        
        if mint_auth is not None and str(mint_auth).lower() not in ["none", "null", ""]: continue
        if freeze_auth is not None and str(freeze_auth).lower() not in ["none", "null", ""]: continue

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

# --- STEP 2: DYNAMIC CANDLES & INDICATORS ---

def get_candlestick_timeframe(age_hours):
    return ("minute", 5) if 2 <= age_hours <= 8 else ("minute", 15)

def fetch_ohlcv(pool_address, timeframe, aggregate):
    clean_addr = pool_address.split("_")[-1]
    endpoint = f"networks/{NETWORK}/pools/{clean_addr}/ohlcv/{timeframe}"
    data = api_get(endpoint, params={"aggregate": aggregate, "limit": 100})
    if data and "data" in data:
        ohlcv_list = data["data"].get("attributes", {}).get("ohlcv_list", [])
        if ohlcv_list:
            df = pd.DataFrame(ohlcv_list, columns=["timestamp", "open", "high", "low", "close", "volume"])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)
            return df.sort_values('timestamp').reset_index(drop=True)
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

    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # Supertrend (TradingView Recursive Formula)
    hl2 = (df['high'] + df['low']) / 2
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - close.shift()).abs(),
        (df['low'] - close.shift()).abs()
    ], axis=1).max(axis=1)
    atr = tr.rolling(window=10).mean()

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
            
        if basic_upper.iloc[i] < final_upper[i-1] or close.iloc[i-1] > final_upper[i-1]:
            final_upper[i] = basic_upper.iloc[i]
        else:
            final_upper[i] = final_upper[i-1]
            
        if basic_lower.iloc[i] > final_lower[i-1] or close.iloc[i-1] < final_lower[i-1]:
            final_lower[i] = basic_lower.iloc[i]
        else:
            final_lower[i] = final_lower[i-1]
            
        if close.iloc[i] <= final_upper[i]:
            supertrend[i] = False
        elif close.iloc[i] >= final_lower[i]:
            supertrend[i] = True
        else:
            supertrend[i] = supertrend[i-1]
            
        st_values[i] = final_lower[i] if supertrend[i] else final_upper[i]

    df['supertrend'] = st_values
    df['supertrend_dir'] = supertrend
    return df

# --- STEP 3: CROSSOVER LOGIC ---

def check_positive_crossover(row, prev_row=None):
    if row['macd_line'] <= row['macd_signal']: return False
    if row['macd_line'] <= 0: return False
    if row['histogram'] <= 0.10 * abs(row['macd_line']): return False
    if prev_row is not None and row['histogram'] <= prev_row['histogram']: return False
    if not row['supertrend_dir']: return False
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

# --- MAIN DUAL-SCHEDULE LOOP ---

def main():
    print(f"[{datetime.now(timezone.utc).astimezone(timezone(IST_OFFSET)).strftime('%Y-%m-%d %H:%M:%S IST')}] Starting Solana Quant Bot...")
    
    candidate_pools = []
    filtered_pools = []
    last_pool_fetch_time = 0
    POOL_FETCH_INTERVAL = 900  # 15 Minutes
    INDICATOR_CHECK_INTERVAL = 300  # 5 Minutes

    while True:
        current_time = time.time()
        
        # 1. Fetch & Filter Pool Candidates every 15 Minutes
        if current_time - last_pool_fetch_time >= POOL_FETCH_INTERVAL or not candidate_pools:
            print("\n[*] Running 15-Minute Raw Pool Discovery & Filtering Routine...")
            candidate_pools = fetch_candidate_pools()
            filtered_pools = filter_pools(candidate_pools, relax_filters=False)
            if not filtered_pools:
                print("[*] No tokens met strict filters. Bypassing M-Q...")
                filtered_pools = filter_pools(candidate_pools, relax_filters=True)
            last_pool_fetch_time = current_time

        # 2. Check Technical Indicators every 5 Minutes
        print(f"\n[*] [{datetime.now(timezone.utc).astimezone(timezone(IST_OFFSET)).strftime('%H:%M:%S IST')}] Checking 5-Min MACD Crossovers for {len(filtered_pools)} tokens...")
        
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

            # Historical Backtest Loop across Candles
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
                        "DexScreener Address": pool_addr,
                        "Entry (IST)": convert_to_ist(entry_time),
                        "Exit (IST)": convert_to_ist(exit_time),
                        "PnL (%)": round(pnl_pct, 2)
                    })
                    in_trade = False

            # Current Active Signal Check on Latest Closed Candle
            latest_curr = df.iloc[-1]
            latest_prev = df.iloc[-2]
            if check_positive_crossover(latest_curr, latest_prev):
                last_5_df = df.tail(5)
                for _, row in last_5_df.iterrows():
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
                        "RSI": f"{row.get('rsi', 0):.1f}"
                    })

        # --- OUTPUT RENDERING ---
        print("\n" + "="*140)
        print("TABLE 1: HISTORICAL MACD CROSSOVER TRADES & POOL ADDRESSES")
        print("="*140)
        if historical_trades:
            print(pd.DataFrame(historical_trades).to_string(index=False))
        else:
            print("No completed historical crossover trades found.")

        print("\n" + "="*140)
        print("TABLE 2: CURRENT ACTIVE POSITIVE MACD CROSSOVERS - LAST 5 TUPLES (5-MIN MONITOR)")
        print("="*140)
        if all_current_signals_detailed:
            print(pd.DataFrame(all_current_signals_detailed).to_string(index=False))
        else:
            print("No current positive crossover detected on latest 5-min candles.")
        print("="*140 + "\n")

        # Fixed 5-minute loop pause for fast crossover monitoring
        print(f"[*] Indicator evaluation finished. Sleeping 5 minutes before next candle check...")
        time.sleep(INDICATOR_CHECK_INTERVAL)

if __name__ == "__main__":
    main()
