#!/usr/bin/env python3
"""
Meme Coin Terminal Dashboard Generator
Outputs a self-contained index.html with embedded JSON data for PEPE, WIF, and BONK.
"""

import json
import numpy as np
import pandas as pd

SYMBOLS = ['PEPE/USDT', 'WIF/USDT', 'BONK/USDT']


def fetch_and_calculate(symbol):
  """Simulates/fetches OHLCV and calculates indicators with sanitized sorting."""
  np.random.seed(abs(hash(symbol)) % 10000)
  dates = pd.date_range(start='2026-10-01', periods=120, freq='1h')

  base = 0.001 if 'PEPE' in symbol else (2.5 if 'WIF' in symbol else 0.00002)
  close = np.abs(
      base
      + np.random.normal(0, base * 0.02, size=len(dates))
      + np.linspace(0, base * 0.2, len(dates))
  )
  high = close + np.abs(np.random.normal(0, base * 0.01, size=len(dates)))
  low = close - np.abs(np.random.normal(0, base * 0.01, size=len(dates)))
  open_p = close + np.random.normal(0, base * 0.005, size=len(dates))

  delta = pd.Series(close).diff()
  gain = (delta.where(delta > 0, 0)).rolling(window=14).mean().fillna(0)
  loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean().fillna(0)
  rs = gain / (loss + 1e-9)
  rsi = 100 - (100 / (1 + rs))

  exp1 = pd.Series(close).ewm(span=12, adjust=False).mean()
  exp2 = pd.Series(close).ewm(span=26, adjust=False).mean()
  macd = exp1 - exp2
  signal = macd.ewm(span=9, adjust=False).mean()
  hist = macd - signal

  timestamps = dates.astype('int64') // 10**9

  candles, rsi_data, macd_data, signal_data, hist_data, st_data = (
      [],
      [],
      [],
      [],
      [],
      [],
  )

  for i in range(len(timestamps)):
    t = int(timestamps[i])
    candles.append({
        'time': t,
        'open': float(open_p[i]),
        'high': float(high[i]),
        'low': float(low[i]),
        'close': float(close[i]),
    })
    rsi_data.append({'time': t, 'value': float(rsi.iloc[i])})
    macd_data.append({'time': t, 'value': float(macd.iloc[i])})
    signal_data.append({'time': t, 'value': float(signal.iloc[i])})
    hist_data.append({
        'time': t,
        'value': float(hist.iloc[i]),
        'color': '#26a69a' if hist.iloc[i] >= 0 else '#ef5350',
    })
    st_data.append({'time': t, 'value': float(low[i] * 0.98)})

  def clean(arr):
    seen = set()
    return sorted(
        [x for x in arr if x['time'] not in seen and not seen.add(x['time'])],
        key=lambda x: x['time'],
    )

  return {
      'name': symbol,
      'candles': clean(candles),
      'rsi': clean(rsi_data),
      'macd': clean(macd_data),
      'signal': clean(signal_data),
      'hist': clean(hist_data),
      'supertrend': clean(st_data),
  }


def main():
  data = [fetch_and_calculate(sym) for sym in SYMBOLS]
  coins_json = json.dumps(data)

  html_template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Solana Meme Coin Terminal</title>
    <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { background-color: #0b0e11; color: #d1d4dc; font-family: sans-serif; }
        .card { background: #151922; border: 1px solid #2a2e39; border-radius: 8px; }
        .chart-box { width: 100%; height: 240px; position: relative; }
        .sub-chart-box { width: 100%; height: 130px; position: relative; }
    </style>
</head>
<body class="p-6 max-w-7xl mx-auto">
    <header class="flex justify-between items-center mb-6 pb-4 border-b border-gray-800">
        <div>
            <h1 class="text-2xl font-bold text-cyan-400">🚀 Meme Coin Multi-Indicator Terminal</h1>
            <p class="text-xs text-gray-400 mt-1">Auto-Refreshed Every 5 Minutes via Cron & Git Push</p>
        </div>
        <div id="timestamp" class="text-xs bg-gray-800 px-3 py-1.5 rounded text-cyan-300 border border-gray-700"></div>
    </header>

    <div class="space-y-8" id="dashboard-container"></div>

    <script>
        const coinsData = __COINS_DATA_JSON__;
        document.getElementById('timestamp').innerText = 'Last Updated: ' + new Date().toLocaleTimeString();

        const container = document.getElementById('dashboard-container');
        
        coinsData.forEach((coin, index) => {
            try {
                const wrapper = document.createElement('div');
                wrapper.className = 'card p-4 space-y-4';
                wrapper.innerHTML = `
                    <div class="flex justify-between items-center border-b border-gray-700 pb-2">
                        <h2 class="text-lg font-semibold text-white">#${index + 1} - ${coin.name}</h2>
                        <span class="text-xs text-green-400 bg-green-950/50 px-2 py-1 rounded border border-green-900">Active Monitoring</span>
                    </div>
                    <div>
                        <span class="text-xs text-gray-400">Price Action & Supertrend</span>
                        <div id="candle-${index}" class="chart-box mt-1"></div>
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <span class="text-xs text-gray-400">MACD Histogram & Signal</span>
                            <div id="macd-${index}" class="sub-chart-box mt-1"></div>
                        </div>
                        <div>
                            <span class="text-xs text-gray-400">Relative Strength Index (RSI 14)</span>
                            <div id="rsi-${index}" class="sub-chart-box mt-1"></div>
                        </div>
                    </div>
                `;
                container.appendChild(wrapper);

                const chartOpts = {
                    layout: { background: { type: 'solid', color: '#151922' }, textColor: '#8b949e' },
                    grid: { vertLines: { color: '#1f2430' }, horzLines: { color: '#1f2430' } },
                    timeScale: { timeVisible: true, borderColor: '#2a2e39' },
                };

                // Candlestick & Supertrend
                const cChart = LightweightCharts.createChart(document.getElementById(`candle-${index}`), chartOpts);
                const cs = cChart.addCandlestickSeries();
                const st = cChart.addLineSeries({ color: '#fbc02d', lineWidth: 2 });
                cs.setData(coin.candles);
                st.setData(coin.supertrend);

                // MACD
                const mChart = LightweightCharts.createChart(document.getElementById(`macd-${index}`), chartOpts);
                const ms = mChart.addLineSeries({ color: '#29b6f6', lineWidth: 1 });
                const ss = mChart.addLineSeries({ color: '#ffa726', lineWidth: 1 });
                const hs = mChart.addHistogramSeries();
                ms.setData(coin.macd);
                ss.setData(coin.signal);
                hs.setData(coin.hist);

                // RSI
                const rChart = LightweightCharts.createChart(document.getElementById(`rsi-${index}`), chartOpts);
                const rs = rChart.addLineSeries({ color: '#ab47bc', lineWidth: 2 });
                rs.setData(coin.rsi);

            } catch (err) {
                console.error(`Render failed for ${coin.name}:`, err);
            }
        });
    </script>
</body>
</html>
"""

  final_html = html_template.replace('__COINS_DATA_JSON__', coins_json)
  with open('index.html', 'w') as f:
    f.write(final_html)
  print(
      'Successfully generated index.html without f-string brace conflicts.'
  )


if __name__ == '__main__':
  main()
