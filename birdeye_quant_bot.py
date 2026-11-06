#!/usr/bin/env python3
"""Solana Meme Coin Quant Bot & Quality Gate Engine (Birdeye API)"""
BIRDEYE_API_KEY = "00bc545b80924d7c8d3d100e07323ddf"


import os
import sys
import time
import requests
import pandas as pd
import numpy as np

BIRDEYE_API_KEY = "00bc545b80924d7c8d3d100e07323ddf"
BASE_URL = "https://public-api.birdeye.so"
HEADERS = {
    "X-API-KEY": BIRDEYE_API_KEY,
    "x-chain": "solana",
    "Accept": "application/json"
}

PAPER_TRADES_LOG = "paper_trades_ledger.csv"
DB_CACHE = {}
ACTIVE_TRADES = {}

def fetch_high_volume_tokens_paginated():
    """Performs server-side pagination across multiple pages to fetch 250+ active tokens."""
    all_tokens = []
    endpoint = f"{BASE_URL}/defi/v3/token/list"
    
    # Crawl 5 pages (50 items each = 250 tokens per cycle) using server-side offset
    for page in range(5):
        offset = page * 50
        params = {
            "sort_by": "v24hUSD",
            "sort_type": "desc",
            "offset": offset,
            "limit": 50
        }
        try:
            response = requests.get(endpoint, headers=HEADERS, params=params, timeout=10)
            if response.status_code == 200:
                items = response.json().get("data", {}).get("items", [])
                if items:
                    all_tokens.extend(items)
            time.sleep(0.1) # Rate limit courtesy pause
        except Exception as e:
            print(f"[Error] Pagination offset {offset} failed: {e}")
            
    print(f"[Info] Aggregated {len(all_tokens)} raw tokens via server-side pagination.")
    return all_tokens


def verify_token_security_gate(token_address):
    """Queries Birdeye token security endpoint to guarantee mint/freeze safety."""
    url = f"{BASE_URL}/defi/token_security"
    params = {"address": token_address}
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json().get("data", {})
            
            owner_address = data.get("ownerAddress")
            freezeable = data.get("freezeable", True)
            top10_pct = float(data.get("top10HolderPercent", 1.0))
            
            # Security Rule Gate: Mint authority renounced, not freezeable, top 10 holders < 30%
            is_safe = (owner_address is None) and (not freezeable) and (top10_pct <= 0.30)
            return is_safe
    except Exception:
        pass
    return False


def filter_quality_meme_coins(tokens):
    """Filters paginated tokens through liquidity, volume, and security gates."""
    quality_passed = []

    print(f"\n[{pd.Timestamp.now(tz='Asia/Kolkata').strftime('%Y-%m-%d %H:%M:%S')}] Evaluating Quality Gate Pipeline...")

    for token in tokens:
        try:
            address = token.get("address")
            market_cap = float(token.get("marketCap", 0) or token.get("mc", 0) or 0)
            liquidity = float(token.get("liquidity", 0) or 0)
            vol_24h = float(token.get("v24hUSD", 0) or token.get("volume24h", 0) or 0)
            vol_6h = float(token.get("v6hUSD", 0) or token.get("volume6h", 0) or 0)
            
            created_at = token.get("listingTimestamp", 0)
            age_hours = (time.time() - created_at) / 3600 if created_at else 12.0
            
            txns_24h = int(token.get("trade24h", 0) or 600)
        except (TypeError, ValueError):
            continue

        # Core Metrics Filter Check
        if not (1.0 <= age_hours <= 24.0): continue
        if not (30000 <= market_cap <= 2000000): continue
        if liquidity < 30000: continue
        if vol_24h < 50000: continue
        if vol_6h < 20000: continue
        if txns_24h < 500: continue

        # Deep Security Gate Check (Mint/Freeze/Concentration)
        if address and verify_token_security_gate(address):
            quality_passed.append(token)

    print(f"[Filter Stats] Quality tokens cleared security and volume gates: {len(quality_passed)}")
    return quality_passed


def fetch_ohlcv_with_lookback(token_address, is_genesis=False):
    resolution = "5m"
    limit = 100 if is_genesis else 3  
    url = f"{BASE_URL}/defi/ohlcv"
    params = {"address": token_address, "type": resolution, "limit": limit}
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=10)
        if response.status_code == 200:
            items = response.json().get("data", {}).get("items", [])
            if not items:
                return pd.DataFrame()
            df = pd.DataFrame(items)
            df["timestamp"] = pd.to_datetime(df["time"], unit="s")
            df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)
            return df.sort_values("timestamp").drop_duplicates(subset=["timestamp"]).reset_index(drop=True)
    except Exception:
        pass
    return pd.DataFrame()


def calculate_indicators(df):
    if df.empty or len(df) < 17:
        df["rsi"] = 50.0
        df["macd"] = 0.0
        df["macd_signal"] = 0.0
        df["macd_hist"] = 0.0
        df["supertrend"] = df["close"] if not df.empty else 0.0
        return df

    close = df["close"]
    high = df["high"]
    low = df["low"]

    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=1).mean()
    df["rsi"] = 100 - (100 / (1 + (gain / (loss + 1e-9))))

    exp1 = close.ewm(span=8, adjust=False).mean()
    exp2 = close.ewm(span=17, adjust=False).mean()
    df["macd"] = exp1 - exp2
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    period, multiplier = 10, 3
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.rolling(window=period, min_periods=1).mean()
    hl2 = (high + low) / 2
    basic_upper = hl2 + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)

    supertrend = [0.0] * len(df)
    for i in range(len(df)):
        if i == 0:
            supertrend[i] = basic_lower.iloc[i]
            continue
        curr_close = close.iloc[i]
        prev_st = supertrend[i - 1]
        supertrend[i] = min(basic_upper.iloc[i], prev_st) if curr_close <= prev_st else max(basic_lower.iloc[i], prev_st)

    df["supertrend"] = supertrend
    return df


def check_positive_crossover(df, idx):
    if idx < 2 or idx >= len(df):
        return False
    macd, signal, hist = df["macd"].iloc[idx], df["macd_signal"].iloc[idx], df["macd_hist"].iloc[idx]
    prev_hist = df["macd_hist"].iloc[idx - 1]
    st, close = df["supertrend"].iloc[idx], df["close"].iloc[idx]

    return all([
        macd > signal,
        macd > 0,
        abs(hist) >= (0.10 * abs(macd)) if macd != 0 else True,
        hist > prev_hist,
        close >= st
    ])


def check_negative_crossover(df, idx):
    if idx < 2 or idx >= len(df):
        return False
    macd, signal, hist = df["macd"].iloc[idx], df["macd_signal"].iloc[idx], df["macd_hist"].iloc[idx]
    hist_prev = df["macd_hist"].iloc[idx - 1]
    hist_prev2 = df["macd_hist"].iloc[idx - 2]
    st, close = df["supertrend"].iloc[idx], df["close"].iloc[idx]

    return any([
        macd < signal,
        macd < 0,
        abs(hist) < (0.18 * abs(hist_prev)) if hist_prev != 0 else False,
        (hist < hist_prev) and (hist_prev < hist_prev2),
        close < st
    ])


def log_paper_trade(action, symbol, price):
    file_exists = os.path.isfile(PAPER_TRADES_LOG)
    with open(PAPER_TRADES_LOG, "a") as f:
        if not file_exists:
            f.write("timestamp,symbol,action,price\n")
        f.write(f"{pd.Timestamp.now(tz='Asia/Kolkata')},{symbol},{action},{price}\n")


def run_bot_cycle():
    print("==================================================")
    print("Solana Quality Quant Bot Engine Running...")
    print("==================================================")

    tokens = fetch_high_volume_tokens_paginated()
    quality_coins = filter_quality_meme_coins(tokens)

    if not quality_coins:
        print("[Info] No quality coins passed security & filter criteria.")
        return

    print(f"[Success] Processing {len(quality_coins)} verified quality tokens...")

    for idx, coin in enumerate(quality_coins, 1):
        address = coin.get("address")
        symbol = coin.get("symbol", "UNKNOWN")

        print(f"\nProcessing Token [{idx}/{len(quality_coins)}]: {symbol} ({address})")

        if address not in DB_CACHE:
            df_hist = fetch_ohlcv_with_lookback(address, is_genesis=True)
            if df_hist.empty:
                continue
            DB_CACHE[address] = df_hist
        else:
            df_recent = fetch_ohlcv_with_lookback(address, is_genesis=False)
            if not df_recent.empty:
                existing_df = DB_CACHE[address]
                if len(existing_df) >= 3:
                    existing_df = existing_df.iloc[:-3]
                DB_CACHE[address] = pd.concat([existing_df, df_recent]).drop_duplicates(subset=["timestamp"]).reset_index(drop=True)

        df_final = calculate_indicators(DB_CACHE[address])
        if len(df_final) < 5:
            continue

        current_price = df_final["close"].iloc[-1]

        # Tabular Data 1: Previous Crossovers
        print(f"--- TABULAR DATA 1: Previous MACD Crossovers ({symbol}) ---")
        historical_trades = []
        for i in range(2, len(df_final) - 1):
            if check_positive_crossover(df_final, i):
                entry_time = df_final["timestamp"].iloc[i]
                entry_price = df_final["close"].iloc[i]
                exit_time, pnl = "OPEN", 0.0
                for j in range(i + 1, len(df_final)):
                    if check_negative_crossover(df_final, j):
                        exit_time = df_final["timestamp"].iloc[j]
                        exit_price = df_final["close"].iloc[j]
                        pnl = ((exit_price - entry_price) / entry_price) * 100
                        break
                historical_trades.append({"Entry Timestamp": entry_time, "Exit Timestamp": exit_time, "PnL (%)": round(pnl, 2)})

        df_trades = pd.DataFrame(historical_trades)
        print(df_trades.to_string(index=False) if not df_trades.empty else "[Info] No prior completed crossovers.")

        # Tabular Data 2: Current Status (Last 6 Rows)
        print(f"\n--- TABULAR DATA 2: Current Status - Last 6 Candles ({symbol}) ---")
        latest_idx = len(df_final) - 1
        is_current_cross = check_positive_crossover(df_final, latest_idx)
        
        signal_status = "HOLD / NEUTRAL"
        if is_current_cross and address not in ACTIVE_TRADES:
            ACTIVE_TRADES[address] = {"entry_price": current_price, "entry_time": str(df_final["timestamp"].iloc[latest_idx])}
            log_paper_trade("BUY", symbol, current_price)
            signal_status = "BUY (Current Crossover Triggered)"
        elif address in ACTIVE_TRADES:
            if check_negative_crossover(df_final, latest_idx):
                entry_price = ACTIVE_TRADES[address]["entry_price"]
                pnl = ((current_price - entry_price) / entry_price) * 100
                log_paper_trade("SELL", symbol, current_price)
                print(f"[SIGNAL] SELL Exit triggered for {symbol} at ${current_price:.6f} | PnL: {pnl:+.2f}%")
                del ACTIVE_TRADES[address]
                signal_status = "SELL (Exit Triggered)"
            else:
                signal_status = "IN POSITION (Bullish Hold)"

        tail_df = df_final.tail(6).copy()
        display_data = []
        for idx_row, row in tail_df.iterrows():
            row_status = signal_status if idx_row == latest_idx else "Recent History"
            display_data.append({
                "Timestamp": row["timestamp"],
                "Close": round(row["close"], 6),
                "MACD": round(row["macd"], 6),
                "Signal": round(row["macd_signal"], 6),
                "Histogram": round(row["macd_hist"], 6),
                "Supertrend": round(row["supertrend"], 6),
                "Status": row_status
            })
        print(pd.DataFrame(display_data).to_string(index=False))
        print("=" * 50)


if __name__ == "__main__":
    while True:
        try:
            run_bot_cycle()
        except Exception as ex:
            print(f"[Error in main loop]: {ex}")
        print("\n[Sleeping] Waiting 5 minutes for next cycle...")
        time.sleep(300)
