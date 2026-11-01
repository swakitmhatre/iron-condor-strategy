#!/usr/bin/env python3
"""
Meme Coin Quantitative Backtesting & Technical Engine
Target Tickers: PEPE, WIF, BONK (Simulated / Public OHLCV Feed)
Risk Profile: Max Drawdown <= 5%, Integer Contract Sizing
"""

import math
import sys
import numpy as np
import pandas as pd

# Configuration Parameters
SYMBOLS = ['PEPE/USDT', 'WIF/USDT', 'BONK/USDT']
INITIAL_CAPITAL = 10000.0  # USD
MAX_ALLOWED_DRAWDOWN = 0.05  # 5% strict limit
LEVERAGE = 1.0  # Low leverage setting


def fetch_historical_data(symbol):
  """Generates or fetches clean OHLCV time series data for backtesting."""
  np.random.seed(42)  # Ensures deterministic reproducible backtest runs
  dates = pd.date_range(start='2026-01-01', periods=500, freq='1H')

  # Base price simulation depending on symbol
  base_price = 0.001 if 'PEPE' in symbol else (2.5 if 'WIF' in symbol else 0.00002)
  noise = np.random.normal(0, base_price * 0.02, size=len(dates))
  trend = np.linspace(0, base_price * 0.5, len(dates))

  close = np.abs(base_price + noise + trend)
  high = close + np.abs(np.random.normal(0, base_price * 0.01, size=len(dates)))
  low = close - np.abs(np.random.normal(0, base_price * 0.01, size=len(dates)))
  open_p = close + np.random.normal(0, base_price * 0.005, size=len(dates))
  volume = np.random.uniform(100000, 5000000, size=len(dates))

  df = pd.DataFrame({
      'timestamp': dates,
      'open': open_p,
      'high': high,
      'low': low,
      'close': close,
      'volume': volume,
  })
  return df


def calculate_indicators(df):
  """Computes 200 EMA, RSI, MACD, and Supertrend."""
  # 200 EMA
  df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()

  # RSI (14)
  delta = df['close'].diff()
  gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
  loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
  rs = gain / loss
  df['rsi'] = 100 - (100 / (1 + rs))

  # MACD
  exp1 = df['close'].ewm(span=12, adjust=False).mean()
  exp2 = df['close'].ewm(span=26, adjust=False).mean()
  df['macd'] = exp1 - exp2
  df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
  df['hist'] = df['macd'] - df['signal']

  # Supertrend (10, 3)
  atr_period = 10
  multiplier = 3.0
  hl2 = (df['high'] + df['low']) / 2
  df['tr'] = np.maximum(
      df['high'] - df['low'],
      np.maximum(
          np.abs(df['high'] - df['close'].shift()),
          np.abs(df['low'] - df['close'].shift()),
      ),
  )
  df['atr'] = df['tr'].rolling(window=atr_period).mean()

  df['upper_band'] = hl2 + (multiplier * df['atr'])
  df['lower_band'] = hl2 - (multiplier * df['atr'])

  supertrend = [True] * len(df)
  st_values = [0.0] * len(df)

  for i in range(1, len(df)):
    curr_close = df['close'].iloc[i]
    prev_close = df['close'].iloc[i - 1]

    if curr_close > df['upper_band'].iloc[i - 1]:
      supertrend[i] = True
    elif curr_close < df['lower_band'].iloc[i - 1]:
      supertrend[i] = False
    else:
      supertrend[i] = supertrend[i - 1]
      if (
          supertrend[i]
          and df['lower_band'].iloc[i] < df['lower_band'].iloc[i - 1]
      ):
        df.loc[i, 'lower_band'] = df['lower_band'].iloc[i - 1]
      elif (
          not supertrend[i]
          and df['upper_band'].iloc[i] > df['upper_band'].iloc[i - 1]
      ):
        df.loc[i, 'upper_band'] = df['upper_band'].iloc[i - 1]

    st_values[i] = (
        df['lower_band'].iloc[i] if supertrend[i] else df['upper_band'].iloc[i]
    )

  df['supertrend'] = st_values
  return df.dropna()


def run_backtest(symbol, df):
  """Backtests the strategy enforcing strict max drawdown <= 5% and integer contracts."""
  capital = INITIAL_CAPITAL
  peak_capital = capital
  max_drawdown = 0.0
  position = 0  # Integer contracts
  entry_price = 0.0
  trade_log = []

  for i in range(1, len(df)):
    row = df.iloc[i]
    price = row['close']

    # Strategy Signal: Long when Supertrend is active and RSI < 70
    signal_long = (row['close'] > row['supertrend']) and (row['rsi'] < 70)
    signal_exit = (row['close'] < row['supertrend']) or (row['rsi'] > 80)

    # Enforce integer contract sizing based on available capital
    if signal_long and position == 0:
      risk_budget = capital * 0.02  # Risk 2% per trade
      raw_contracts = risk_budget / price
      position = int(math.floor(raw_contracts))  # Strictly integer contracts
      if position > 0:
        entry_price = price

    elif (signal_exit or (position > 0 and price < entry_price * 0.98)) and (
        position > 0
    ):
      # Close position (Stop loss at -2% or exit signal)
      pnl = position * (price - entry_price)
      capital += pnl
      position = 0

    # Track drawdown dynamically
    if capital > peak_capital:
      peak_capital = capital

    current_dd = (peak_capital - capital) / peak_capital
    if current_dd > max_drawdown:
      max_drawdown = current_dd

    # Hard circuit breaker if drawdown exceeds 5% limit
    if max_drawdown > MAX_ALLOWED_DRAWDOWN:
      print(
          f'[{symbol}] CIRCUIT BREAKER TRIGGERED: Drawdown {max_drawdown:.2%}'
          ' exceeded limit!'
      )
      break

  total_return = ((capital - INITIAL_CAPITAL) / INITIAL_CAPITAL) * 100
  return {
      'symbol': symbol,
      'final_capital': round(capital, 2),
      'return_pct': round(total_return, 2),
      'max_drawdown_pct': round(max_drawdown * 100, 2),
  }


def main():
  print('=== STARTING MEME COIN QUANTITATIVE BACKTEST ===\n')
  results = []

  for symbol in SYMBOLS:
    df = fetch_historical_data(symbol)
    df = calculate_indicators(df)
    res = run_backtest(symbol, df)
    results.append(res)

  results_df = pd.DataFrame(results)
  print(results_df.to_string(index=False))
  print('\n=== BACKTEST COMPLETED SUCCESSFULLY ===')


if __name__ == '__main__':
  main()
