#!/usr/bin/env python3
"""Solana Meme Coin Quant Strategy Engine & Terminal Dashboard

Features:
- Multi-page GeckoTerminal fetching for robust coin discovery (1-24 hrs old).
- Strict primary filtering with expanded mid-cap allowance.
- OHLCV historical retry logic & empty candle bypass.
- Safe technical indicator generation (MACD 8,17,9; Supertrend 10,3; RSI 14).
- Terminal multi-panel plotting via Plotext.
- Paper Trading PnL ledger.
"""

import os
import sys
import time
import requests
import pandas as pd
import numpy as np
import plotext as plt

GECKO_BASE_URL = "https://api.geckoterminal.com/api/v2"
PAPER_TRADES_LOG = "paper_trades_ledger.csv"


def fetch_geckoterminal_pools():
    """Fetches multiple pages of Solana pools from GeckoTerminal to ensure a robust sample size."""
    all_pools = []
    for page in range(1, 4):
        url = f"{GECKO_BASE_URL}/networks/solana/pools?page={page}"
        try:
            response = requests.get(url, headers={"Accept": "application/json"}, timeout=10)
            if response.status_code == 200:
                data = response.json().get("data", [])
                if data:
                    all_pools.extend(data)
            time.sleep(0.2)
        except Exception as e:
            print(f"[Error] Failed to fetch page {page}: {e}")
            
    print(f"[Info] Fetched a total of {len(all_pools)} pools across multiple pages for filtering.")
    return all_pools


def filter_meme_coins(pools):
    """Filters Solana meme coins with step-by-step detailed debug output."""
    current_time_ms = time.time() * 1000
    primary_passed = []
    secondary_passed = []

    print("\n" + "="*50)
    print(f"--- Starting Filter Pass [{pd.Timestamp.now()}] ---")
    print("="*50)

    for pool in pools:
        if not isinstance(pool, dict):
            continue
        
        attrs = pool.get("attributes", {})
        name = attrs.get("name", "UNKNOWN")
        pool_address = attrs.get("address")
        
        try:
            created_at_str = attrs.get("pool_created_at")
            if not created_at_str:
                continue
            
            pair_created_at = pd.to_datetime(created_at_str, utc=True).timestamp() * 1000
            age_hours = (current_time_ms - pair_created_at) / (1000 * 3600)

            # 1.a: Pair Age Check (1 to 24 hours)
            if not (1.0 <= age_hours <= 24.0):
                continue

            market_cap = float(attrs.get("market_cap_usd") or attrs.get("fdv_usd") or 0)
            liquidity_usd = float(attrs.get("reserve_in_usd", 0))
            
            volume_dict = attrs.get("volume_usd", {})
            vol_24h = float(volume_dict.get("h24", 0) if isinstance(volume_dict, dict) else 0)
            vol_6h = float(volume_dict.get("h6", 0) if isinstance(volume_dict, dict) else 0)
            
            txns_dict = attrs.get("transactions", {})
            h24_txns = txns_dict.get("h24", {}) if isinstance(txns_dict, dict) else {}
            buys_24h = int(h24_txns.get("buys", 0) if isinstance(h24_txns, dict) else 0)
            sells_24h = int(h24_txns.get("sells", 0) if isinstance(h24_txns, dict) else 0)
            txns_24h = buys_24h + sells_24h
            
            price_change_dict = attrs.get("price_change_percentage", {})
            chg_1h = float(price_change_dict.get("h1", 0) if isinstance(price_change_dict, dict) else 0)
            chg_6h = float(price_change_dict.get("h6", 0) if isinstance(price_change_dict, dict) else 0)
            chg_24h = float(price_change_dict.get("h24", 0) if isinstance(price_change_dict, dict) else 0)
            
            buy_sell_ratio = buys_24h / max(sells_24h, 1)

        except (TypeError, ValueError):
            continue

        print(f"[Age OK] {name} | Age: {age_hours:.2f} hrs")

        # --- Step-by-Step Primary Filters with Debug Prints ---
        if not (30000 <= market_cap <= 50000000):
            print(f"  [Rejected MCap] {name} | MCap: ${market_cap:,.2f}")
            continue
        if liquidity_usd < 30000:
            print(f"  [Rejected Liq] {name} | Liq: ${liquidity_usd:,.2f}")
            continue
        if vol_24h < 50000:
            print(f"  [Rejected Vol24] {name} | Vol24: ${vol_24h:,.2f}")
            continue
        if vol_6h < 20000:
            print(f"  [Rejected Vol6] {name} | Vol6: ${vol_6h:,.2f}")
            continue
        if txns_24h < 500:
            print(f"  [Rejected Txns] {name} | Txns: {txns_24h:,}")
            continue

        # If it reaches here, it passed all primary filters successfully!
        print(f"  [PASSED PRIMARY] {name} | MCap: ${market_cap:,.2f} | Liq: ${liquidity_usd:,.2f} | Vol24: ${vol_24h:,.2f}")

        formatted_coin = {
            "pairAddress": pool_address,
            "baseToken": {"symbol": name.split("/")[0] if "/" in name else name},
            "priceUsd": float(attrs.get("price_to_usd", 0))
        }

        primary_passed.append(formatted_coin)

        # --- Secondary Filters (g to m) ---
        passes_secondary = (
            chg_6h >= 5.0 and 
            chg_1h > 0 and chg_6h > 0 and chg_24h > 0 and 
            buy_sell_ratio >= 1.5
        )

        if passes_secondary:
            print(f"  [PASSED SECONDARY] {name} | 6h Chg: {chg_6h}% | B/S Ratio: {buy_sell_ratio:.2f}")
            secondary_passed.append(formatted_coin)

    print("="*50)
    print(f"--- Filter Pass Complete: {len(primary_passed)} primary passed, {len(secondary_passed)} secondary passed ---")
    print("="*50)

    if secondary_passed:
        return secondary_passed
    elif primary_passed:
        return primary_passed
    else:
        return []

def fetch_geckoterminal_ohlcv(pool_address, timeframe="minute", aggregate=5):
    """Fetches OHLCV data from GeckoTerminal."""
    url = f"{GECKO_BASE_URL}/networks/solana/pools/{pool_address}/ohlcv/{timeframe}?aggregate={aggregate}&limit=100"
    try:
        response = requests.get(url, headers={"Accept": "application/json"}, timeout=10)
        if response.status_code != 200:
            return pd.DataFrame()
        
        data = response.json().get("data", {}).get("attributes", {}).get("ohlcv_list", [])
        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
        df[["open", "high", "low", "close", "volume"]] = df[["open", "high", "low", "close", "volume"]].astype(float)
        df = df.sort_values("timestamp").reset_index(drop=True)
        return df
    except Exception as e:
        return pd.DataFrame()


def fetch_geckoterminal_ohlcv_with_retry(pool_address, timeframe="minute", aggregate=5, retries=2):
    """Fetches OHLCV data with retry logic for newly minted pools."""
    for attempt in range(retries):
        df = fetch_geckoterminal_ohlcv(pool_address, timeframe, aggregate)
        if not df.empty and len(df) >= 5:
            return df
        if attempt < retries - 1:
            time.sleep(3)
    return pd.DataFrame()


def calculate_indicators(df):
    """Safely calculates MACD, Supertrend, and RSI."""
    if df.empty or len(df) < 5:
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
    rs = gain / (loss + 1e-9)
    df["rsi"] = 100 - (100 / (1 + rs))

    exp1 = close.ewm(span=8, adjust=False).mean()
    exp2 = close.ewm(span=17, adjust=False).mean()
    df["macd"] = exp1 - exp2
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    period = 10
    multiplier = 3
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
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
        
        if curr_close <= prev_st:
            supertrend[i] = min(basic_upper.iloc[i], prev_st)
        else:
            supertrend[i] = max(basic_lower.iloc[i], prev_st)

    df["supertrend"] = supertrend
    return df


def log_paper_trade(action, symbol, price):
    """Logs paper trade to CSV."""
    file_exists = os.path.isfile(PAPER_TRADES_LOG)
    with open(PAPER_TRADES_LOG, "a") as f:
        if not file_exists:
            f.write("timestamp,symbol,action,price\n")
        f.write(f"{pd.Timestamp.now()},{symbol},{action},{price}\n")


def render_terminal_chart(coin_name, df):
    """Renders clean individual terminal charts."""
    if df.empty or len(df) < 2:
        return

    closes = df["close"].tolist()
    st = df["supertrend"].tolist()
    macd_hist = df["macd_hist"].tolist()
    macd = df["macd"].tolist()
    signal = df["macd_signal"].tolist()
    rsi = df["rsi"].tolist()
    x_indices = list(range(len(closes)))

    print("\n" + "="*50)
    print(f">>> TERMINAL CHARTS FOR: {coin_name} [{pd.Timestamp.now()}]")
    print("="*50)

    # Chart 1: Price & Supertrend
    plt.clf()
    plt.plotsize(90, 14)
    plt.title(f"{coin_name} - Price vs Supertrend (10,3)")
    plt.plot(x_indices, closes, label="Close Price")
    plt.plot(x_indices, st, label="Supertrend")
    plt.show()

    print("-" * 50)

    # Chart 2: MACD Histogram & Lines
    plt.clf()
    plt.plotsize(90, 12)
    plt.title(f"{coin_name} - MACD (8,17,9)")
    plt.bar(x_indices, macd_hist, label="MACD Hist")
    plt.plot(x_indices, macd, label="MACD Line")
    plt.plot(x_indices, signal, label="Signal Line")
    plt.show()

    print("-" * 50)

    # Chart 3: RSI
    plt.clf()
    plt.plotsize(90, 10)
    plt.title(f"{coin_name} - RSI (14)")
    plt.plot(x_indices, rsi, label="RSI")
    plt.ylim(0, 100)
    plt.show()
    print("="*50 + "\n")


def main_loop():
    print("==================================================")
    print("Starting Solana Meme Coin Quant Bot & Terminal")
    print("==================================================")

    db_cache = {}

    while True:
        try:
            print(f"\n[{pd.Timestamp.now()}] Fetching Solana pools from GeckoTerminal...")
            pools = fetch_geckoterminal_pools()
            coins = filter_meme_coins(pools)

            if not coins:
                print("[Info] No pools matched criteria. Retrying in 5 mins...")
                time.sleep(300)
                continue

            top_coins = coins[:3]
            print(f"[Success] Found {len(coins)} matching tokens. Tracking top {len(top_coins)} coins.")

            for coin in top_coins:
                symbol = coin.get("baseToken", {}).get("symbol", "UNKNOWN")
                pool_address = coin.get("pairAddress")

                if not pool_address:
                    continue

                # Fetch OHLCV data with retry & skip check
                df_fresh = fetch_geckoterminal_ohlcv_with_retry(pool_address)
                if df_fresh.empty or len(df_fresh) < 5:
                    print(f"[Warning] Skipping {symbol}: Insufficient or empty OHLCV candles returned.")
                    continue

                if pool_address in db_cache:
                    df_existing = db_cache[pool_address]
                    if len(df_existing) >= 3 and len(df_fresh) >= 3:
                        df_existing = df_existing.iloc[:-3]
                    df_combined = pd.concat([df_existing, df_fresh]).drop_duplicates(subset=["timestamp"]).reset_index(drop=True)
                    db_cache[pool_address] = df_combined
                else:
                    db_cache[pool_address] = df_fresh

                df_final = calculate_indicators(db_cache[pool_address])

                current_price = float(coin.get("priceUsd") or df_final["close"].iloc[-1] or 0)
                if current_price <= 0:
                    print(f"[Warning] Invalid price ($0.0) for {symbol}. Bypassing signal check.")
                    continue

                if len(df_final) > 2:
                    last_rsi = df_final["rsi"].iloc[-1]
                    if last_rsi < 35:
                        log_paper_trade("BUY", symbol, current_price)
                        print(f"[SIGNAL] BUY triggered for {symbol} at price ${current_price} (RSI: {last_rsi:.2f})")
                    elif last_rsi > 70:
                        log_paper_trade("SELL", symbol, current_price)
                        print(f"[SIGNAL] SELL triggered for {symbol} at price ${current_price} (RSI: {last_rsi:.2f})")

                render_terminal_chart(symbol, df_final)

            print("\n[Sleeping] Waiting 5 minutes for the next candle interval append loop...")
            time.sleep(300)

        except KeyboardInterrupt:
            print("\n[Exit] Bot stopped gracefully by user.")
            sys.exit(0)
        except Exception as ex:
            print(f"[Error Encountered] {ex}")
            time.sleep(60)


if __name__ == "__main__":
    main_loop()
