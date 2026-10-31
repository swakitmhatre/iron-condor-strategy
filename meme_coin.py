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

CHECK_INTERVAL_SECONDS = 300  # 5 minutes
PORT = 8000

# ==========================================
# 1. TECHNICAL INDICATORS ENGINE
# ==========================================
def calculate_indicators(df):
    if len(df) < 14:
        return df

    df = df.copy()

    # MACD (8, 17, 9)
    ema_fast = df['close'].ewm(span=8, adjust=False).mean()
    ema_slow = df['close'].ewm(span=17, adjust=False).mean()
    df['MACD'] = ema_fast - ema_slow
    df['MACD_signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
    df['MACD_hist'] = df['MACD'] - df['MACD_signal']

    # RSI (14)
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    df['RSI'] = 100 - (100 / (1 + rs))
    df['RSI'] = df['RSI'].fillna(50.0)

    # Supertrend (10, 3)
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
# 2. PLOTLY CHART GENERATOR ENGINE
# ==========================================
def generate_interactive_chart(symbol, df, filename="chart.html"):
    fig = make_subplots(
        rows=3, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        subplot_titles=(f"{symbol} 5m Price & Supertrend", "MACD (Line vs Signal vs Histogram)", "RSI (14) Oscillator"),
        row_heights=[0.6, 0.2, 0.2]
    )

    # Main Panel: Candlesticks
    fig.add_trace(go.Candlestick(
        x=df['timestamp'],
        open=df['open'], high=df['high'], low=df['low'], close=df['close'],
        name='Candles',
        increasing_line_color='#06d6a0', decreasing_line_color='#ef476f'
    ), row=1, col=1)

    # Main Panel: Supertrend Line Overlay
    fig.add_trace(go.Scatter(
        x=df['timestamp'], y=df['SUPERTREND'],
        mode='lines', line=dict(color='#ffd166', width=1.5),
        name='Supertrend'
    ), row=1, col=1)

    # Subpanel 1: MACD Line, Signal Line, and Color-Coded Histogram
    colors = ['#06d6a0' if val >= 0 else '#ef476f' for val in df['MACD_hist']]
    fig.add_trace(go.Bar(
        x=df['timestamp'], y=df['MACD_hist'],
        marker_color=colors, name='MACD Hist'
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=df['timestamp'], y=df['MACD'],
        mode='lines', line=dict(color='#118ab2', width=1.5),
        name='MACD Line'
    ), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=df['timestamp'], y=df['MACD_signal'],
        mode='lines', line=dict(color='#ff9f1c', width=1.5),
        name='Signal Line'
    ), row=2, col=1)

    # Subpanel 2: RSI Curve & Thresholds (70 Overbought / 30 Oversold)
    fig.add_trace(go.Scatter(
        x=df['timestamp'], y=df['RSI'],
        mode='lines', line=dict(color='#9d4edd', width=2),
        name='RSI (14)'
    ), row=3, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="#ef476f", row=3, col=1)
    fig.add_hline(y=30, line_dash="dash", line_color="#06d6a0", row=3, col=1)

    # Dark Theme Layout
    fig.update_layout(
        template="plotly_dark",
        title=f"TradingView Console Monitor — {symbol}",
        xaxis_rangeslider_visible=False,
        height=850,
        margin=dict(l=50, r=30, t=60, b=40)
    )

    fig.write_html(filename)
    print(f"[UPDATED] Visual chart rendered to {filename}")


# ==========================================
# 3. BACKGROUND WEB SERVER
# ==========================================
def start_web_server():
    Handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", PORT), Handler) as httpd:
        print(f"[SERVER] Live Web Viewer running on http://13.201.230.37:{PORT}/chart.html")
        httpd.serve_forever()


# ==========================================
# 4. DATA FETCHERS & MAIN LOOP
# ==========================================
def fetch_and_filter_solana_coins():
    keywords = ["PEPE", "WIF", "BONK"]
    all_pairs = []

    for kw in keywords:
        url = f"https://api.dexscreener.com/latest/dex/search?q={kw}"
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                for p in res.json().get('pairs', []):
                    if p.get('chainId') == 'solana':
                        base_symbol = p.get('baseToken', {}).get('symbol', '').upper()
                        if base_symbol not in ['SOL', 'WSOL', 'USDC', 'USDT']:
                            all_pairs.append({
                                'pairAddress': p['pairAddress'],
                                'symbol': base_symbol
                            })
        except Exception:
            continue

    unique_coins = {}
    for c in all_pairs:
        if c['pairAddress'] not in unique_coins:
            unique_coins[c['pairAddress']] = c
        if len(unique_coins) >= 1:
            break
    return list(unique_coins.values())

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

def main():
    # Start web server thread
    server_thread = threading.Thread(target=start_web_server, daemon=True)
    server_thread.start()

    print("[SYSTEM] Starting Live Chart Monitor...")
    while True:
        top_coins = fetch_and_filter_solana_coins()
        for coin in top_coins:
            df = fetch_geckoterminal_ohlcv(coin['pairAddress'])
            if not df.empty:
                df = calculate_indicators(df)
                generate_interactive_chart(coin['symbol'], df)

        print(f"[SLEEP] Waiting 5 minutes for next candle cycle...\n")
        time.sleep(CHECK_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
