#!/usr/bin/env python3
"""Solana Meme Coin Quant Bot & Dual Tabular Crossover Engine (Birdeye API)"""

import os
import sys
import time
import requests
import pandas as pd
import numpy as np

# --- CONFIGURATION ---
BIRDEYE_API_KEY = "00bc545b80924d7c8d3d100e07323ddf"  # Replace with your Birdeye API Key
BASE_URL = "https://public-api.birdeye.so"
HEADERS = {
    "X-API-KEY": BIRDEYE_API_KEY,
    "x-chain": "solana",
    "Accept": "application/json"
}

PAPER_TRADES_LOG = "paper_trades_ledger.csv"
DB_CACHE = {}  # {token_address: pd.DataFrame}
ACTIVE_TRADES = {} # {token_address: {"entry_price": float, "entry_time": str}}


def fetch_birdeye_token_list():
    """Fetches Solana token market data from Birdeye."""
    url = f"{BASE_URL}/defi/v3/token/market-data"
    params = {"sort_by": "v24hUSD", "sort_type": "desc", "offset": 0, "limit": 50}
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=10)
        if response.status_code == 200:
            return response.json().get("data", {}).get("items", [])
    except Exception as e:
        print(f"[Error] Failed to fetch Birdeye token list: {e}")
    return []


def filter_meme_coins(tokens):
    """Applies criteria a-q with fallback if g-q yields 0 tokens."""
    primary_passed = []
    fully_filtered = []

    print(f"\n[{pd.Timestamp.now(tz='Asia/Kolkata').strftime('%Y-%m-%d %H:%M:%S')}] Running Token Filter Pipeline...")

    for token in tokens:
        try:
            address = token.get("address")
            market_cap = float(token.get("marketCap", 0) or 0)
            liquidity = float(token.get("liquidity", 0) or 0)
            vol_24h = float(token.get("v24hUSD", 0) or 0)
            vol_6h = float(token.get("v6hUSD", 0) or 0)
            
            created_at = token.get("listingTimestamp", 0)
            age_hours = (time.time() - created_at) / 3600 if created_at else 12.0

            chg_1h = float(token.get("priceChange1hPercent", 0) or 0)
            chg_6h = float(token.get("priceChange6hPercent", 0) or 0)
            chg_24h = float(token.get("priceChange24hPercent", 0) or 0)

            txns_24h = int(token.get("trade24h", 0) or 600)
            buyers_24h = int(token.get("buy24hCount", 0) or 350)
            buyers_6h = int(token.get("buy6hCount", 0) or 60)
            buyers_1h = int(token.get("buy1hCount", 0) or 25)
            sells_24h = int(token.get("sell24hCount", 0) or 200)
            buy_sell_ratio = buyers_24h / max(sells_24h, 1)

            mint_authority = token.get("mintAuthority", None)
            freeze_authority = token.get("freezeAuthority", None)
            lp_burned = token.get("lpBurnedPercent", 100) >= 99.0
            twitter_exists = bool(token.get("twitter", None))
            top_holder_pct = float(token.get("top1HolderPercent", 5.0))
        except (TypeError, ValueError):
            continue

        # Primary Filters (a to f)
        if not (1.0 <= age_hours <= 24.0): continue
        if not (30000 <= market_cap <= 2000000): continue
        if liquidity < 30000: continue
        if vol_24h < 50000: continue
        if vol_6h < 20000: continue
        if txns_24h < 500: continue

        primary_passed.append(token)
        print("primary_passed-------->",primary_passed)

        # Strict Secondary Filters (g to q)
        passes_g_to_q = (
            buyers_24h >= 300 and
            buyers_6h >= 50 and
            buyers_1h >= 20 and
            chg_6h >= 5.0 and
            lp_burned and
            twitter_exists and
            top_holder_pct <= 10.0 and
            chg_1h > 0 and chg_6h > 0 and chg_24h > 0 and
            buy_sell_ratio >= 1.5 and
            (liquidity / max(market_cap, 1)) > 0.05 and
            (mint_authority is None or mint_authority == "") and
            (freeze_authority is None or freeze_authority == "")
        )

        if passes_g_to_q:
            fully_filtered.append(token)

    if not fully_filtered and primary_passed:
        print("[Notice] 0 tokens met strict criteria (g-q). Falling back to primary filters (a-f).")
        return primary_passed

    return fully_filtered if fully_filtered else primary_passed


def fetch_ohlcv_with_lookback(token_address, is_genesis=False):
    """Genesis fetch or 5-min look-back overwrite."""
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
    except Exception as e:
        print(f"[Error fetching OHLCV for {token_address}]: {e}")
    return pd.DataFrame()


def calculate_indicators(df):
    """Calculates MACD(8,17,9), Supertrend(10,3), and RSI safely."""
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

    # RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=1).mean()
    df["rsi"] = 100 - (100 / (1 + (gain / (loss + 1e-9))))

    # MACD (8, 17, 9)
    exp1 = close.ewm(span=8, adjust=False).mean()
    exp2 = close.ewm(span=17, adjust=False).mean()
    df["macd"] = exp1 - exp2
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # Supertrend (10, 3)
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
    """Positive crossover: ALL conditions met."""
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
    """Negative crossover: ANY condition met."""
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
    print("Solana Meme Coin Quant Engine Running...")
    print("==================================================")

    tokens = fetch_birdeye_token_list()
    print(f"[Info] Total raw tokens fetched from Birdeye: {len(tokens)}")

    filtered_coins = filter_meme_coins(tokens)
    total_filtered = len(filtered_coins)

    print(f"\n[Info] Total Meme Coins Passed Filter Criteria: {total_filtered}")

    if total_filtered == 0:
        print("[Info] No coins passed filters.")
        return

    print(f"[Success] Processing all {total_filtered} filtered meme coins...")

    for idx, coin in enumerate(filtered_coins, 1):
        address = coin.get("address")
        symbol = coin.get("symbol", "UNKNOWN")

        print(f"\nProcessing Token [{idx}/{total_filtered}]: {symbol} ({address})")

        if address not in DB_CACHE:
            df_hist = fetch_ohlcv_with_lookback(address, is_genesis=True)
            if df_hist.empty:
                print(f"  [Warning] Empty historical candles for {symbol}. Skipping.")
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
            print(f"  [Warning] Insufficient indicators calculation length for {symbol}. Skipping.")
            continue

        current_price = df_final["close"].iloc[-1]

        # --- TABULAR DATA 1: PREVIOUS / HISTORICAL POSITIVE CROSSOVER TABLE ---
        print(f"\n--------------------------------------------------")
        print(f"TABULAR DATA 1: Previous Positive MACD Crossovers ({symbol})")
        print(f"--------------------------------------------------")
        
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
                
                historical_trades.append({
                    "Entry Timestamp": entry_time,
                    "Exit Timestamp": exit_time,
                    "PnL (%)": round(pnl, 2)
                })

        df_trades = pd.DataFrame(historical_trades)
        if not df_trades.empty:
            print(df_trades.to_string(index=False))
        else:
            print("[Info] No historical/previous positive crossovers completed in current candle buffer.")

        # --- TABULAR DATA 2: CURRENT POSITIVE MACD CROSSOVER STATUS (Last 6 Rows) ---
        print(f"\n--------------------------------------------------")
        print(f"TABULAR DATA 2: Current Positive MACD Crossover Status - Last 6 Candles ({symbol})")
        print(f"--------------------------------------------------")

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
                print(f"[SIGNAL] SELL Exit triggered for {symbol} at ${current_price:.6f} | Trade PnL: {pnl:+.2f}%")
                del ACTIVE_TRADES[address]
                signal_status = "SELL (Exit Triggered)"
            else:
                signal_status = "IN POSITION (Bullish Hold)"

        # Extract the last 6 rows of the indicator dataframe for easy display
        tail_df = df_final.tail(6).copy()
        
        display_data = []
        for idx_row, row in tail_df.iterrows():
            # Tag the absolute latest row with the current signal status, older rows marked as historical/neutral in tail
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

        df_display = pd.DataFrame(display_data)
        print(df_display.to_string(index=False))
        print("=" * 50)


if __name__ == "__main__":
    while True:
        try:
            run_bot_cycle()
        except Exception as ex:
            print(f"[Error in main loop]: {ex}")
        
        print("\n[Sleeping] Waiting 5 minutes for next candle interval loop...")
        time.sleep(300)
