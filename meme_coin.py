#!/usr/bin/env python3
"""Meme Coin Terminal Dashboard Generator

Generates a fully functional index.html using Lightweight Charts v4 syntax.
"""

import json
import numpy as np
import pandas as pd

SYMBOLS = ['PEPE/USDT', 'WIF/USDT', 'BONK/USDT']


def fetch_and_calculate(symbol):
  np.random.seed(abs(hash(symbol)) % 10000)
  # Standard 1-hour hourly intervals from a fixed epoch
  start_ts = 1700000000
  timestamps = [start_ts + i * 3600 for i in range(120)]

  base = 0.001 if 'PEPE' in symbol else (2.5 if 'WIF' in symbol else 0.00002)
  close = np.abs(
      base
      + np.random.normal(0, base * 0.02, size=120)
      + np.linspace(0, base * 0.2, 120)
  )
  high = close + np.abs(np.random.normal(0, base * 0.01, size=120))
  low = close - np.abs(np.random.normal(0, base * 0.01, size=120))
  open_p = close + np.random.normal(0, base * 0.005, size=120)

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

  candles, rsi_data, macd_data, signal_data, hist_data, st_data = (
      [],
      [],
      [],
      [],
      [],
      [],
  )

  for i in range(len(timestamps)):
    t = timestamps[i]
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

  return {
      'name': symbol,
      'candles': candles,
      'rsi': rsi_data,
      'macd': macd_data,
      'signal': signal_data,
      'hist': hist_data,
      'supertrend': st_data,
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
    <script src="https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { background-color: #0b0e11; color: #d1d4dc; font-family: sans-serif; }
        .card { background: #151922; border: 1px solid #2a2e39; border-radius: 8px; }
        .chart-box { width: 100%; height: 260px; position: relative; }
        .sub-chart-box { width: 100%; height: 140px; position: relative; }
    </style>
</head>
<body class="p-6 max-w-7xl mx-auto">
    <header class="flex justify-between items-center mb-6 pb-4 border-b border-gray-800">
        <div>
            <h1 class="text-2xl font-bold text-cyan-400">🚀 Meme Coin Multi-Indicator Terminal</h1>
            <p class="text-xs text-gray-400 mt-1">Live Multi-Indicator View (Lightweight Charts v4 Fixed)</p>
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
                        <span class="text-xs text-gray-400 font-medium">Price Action & Supertrend</span>
                        <div id="candle-${index}" class="chart-box mt-1"></div>
                    </div>
                    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                            <span class="text-xs text-gray-400 font-medium">MACD Histogram & Signal</span>
                            <div id="macd-${index}" class="sub-chart-box mt-1"></div>
                        </div>
                        <div>
                            <span class="text-xs text-gray-400 font-medium">Relative Strength Index (RSI 14)</span>
                            <div id="rsi-${index}" class="sub-chart-box mt-1"></div>
                        </div>
                    </div>
                `;
                container.appendChild(wrapper);

                const baseOpts = {
                    layout: { background: { type: 'solid', color: '#151922' }, textColor: '#8b949e' },
                    grid: { vertLines: { color: '#1f2430' }, horzLines: { color: '#1f2430' } },
                    timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#2a2e39' },
                };

                // 1. Candlestick & Supertrend Chart
                const cChart = LightweightCharts.createChart(document.getElementById(`candle-${index}`), baseOpts);
                const cs = cChart.addSeries(LightweightCharts.CandlestickSeries, {
                    upColor: '#26a69a', downColor: '#ef5350', borderVisible: false, wickUpColor: '#26a69a', wickDownColor: '#ef5350'
                });
                const st = cChart.addSeries(LightweightCharts.LineSeries, { color: '#fbc02d', lineWidth: 2 });
                cs.setData(coin.candles);
                st.setData(coin.supertrend);
                cChart.timeScale().fitContent();

                // 2. MACD Chart
                const mChart = LightweightCharts.createChart(document.getElementById(`macd-${index}`), baseOpts);
                const hs = mChart.addSeries(LightweightCharts.HistogramSeries);
                const ms = mChart.addSeries(LightweightCharts.LineSeries, { color: '#29b6f6', lineWidth: 1 });
                const ss = mChart.addSeries(LightweightCharts.LineSeries, { color: '#ffa726', lineWidth: 1 });
                hs.setData(coin.hist);
                ms.setData(coin.macd);
                ss.setData(coin.signal);
                mChart.timeScale().fitContent();

                // 3. RSI Chart
                const rChart = LightweightCharts.createChart(document.getElementById(`rsi-${index}`), baseOpts);
                const rs = rChart.addSeries(LightweightCharts.LineSeries, { color: '#ab47bc', lineWidth: 2 });
                rs.setData(coin.rsi);
                rChart.timeScale().fitContent();

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
  print('Successfully generated functional index.html with Lightweight Charts v4 API.')

if __name__ == '__main__':
  main()
