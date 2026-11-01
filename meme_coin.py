import os
import time
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone
import zoneinfo

# --- CONFIGURATION & DIRECTORIES ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HTML_OUTPUT_PATH = os.path.join(BASE_DIR, "index.html")
TRADE_LOG_PATH = os.path.join(BASE_DIR, "paper_trades_log.csv")

# AWS defaults to UTC. We define IST for local logging & analysis.
UTC = timezone.utc
IST = zoneinfo.ZoneInfo("Asia/Kolkata")

# Ensure directory exists
os.makedirs(BASE_DIR, exist_ok=True)

class TradingEngine:
    def __init__(self):
        self.active_coins = []
        self.db_candles = {}  # pool_address -> DataFrame of candles
        self.paper_trades = []
        self.load_trade_log()

    def load_trade_log(self):
        if os.path.exists(TRADE_LOG_PATH):
            try:
                df = pd.read_csv(TRADE_LOG_PATH)
                self.paper_trades = df.to_dict('records')
            except Exception:
                self.paper_trades = []

    def save_trade_log(self):
        if self.paper_trades:
            pd.DataFrame(self.paper_trades).to_csv(TRADE_LOG_PATH, index=False)

    def fetch_dexscreener_solana_coins(self):
        """Fetches Solana pairs from Dexscreener and filters them."""
        print(f"\n[{datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')} IST] Scanning Dexscreener for Solana Meme Coins...")
        url = "https://api.dexscreener.com/latest/dex/search?q=SOL"
        try:
            response = requests.get(url, timeout=10)
            data = response.json()
            pairs = data.get('pairs', [])
        except Exception as e:
            print(f"Error connecting to Dexscreener API: {e}")
            return []

        filtered_coins = []
        for p in pairs:
            if p.get('chainId') != 'solana':
                continue
            
            # Extract metrics safely
            try:
                market_cap = float(p.get('marketCap', 0) or p.get('fdv', 0) or 0)
                liquidity = float(p.get('liquidity', {}).get('usd', 0) or 0)
                vol_24h = float(p.get('volume', {}).get('h24', 0) or 0)
                vol_6h = float(p.get('volume', {}).get('h6', 0) or 0)
                
                txns = p.get('txns', {})
                txns_24h = int(txns.get('h24', {}).get('buys', 0) + txns.get('h24', {}).get('sells', 0))
                buys_24h = int(txns.get('h24', {}).get('buys', 0))
                sells_24h = int(txns.get('h24', {}).get('sells', 0))
                
                price_change = p.get('priceChange', {})
                chg_1h = float(price_change.get('h1', 0) or 0)
                chg_6h = float(price_change.get('h6', 0) or 0)
                chg_24h = float(price_change.get('h24', 0) or 0)
                
                # Pair age estimation via pairCreatedAt if available
                created_at = p.get('pairCreatedAt', 0)
                if created_at:
                    age_hours = (time.time() - (created_at / 1000)) / 3600
                else:
                    age_hours = 12  # default assumption if missing

                socials = p.get('info', {}).get('socials', [])
                has_twitter = any(s.get('type') == 'twitter' for s in socials)
                
                buy_sell_ratio = (buys_24h / max(sells_24h, 1))
            except Exception:
                continue

            # Strict Filtering criteria (1a to 1m)
            strict_pass = (
                1 <= age_hours <= 48 and
                30000 <= market_cap <= 2000000 and
                liquidity >= 30000 and
                vol_24h >= 50000 and
                vol_6h >= 20000 and
                txns_24h >= 500 and
                buys_24h >= 300 and
                
               
                
            )
            #chg_1h > 0 and chg_6h > 0 and chg_24h > 0 and
            #buy_sell_ratio >= 1.2

            if strict_pass:
                filtered_coins.append({
                    'name': p.get('baseToken', {}).get('name', 'UNKNOWN'),
                    'symbol': p.get('baseToken', {}).get('symbol', 'MEME'),
                    'address': p.get('baseToken', {}).get('address'),
                    'pool_address': p.get('pairAddress'),
                    'liquidity': liquidity,
                    'volume_24h': vol_24h,
                    'score': vol_24h + liquidity
                })

        # Fallback mechanism: if strict criteria yield no coins, loosen g-m criteria
        if not filtered_coins:
            print("No coins met strict criteria (g to m). Loosening filter parameters...")
            for p in pairs:
                if p.get('chainId') != 'solana':
                    continue
                try:
                    market_cap = float(p.get('marketCap', 0) or p.get('fdv', 0) or 0)
                    liquidity = float(p.get('liquidity', {}).get('usd', 0) or 0)
                    vol_24h = float(p.get('volume', {}).get('h24', 0) or 0)
                    if 30000 <= market_cap <= 2000000 and liquidity >= 30000 and vol_24h >= 20000:
                        filtered_coins.append({
                            'name': p.get('baseToken', {}).get('name', 'UNKNOWN'),
                            'symbol': p.get('baseToken', {}).get('symbol', 'MEME'),
                            'address': p.get('baseToken', {}).get('address'),
                            'pool_address': p.get('pairAddress'),
                            'liquidity': liquidity,
                            'volume_24h': vol_24h,
                            'score': vol_24h + liquidity
                        })
                except Exception:
                    continue

        # Sort by liquidity/volume score and pick top 3
        filtered_coins = sorted(filtered_coins, key=lambda x: x['score'], reverse=True)
        top_3 = filtered_coins[:3]
        print(f"Selected Top Coins for Dashboard: {[c['symbol'] for c in top_3]}")
        return top_3

    def fetch_geckoterminal_ohlcv(self, pool_address, is_genesis=False):
        """Fetches OHLCV data from GeckoTerminal API with smart lookback overwrite."""
        url = f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool_address}/ohlcv/minute?aggregate=5&limit=100"
        try:
            res = requests.get(url, headers={"Accept": "application/json"}, timeout=10)
            data = res.json()
            raw_candles = data.get('data', {}).get('attributes', {}).get('ohlcv_list', [])
            
            # Format: [timestamp, open, high, low, close, volume]
            formatted = []
            for c in reversed(raw_candles):  # Chronological order
                formatted.append({
                    'time': int(c[0]),
                    'open': float(c[1]),
                    'high': float(c[2]),
                    'low': float(c[3]),
                    'close': float(c[4]),
                    'volume': float(c[5])
                })
            
            df = pd.DataFrame(formatted)
            if df.empty:
                return pd.DataFrame(columns=['time', 'open', 'high', 'low', 'close', 'volume'])

            if not is_genesis and pool_address in self.db_candles:
                existing_df = self.db_candles[pool_address]
                # Look-back overwrite: replace last 3 candles to account for late indexer updates
                existing_df = existing_df.iloc[:-3] if len(existing_df) >= 3 else existing_df
                df = pd.concat([existing_df, df]).drop_duplicates(subset=['time']).reset_index(drop=True)

            self.db_candles[pool_address] = df
            return df
        except Exception as e:
            print(f"Error fetching OHLCV for {pool_address}: {e}")
            return self.db_candles.get(pool_address, pd.DataFrame())

    def calculate_indicators(self, df):
        """Safely computes MACD(8,17,9), Supertrend(10,3), and RSI(14) without failing on short arrays."""
        if len(df) < 20:
            # Fallback dummy values if candlestick count is too low
            df['macd'] = 0.0
            df['signal'] = 0.0
            df['hist'] = 0.0
            df['supertrend'] = df['close'] * 0.95
            df['rsi'] = 50.0
            return df

        close = df['close']
        high = df['high']
        low = df['low']

        # MACD(8, 17, 9)
        exp1 = close.ewm(span=8, adjust=False).mean()
        exp2 = close.ewm(span=17, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['hist'] = df['macd'] - df['signal']

        # RSI(14)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-9)
        df['rsi'] = 100 - (100 / (1 + rs))
        df['rsi'] = df['rsi'].fillna(50)

        # Supertrend(10, 3)
        period = 10
        multiplier = 3
        hl2 = (high + low) / 2
        tr = np.maximum(high - low, np.maximum(abs(high - close.shift()), abs(low - close.shift())))
        atr = tr.rolling(window=period).mean()

        upper_band = hl2 + (multiplier * atr)
        lower_band = hl2 - (multiplier * atr)

        supertrend = [True] * len(df)
        st_values = [0.0] * len(df)

        for i in range(period, len(df)):
            if close.iloc[i] > upper_band.iloc[i-1]:
                supertrend[i] = True
            elif close.iloc[i] < lower_band.iloc[i-1]:
                supertrend[i] = False
            else:
                supertrend[i] = supertrend[i-1]
                if supertrend[i] and lower_band.iloc[i] < lower_band.iloc[i-1]:
                    lower_band.iloc[i] = lower_band.iloc[i-1]
                if not supertrend[i] and upper_band.iloc[i] > upper_band.iloc[i-1]:
                    upper_band.iloc[i] = upper_band.iloc[i-1]

            st_values[i] = lower_band.iloc[i] if supertrend[i] else upper_band.iloc[i]

        df['supertrend'] = st_values
        df['supertrend'] = df['supertrend'].fillna(close * 0.95)
        return df

    def generate_html_dashboard(self, top_coins):
        """Generates a single HTML file containing charts and indicators for top 3 meme coins."""
        charts_js_data = []

        for idx, coin in enumerate(top_coins):
            pool = coin['pool_address']
            df = self.db_candles.get(pool, pd.DataFrame())
            if df.empty:
                continue
            df = self.calculate_indicators(df)

            candles_json = df[['time', 'open', 'high', 'low', 'close']].to_dict(orient='records')
            macd_json = df[['time', 'macd']].rename(columns={'macd': 'value'}).to_dict(orient='records')
            signal_json = df[['time', 'signal']].rename(columns={'signal': 'value'}).to_dict(orient='records')
            hist_json = []
            for _, row in df.iterrows():
                hist_json.append({
                    'time': int(row['time']),
                    'value': float(row['hist']),
                    'color': '#26a69a' if row['hist'] >= 0 else '#ef5350'
                })
            st_json = df[['time', 'supertrend']].rename(columns={'supertrend': 'value'}).to_dict(orient='records')
            rsi_json = df[['time', 'rsi']].rename(columns={'rsi': 'value'}).to_dict(orient='records')

            charts_js_data.append({
                'name': f"{coin['name']} ({coin['symbol']})",
                'candles': candles_json,
                'macd': macd_json,
                'signal': signal_json,
                'hist': hist_json,
                'supertrend': st_json,
                'rsi': rsi_json
            })

        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Solana Meme Coin Multi-Indicator Engine</title>
    <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {{ background-color: #0b0e11; color: #d1d4dc; font-family: sans-serif; }}
        .card {{ background: #151922; border: 1px solid #2a2e39; border-radius: 8px; }}
        .chart-box {{ width: 100%; height: 260px; position: relative; }}
        .sub-chart-box {{ width: 100%; height: 150px; position: relative; }}
    </style>
</head>
<body class="p-6">
    <header class="flex justify-between items-center mb-6 pb-4 border-b border-gray-800">
        <div>
            <h1 class="text-2xl font-bold text-cyan-400">🚀 Solana Meme Coin Terminal (Top 3 Filtered)</h1>
            <p class="text-xs text-gray-400 mt-1">Auto-rewritten every 5 minutes | AWS Time: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
        </div>
        <span class="text-xs bg-gray-800 px-3 py-1.5 rounded text-cyan-300 border border-gray-700">Status: Active Engine</span>
    </header>

    <div class="space-y-8" id="dashboard-container"></div>

    <script>
        const coinsData = {charts_js_data};

        const container = document.getElementById('dashboard-container');

        coinsData.forEach((coin, index) => {{
            const wrapper = document.createElement('div');
            wrapper.className = 'card p-4 space-y-4';
            wrapper.innerHTML = `
                <h2 class="text-lg font-semibold text-white border-b border-gray-700 pb-2">#${{index + 1}} - ${{coin.name}}</h2>
                
                <div>
                    <span class="text-xs text-gray-400">Price Action & Supertrend (10,3)</span>
                    <div id="candle-${{index}}" class="chart-box mt-1"></div>
                </div>

                <div>
                    <span class="text-xs text-gray-400">MACD Histogram (8,17,9)</span>
                    <div id="macd-${{index}}" class="sub-chart-box mt-1"></div>
                </div>

                <div>
                    <span class="text-xs text-gray-400">Relative Strength Index (RSI 14)</span>
                    <div id="rsi-${{index}}" class="sub-chart-box mt-1"></div>
                </div>
            `;
            container.appendChild(wrapper);

            const chartOpts = {{
                layout: {{ background: {{ type: 'solid', color: '#151922' }}, textColor: '#8b949e' }},
                grid: {{ vertLines: {{ color: '#1f2430' }}, horzLines: {{ color: '#1f2430' }} }},
                timeScale: {{ timeVisible: true, borderColor: '#2a2e39' }},
            }};

            // 1. Candlestick + Supertrend
            const cChart = LightweightCharts.createChart(document.getElementById(`candle-${{index}}`), chartOpts);
            const candleSeries = cChart.addCandlestickSeries();
            const stSeries = cChart.addLineSeries({{ color: '#fbc02d', lineWidth: 2 }});
            candleSeries.setData(coin.candles);
            stSeries.setData(coin.supertrend);

            // 2. MACD
            const mChart = LightweightCharts.createChart(document.getElementById(`macd-${{index}}`), chartOpts);
            const macdSeries = mChart.addLineSeries({{ color: '#29b6f6', lineWidth: 1 }});
            const signalSeries = mChart.addLineSeries({{ color: '#ffa726', lineWidth: 1 }});
            const histSeries = mChart.addHistogramSeries();
            macdSeries.setData(coin.macd);
            signalSeries.setData(coin.signal);
            histSeries.setData(coin.hist);

            // 3. RSI
            const rChart = LightweightCharts.createChart(document.getElementById(`rsi-${{index}}`), chartOpts);
            const rsiSeries = rChart.addLineSeries({{ color: '#ab47bc', lineWidth: 2 }});
            rsiSeries.setData(coin.rsi);
        }});
    </script>
</body>
</html>
"""
        with open(HTML_OUTPUT_PATH, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"[{datetime.now(IST).strftime('%H:%M:%S')} IST] HTML dashboard successfully rewritten to {HTML_OUTPUT_PATH}")

    def run_loop(self):
        print("=== Starting Solana Meme Coin Engine Loop ===")
        while True:
            try:
                top_3 = self.fetch_dexscreener_solana_coins()
                if top_3:
                    for coin in top_3:
                        pool = coin['pool_address']
                        # Perform genesis fetch or 5-min incremental append with lookback overwrite
                        is_genesis = pool not in self.db_candles
                        self.fetch_geckoterminal_ohlcv(pool, is_genesis=is_genesis)
                    
                    self.generate_html_dashboard(top_3)
                else:
                    print("No matching coins found in this cycle. Retrying in 5 minutes...")
            except Exception as e:
                print(f"Error in main execution loop: {e}")

            print("Sleeping for 5 minutes...\n")
            time.sleep(300)

if __name__ == '__main__':
    engine = TradingEngine()
    engine.run_loop()
