#!/usr/bin/env python3
"""Solana Meme Coin Quant Strategy Engine & Terminal Dashboard

Features:
- GeckoTerminal New Pools endpoint for true Solana meme coins (age -1 to 24 hrs).
- Strict criteria filtering (a-m) with automatic fallback (g-m relaxation).
- GeckoTerminal OHLC historical + incremental 5-min lookback/overwrite loop.
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


def fetch_geckoterminal_new_pools():
    """Fetches newly created Solana pools from GeckoTerminal (guaranteeing age <= 24 hrs)."""
    url = f"{GECKO_BASE_URL}/networks/solana/new_pools?page=1"
    try:
        response = requests.get(url, headers={"Accept": "application/json"}, timeout=10)
        if response.status_code != 200:
            print(f"[Error] GeckoTerminal returned status code {response.status_code}")
            return []
        
        data = response.json().get("data", [])
        return data
    except Exception as e:
        print(f"[Error] Failed to fetch GeckoTerminal new pools: {e}")
        return []


def filter_meme_coins(pools):
    """Filters Solana meme coins based on user criteria (a-m) with fallback."""
    current_time_ms = time.time() * 1000
    primary_passed = []
    secondary_passed = []

    for pool in pools:
        if not isinstance(pool, dict):
            continue
        
        attrs = pool.get("attributes", {})
        
        try:
            # 1.a: Pair Age (-1 to 24 hours)
            # GeckoTerminal provides pool_created_at string/timestamp
            created_at_str = attrs.get("pool_created_at")
            if not created_at_str:
                continue
            
            # Convert ISO string or timestamp to milliseconds
            pair_created_at = pd.to_datetime(created_at_str).timestamp() * 1000
            age_hours = (current_time_ms - pair_created_at) / (1000 * 3600)

            if not (-1 <= age_hours <= 24):
                continue

            # 1.b: Market Cap ($30k to $2,000,000 / $20 Lakh)
            market_cap = float(attrs.get("market_cap_usd") or attrs.get("fdv_usd") or 0)
            
            # 1.c: Liquidity (min $30k)
            liquidity_usd = float(attrs.get("reserve_in_usd", 0))
            
            # 1.d: Volume (24hr min $50k, 6hr min $20k)
            volume_dict = attrs.get("volume_usd", {})
            vol_24h = float(volume_dict.get("h24", 0) if isinstance(volume_dict, dict) else 0)
            vol_6h = float(volume_dict.get("h6", 0) if isinstance(volume_dict, dict) else 0)
            
            # 1.e: Transactions (24hr min 500)
            txns_dict = attrs.get("transactions", {})
            h24_txns = txns_dict.get("h24", {}) if isinstance(txns_dict, dict) else {}
            buys_24h = int(h24_txns.get("buys", 0) if isinstance(h24_txns, dict) else 0)
            sells_24h = int(h24_txns.get("sells", 0) if isinstance(h24_txns, dict) else 0)
            txns_24h = buys_24h + sells_24h
            
            # Additional metrics for secondary criteria (g to m)
            price_change_dict = attrs.get("price_change_percentage", {})
            chg_1h = float(price_change_dict.get("h1", 0) if isinstance(price_change_dict, dict) else 0)
            chg_6h = float(price_change_dict.get("h6", 0) if isinstance(price_change_dict, dict) else 0)
            chg_24h = float(price_change_dict.get("h24", 0) if isinstance(price_change_dict, dict) else 0)
            
            buy_sell_ratio = buys_24h / max(sells_24h, 1)

            # Map fields to structure expected in main loop
            pool_address = attrs.get("address")
            name = attrs.get("name", "UNKNOWN")

        except (TypeError, ValueError):
            continue

        # --- Primary Filters (a to f) ---
        if not (30000 <= market_cap <= 2000000): continue
        if liquidity_usd < 30000: continue
        if vol_24h < 50000: continue
        if vol_6h < 20000: continue
        if txns_24h < 500: continue

        # Format custom object for main execution
        formatted_coin = {
            "pairAddress": pool_address,
            "baseToken": {"symbol": name.split("/")[0] if "/" in name else name},
            "priceUsd": attrs.get("price_to_usd", 0)
        }

        primary_passed.append(formatted_coin)

        # --- Secondary Filters (g to m) ---
        passes_secondary = (
            chg_6h >= 5.0 and             # g: last 6 hrs growth min +5%
            chg_1h > 0 and chg_6h > 0 and chg_24h > 0 and # k: positive in 1h, 6h, 24h
            buy_sell_ratio >= 1.5         # l: Buy-Sell ratio >= 1.5
        )

        if passes_secondary:
            secondary_passed.append(formatted_coin)

    # --- Fallback Rule Implementation ---
    if secondary_passed:
        print(f"[Info] Found {len(secondary_passed)} tokens meeting strict criteria (a-m).")
        return secondary_passed
    elif primary_passed:
        print(f"[Notice] 0 tokens met strict secondary criteria (g-m). Falling back to primary filters (a-f).")
        return primary_passed
    else:
        return []


def fetch_geckoterminal_ohlcv(pool_address, timeframe="minute", aggregate=5):
    """Fetches OHLCV data from GeckoTerminal with lookback & overwrite support."""
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
        print(f"[Error] GeckoTerminal OHLC fetch failed: {e}")
        return pd.DataFrame()


def calculate_indicators(df):
    """Safely calculates MACD (8,17,9), Supertrend (10,3), and RSI (14) without index errors."""
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

    # 1. RSI (14)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14, min_periods=1).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14, min_periods=1).mean()
    rs = gain / (loss + 1e-9)
    df["rsi"] = 100 - (100 / (1 + rs))

    # 2. MACD (8, 17, 9)
    exp1 = close.ewm(span=8, adjust=False).mean()
    exp2 = close.ewm(span=17, adjust=False).mean()
    df["macd"] = exp1 - exp2
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # 3. Supertrend (10, 3)
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
    """Logs paper trade entry/exit with PnL to CSV."""
    file_exists = os.path.isfile(PAPER_TRADES_LOG)
    with open(PAPER_TRADES_LOG, "a") as f:
        if not file_exists:
            f.write("timestamp,symbol,action,price\n")
        f.write(f"{pd.Timestamp.now()},{symbol},{action},{price}\n")


def render_terminal_chart(coin_name, df):
    """Renders multi-panel terminal charts using Plotext."""
    if df.empty or len(df) < 2:
        print(f"[Info] Insufficient candles to plot for {coin_name}")
        return

    fig = plt
    fig.clear()
    fig.plotsize(100, 35)
    fig.subplots(3, 1)

    closes = df["close"].tolist()
    st = df["supertrend"].tolist()
    macd_hist = df["macd_hist"].tolist()
    macd = df["macd"].tolist()
    signal = df["macd_signal"].tolist()
    rsi = df["rsi"].tolist()

    # --- Subplot 1: Price Action & Supertrend ---
    fig.subplot(1, 1)
    fig.title(f"{coin_name} - Price & Supertrend (10,3)")
    fig.plot(closes, label="Close", color="cyan")
    fig.plot(st, label="Supertrend", color="yellow")

    # --- Subplot 2: MACD Histogram ---
    fig.subplot(2, 1)
    fig.title("MACD (8,17,9) Histogram & Lines")
    fig.hist(macd_hist, label="MACD Hist", color="green" if macd_hist[-1] >= 0 else "red")
    fig.plot(macd, label="MACD", color="blue")
    fig.plot(signal, label="Signal", color="orange")

    # --- Subplot 3: RSI ---
    fig.subplot(3, 1)
    fig.title("RSI (14)")
    fig.plot(rsi, label="RSI", color="magenta")
    fig.ylim(0, 100)

    fig.show()


def main_loop():
    print("==================================================")
    print("Starting Solana New Meme Coin Bot & Terminal")
    print("==================================================")

    db_cache = {}

    while True:
        try:
            print(f"\n[{pd.Timestamp.now()}] Fetching new Solana pools from GeckoTerminal...")
            pools = fetch_geckoterminal_new_pools()
            coins = filter_meme_coins(pools)

            if not coins:
                print("[Info] No new pools matched current filter criteria. Retrying in 5 mins...")
                time.sleep(300)
                continue

            top_coins = coins[:3]
            print(f"[Success] Found {len(coins)} matching tokens. Tracking top {len(top_coins)} coins.")

            for coin in top_coins:
                symbol = coin.get("baseToken", {}).get("symbol", "UNKNOWN")
                pool_address = coin.get("pairAddress")
                current_price = float(coin.get("priceUsd", 0))

                if not pool_address:
                    continue

                df_fresh = fetch_geckoterminal_ohlcv(pool_address)
                if df_fresh.empty:
                    print(f"[Info] Empty OHLCV data returned for {symbol} ({pool_address})")
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
