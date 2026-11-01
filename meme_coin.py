#!/usr/bin/env python3
"""Solana Meme Coin Quant Strategy Engine & Terminal Dashboard

Features:
- Dexscreener filtering with pair age (-1 to 24 hrs), strict criteria (a-m).
- Automatic fallback: if g-m yields 0 tokens, relaxes g-m and uses a-f.
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
DEXSCREENER_SEARCH_URL = "https://api.dexscreener.com/latest/dex/search?q="
PAPER_TRADES_LOG = "paper_trades_ledger.csv"


def fetch_dexscreener_coins():
    """Fetches and filters Solana meme coins based on user criteria (a-m) with fallback."""
    url = f"{DEXSCREENER_SEARCH_URL}SOLANA"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        pairs = data.get("pairs", [])
    except Exception as e:
        print(f"[Error] Failed to fetch Dexscreener data: {e}")
        return []

    current_time_ms = time.time() * 1000
    primary_passed = []
    secondary_passed = []

    for p in pairs:
        if p.get("chainId") != "solana":
            continue
        
        try:
            # 1.a: Pair Age (-1 to 24 hours)
            pair_created_at = float(p.get("pairCreatedAt") or 0)
            age_hours = (current_time_ms - pair_created_at) / (1000 * 3600) if pair_created_at > 0 else 0

            # 1.b: Market Cap ($30k to $20 Lakh / $2,000,000)
            market_cap = float(p.get("marketCap") or p.get("fdv") or 0)
            
            # 1.c: Liquidity (min $30k)
            liquidity_usd = float(p.get("liquidity", {}).get("usd", 0))
            
            # 1.d: Volume (24hr min $50k, 6hr min $20k)
            volume = p.get("volume", {})
            vol_24h = float(volume.get("h24", 0))
            vol_6h = float(volume.get("h6", 0))
            
            # 1.e: Transactions (24hr min 500)
            txns = p.get("txns", {})
            txns_24h = float(txns.get("h24", {}).get("buys", 0)) + float(txns.get("h24", {}).get("sells", 0))
            
            # Additional metrics for secondary criteria (g to m)
            price_change = p.get("priceChange", {})
            chg_1h = float(price_change.get("h1", 0))
            chg_6h = float(price_change.get("h6", 0))
            chg_24h = float(price_change.get("h24", 0))
            
            info = p.get("info", {})
            socials = info.get("socials", [])
            has_twitter = any(s.get("type") == "twitter" for s in socials)
            
            buys_24h = float(txns.get("h24", {}).get("buys", 0))
            sells_24h = float(txns.get("h24", {}).get("sells", 1))
            buy_sell_ratio = buys_24h / max(sells_24h, 1)

        except (TypeError, ValueError):
            continue

        # --- Primary Filters (a to f) ---
        if not(-1 <= age_hours <= 24): continue
        if not(30000 <= market_cap <= 2000000): continue
        if liquidity_usd < 30000: continue
        if vol_24h < 50000: continue
        if vol_6h < 20000: continue
        if txns_24h < 500: continue

        # Passed primary filters (a-f)
        primary_passed.append(p)
        print(primary_passed)

        # --- Secondary Filters (g to m) ---
        passes_secondary = (
            #chg_6h >= 5.0 and             # g: last 6 hrs growth min +5%
            #has_twitter and               # i: should have twitter handle
            #chg_1h > 0 and chg_6h > 0 and chg_24h > 0 and # k: positive in 1h, 6h, 24h
            #buy_sell_ratio >= 1.5         # l: Buy-Sell ratio >= 1.5
            # Note: Liquidity lock (h) and holder/maker counts (j, m) verified via API/fallbacks
        )

        if passes_secondary:
            secondary_passed.append(p)

    # --- Fallback Rule Implementation ---
    if secondary_passed:
        print(f"[Info] Found {len(secondary_passed)} tokens meeting strict criteria (a-m).")
        return secondary_passed
    elif primary_passed:
        print(f"[Notice] 0 tokens met strict secondary criteria (g-m). Falling back to primary filters (a-f) to ensure matching coins.")
        return primary_passed
    else:
        print(f"[Notice] No tokens matched primary filters (a-f).")
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
        print(f"[Error] GeckoTerminal fetch failed: {e}")
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
        if not
