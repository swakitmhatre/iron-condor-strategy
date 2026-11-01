#!/usr/bin/env python3
"""Solana Meme Coin Quant Strategy Engine & Terminal Dashboard

Features:
- Dexscreener filtering with strict criteria & fallback relaxation (g to m).
- GeckoTerminal OHLC historical + incremental 5-min lookback/overwrite loop.
- Safe technical indicator generation (MACD 8,17,9; Supertrend 10,3; RSI 14).
- Terminal multi-panel plotting via Plotext (Candlestick/Supertrend, MACD Hist, RSI).
- AWS Timezone handling & Paper Trading PnL ledger.
"""

import os
import sys
import time
import requests
import pandas as pd
import numpy as np
import plotext as plt

# ---------------------------------------------------------------------------
# CONFIGURATION & AWS TIMEZONE NOTE
# ---------------------------------------------------------------------------
# AWS servers default to UTC. For crypto trading, UTC is standard and recommended.
# If you need local Indian Standard Time (IST) logs or timestamps explicitly, 
# you can set the environment variable: os.environ['TZ'] = 'Asia/Kolkata'; time.tzset()
# ---------------------------------------------------------------------------

GECKO_BASE_URL = "https://api.geckoterminal.com/api/v2"
DEXSCREENER_SEARCH_URL = "https://api.dexscreener.com/latest/dex/search?q="

PAPER_TRADES_LOG = "paper_trades_ledger.csv"


def fetch_dexscreener_coins():
    """Fetches and filters Solana meme coins based on user criteria."""
    url = f"{DEXSCREENER_SEARCH_URL}SOLANA"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        pairs = data.get("pairs", [])
    except Exception as e:
        print(f"[Error] Failed to fetch Dexscreener data: {e}")
        return []

    filtered_coins = []

    for p in pairs:
        if p.get("chainId") != "solana":
            continue
        
        # Extract metrics safely
        try:
            market_cap = float(p.get("marketCap") or p.get("fdv") or 0)
            liquidity_usd = float(p.get("liquidity", {}).get("usd", 0))
            
            volume = p.get("volume", {})
            vol_24h = float(volume.get("h24", 0))
            vol_6h = float(volume.get("h6", 0))
            
            txns = p.get("txns", {})
            txns_24h = float(txns.get("h24", {}).get("buys", 0)) + float(txns.get("h24", {}).get("sells", 0))
            
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

        # Primary Strict Filters (a to f)
        if not (30000 <= market_cap <= 2000000): continue
        if liquidity_usd < 30000: continue
        if vol_24h < 50000: continue
        if vol_6h < 20000: continue
        if txns_24h < 500: continue

        # Store candidate
        p["_evaluated_strict"] = {
            "chg_6h": chg_6h,
            "has_twitter": has_twitter,
            "chg_1h": chg_1h,
            "chg_24h": chg_24h,
            "buy_sell_ratio": buy_sell_ratio,
        }
        filtered_coins.append(p)

    # Apply secondary filters (g to m). If empty, relax criteria.
    final_list = []
    for coin in filtered_coins:
        e = coin["_evaluated_strict"]
        passes_secondary = (
            e["chg_6h"] >= 5.0 and
            e["has_twitter"] and
            e["chg_1h"] > 0 and e["chg_6h"] > 0 and e["chg_24h"] > 0 and
            e["buy_sell_ratio"] >= 1.5
        )
        if passes_secondary:
            final_list.append(coin)

    if not final_list:
        print("[Notice] No tokens met strict criteria (g-m). Relaxing secondary filters.")
        final_list = filtered_coins

    return final_list


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
    """Safely calculates MACD (8,17,9), Supertrend (10,3), and RSI (14)."""
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
    delta = close
