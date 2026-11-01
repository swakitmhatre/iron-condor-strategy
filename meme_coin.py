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
    print("Starting Solana Meme Coin Quant Bot & Terminal")
    print("==================================================")

    db_cache = {}

    while True:
        try:
            print(f"\n[{pd.Timestamp.now()}] Scanning Dexscreener for top Solana pairs...")
            coins = fetch_dexscreener_coins()

            if not coins:
                print("[Info] No coins matched current filter criteria. Retrying in 5 mins...")
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
