import os
import time
import requests
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import http.server
import socketserver
import threading

CHECK_INTERVAL_SECONDS = 300  # 5-minute candle cycle
PORT = 8000
TARGET_SYMBOLS = ["PEPE", "WIF", "BONK"]

# ==========================================
# STEP 2: DETERMINISTIC INDICATOR ENGINE
# ==========================================
def calculate_indicators(df):
    if len(df) < 14:
        return df

    df = df.copy()

    # 1. MACD (8, 17, 9) — Precise Exponential Smoothing
    ema_fast = df['close'].ewm(span=8, adjust=False).mean()
    ema_slow = df['close'].ewm(span=17, adjust=False).mean()
    df['MACD'] = ema_fast - ema_slow
    df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_hist'] = df['MACD'] - df['MACD_signal']

    # 2. RSI (14) — Wilder's Smoothing (Exact TradingView Logic)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    df['RSI'] = 100 - (100 / (1 + rs))
    df['RSI'] = df['RSI'].fillna(50.0)

    # 3. Supertrend (10, 3) — Precise Trailing Band Calculation
    high_low = df['high'] - df['low']
    high_cp = (df['high'] - df['close'].shift(1)).abs()
    low_cp = (df['low'] - df['close'].shift(1)).abs()
    tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
    atr = tr.rolling(min(10, len(df))).mean()

    hl2 = (df['high'] + df['low']) / 2
    basic_upper = hl2 + (3 * atr)
    basic_lower = hl2 - (3 * atr)

    supertrend = np.zeros(len(df))
    direction = np.ones(len(df))

    for i in range(1, len(df)):
        if df['close'].iloc[i] > basic_upper.iloc[i-1]:
            direction[i] = 1
        elif df['close'].iloc[i] < basic_lower.iloc[i-1]:
            direction[i] = -1
        else:
            direction[i] = direction[i-1]
        supertrend[i] = basic_lower.iloc[i] if direction[i] == 1 else basic_upper.iloc[i]

    df['SUPERTREND'] = supertrend
    df['SUPERTREND_dir'] = direction
    return df


# ==========================================
# MULTI-PANEL CHART DASHBOARD GENERATOR
# ==========================================
def generate_interactive_chart(symbol, df, filename):
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        subplot_titles=(
            f"{symbol} (5m) — Price & Supertrend Overlay", 
            "MACD (Blue: Line | Orange: Signal | Bars: Hist)", 
            "RSI 14 (Purple: Curve | Red/Green: Boundaries)"
        ),
        row_heights=[0.55, 0.22, 0.23]
    )

    # 1. Main Candlesticks + Supertrend Line
    fig.add_trace(go.Candlestick(
        x=df['timestamp'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
        name='Price (OHLC)', increasing_line_color='#06d6a0', decreasing_line_color='#ef476f'
    ), row=1, col=1)

    fig.add_trace(go.Scatter(
        x=df['timestamp'], y=df['SUPERTREND'],
        mode='lines', line=dict(color='#ffd166', width=1.5), name='Supertrend'
    ), row=1, col=1)

    # 2. MACD Histogram + MACD Line vs Signal Line
    colors = ['#06d6a0' if val >= 0 else '#ef476f' for val in df['MACD_hist']]
    fig.add_trace(go.Bar(
        x=df['timestamp'], y=df['MACD_hist'], marker_color=colors, name='MACD Hist'
    ), row=2, col=1)

    fig.add_trace(go.Scatter(
        x=df['timestamp'], y=df['MACD'],
        mode='lines', line=dict(color='#118ab2', width=1.8), name='MACD Line'
    ), row=2, col=1)

    fig.add_trace(go.Scatter(
        x=df['timestamp'], y=df['MACD_signal'],
        mode='lines', line=dict(color='#ff9f1c', width=1.8), name='Signal Line'
    ), row=2, col=1)

    # 3. RSI Curve with Overbought/Oversold Threshold Lines
    fig.add_trace(go.Scatter(
        x=df['timestamp'], y=df['RSI'],
        mode='lines', line=dict(color='#9d4edd', width=2), name='RSI (14)'
    ), row=3, col=1)

    fig.add_hline(y=70, line_dash="dash", line_color="#ef476f", row=3, col=1, annotation_text="Overbought 70")
    fig.add_hline(y=30, line_dash="dash", line_color="#06d6a0", row=3, col=1, annotation_text="Oversold 30")

    # Unified Hover Crosshair Template
    fig.update_layout(
        template="plotly_dark",
        title=f"Precision Execution Dashboard — {symbol}",
        xaxis_rangeslider_visible=False,
        hovermode="x unified",
        height=880,
        margin=dict(l=50, r=30, t=60, b=40)
    )

    fig.write_html(filename)
    print(f"[SUCCESS] Updated {symbol} chart -> {filename}")


# ==========================================
# STEP 1: STEP-FREE DATA PIPELINE
# ==========================================
def fetch_top_solana_coins():
    found_coins = []
    for kw in TARGET_SYMBOLS:
        url = f"https://api.dexscreener.com/latest/dex/search?q={kw}"
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                for p in res.json().get('pairs', []):
                    if p.get('chainId') == 'solana':
                        base_symbol = p.get('baseToken', {}).get('symbol', '').upper()
                        if base_symbol == kw:
                            found_coins.append({
                                'pairAddress': p['pairAddress'],
                                'symbol': base_symbol
                            })
                            break
        except Exception:
            continue
    return found_coins

def fetch_geckoterminal_ohlcv(pool_address):
    url = f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool_address}/ohlcv/minute?aggregate=5"
    headers = {"Accept": "application/json;version=20230302"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            ohlcv_list = res.json().get('data', {}).get('attributes', {}).get('ohlcv_list', [])
            df = pd.DataFrame(ohlcv_list, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s', utc=True)
            return df.sort_values('timestamp').reset_index(drop=True)
    except Exception:
        pass
    return pd.DataFrame()


# ==========================================
# BACKGROUND SERVER & LOOP
# ==========================================
def start_web_server():
    Handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"\n[DASHBOARD HUB READY]")
        print(f"  ► PEPE Chart: http://13.201.230.37:{PORT}/pepe.html")
        print(f"  ► WIF Chart:  http://13.201.230.37:{PORT}/wif.html")
        print(f"  ► BONK Chart: http://13.201.230.37:{PORT}/bonk.html\n")
        httpd.serve_forever()

def main():
    server_thread = threading.Thread(target=start_web_server, daemon=True)
    server_thread.start()

    print("[SYSTEM] Running Solana Indicator & Charting Engine...")
    while True:
        coins = fetch_top_solana_coins()
        for coin in coins:
            symbol = coin['symbol']
            filename = f"{symbol.lower()}.html"
            
            df = fetch_geckoterminal_ohlcv(coin['pairAddress'])
            if not df.empty:
                df = calculate_indicators(df)
                generate_interactive_chart(symbol, df, filename)

        print(f"[SLEEP] Cycles updated. Waiting 5 minutes...\n")
        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
