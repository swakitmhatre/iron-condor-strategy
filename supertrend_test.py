from datetime import datetime, timezone, timedelta
import time
import numpy as np
import pandas as pd
import requests

BASE_URL = "https://api.geckoterminal.com/api/v2"
HEADERS = {"Accept": "application/json;version=20230302"}
IST = timezone(timedelta(hours=5, minutes=30))

POOLS = [
    {
        "coin": "SOL",
        "pool_name": "SOL / USDC (Solana)",
        "network": "solana",
        "pool": "58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2",
    },
    {
        "coin": "PEPE",
        "pool_name": "PEPE / WETH (Ethereum)",
        "network": "eth",
        "pool": "0xa43fe16908251ee70ef74718545e4fe6c5ccec9f",
    },
]


def fetch_15m_ohlcv(network: str, pool_address: str, limit: int = 250, before_ts: int | None = None) -> pd.DataFrame:
    url = f"{BASE_URL}/networks/{network}/pools/{pool_address}/ohlcv/minute"
    params = {"aggregate": 15, "limit": limit}
    if before_ts is not None:
        params["before_timestamp"] = before_ts

    resp = requests.get(url, headers=HEADERS, params=params, timeout=20)
    resp.raise_for_status()
    ohlcv_list = resp.json()["data"]["attributes"]["ohlcv_list"]
    if not ohlcv_list:
        return pd.DataFrame()

    df = pd.DataFrame(ohlcv_list, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s", utc=True)
    df = df.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)
    return df


def calculate_indicators(df: pd.DataFrame, st_period: int = 10, st_mult: float = 3.0) -> pd.DataFrame:
    df = df.copy()
    close = df["close"]
    high = df["high"]
    low = df["low"]

    # MACD (8, 17, 9)
    ema_fast = close.ewm(span=8, adjust=False).mean()
    ema_slow = close.ewm(span=17, adjust=False).mean()
    df["macd_line"] = ema_fast - ema_slow
    df["macd_signal"] = df["macd_line"].ewm(span=9, adjust=False).mean()
    df["histogram"] = df["macd_line"] - df["macd_signal"]

    # TradingView-matched Supertrend (10, 3): SMA seed on bar (period - 1), then Wilder's RMA
    hl2 = (high + low) / 2.0
    tr = pd.concat(
        [
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = pd.Series(np.nan, index=df.index, dtype="float64")
    if len(df) >= st_period:
        atr.iloc[st_period - 1] = tr.iloc[:st_period].mean()
        alpha = 1.0 / st_period
        for i in range(st_period, len(df)):
            atr.iloc[i] = alpha * tr.iloc[i] + (1.0 - alpha) * atr.iloc[i - 1]

    basic_upper = (hl2 + st_mult * atr).tolist()
    basic_lower = (hl2 - st_mult * atr).tolist()
    closes = close.tolist()

    n = len(df)
    final_upper = [np.nan] * n
    final_lower = [np.nan] * n
    supertrend_dir = [False] * n
    st_values = [np.nan] * n

    start_idx = st_period - 1
    if n > start_idx:
        final_upper[start_idx] = basic_upper[start_idx]
        final_lower[start_idx] = basic_lower[start_idx]
        supertrend_dir[start_idx] = closes[start_idx] > basic_upper[start_idx]
        st_values[start_idx] = (
            final_lower[start_idx] if supertrend_dir[start_idx] else final_upper[start_idx]
        )

        for i in range(start_idx + 1, n):
            if basic_upper[i] < final_upper[i - 1] or closes[i - 1] > final_upper[i - 1]:
                final_upper[i] = basic_upper[i]
            else:
                final_upper[i] = final_upper[i - 1]

            if basic_lower[i] > final_lower[i - 1] or closes[i - 1] < final_lower[i - 1]:
                final_lower[i] = basic_lower[i]
            else:
                final_lower[i] = final_lower[i - 1]

            if supertrend_dir[i - 1]:
                supertrend_dir[i] = False if closes[i] < final_lower[i] else True
            else:
                supertrend_dir[i] = True if closes[i] > final_upper[i] else False

            st_values[i] = final_lower[i] if supertrend_dir[i] else final_upper[i]

    df["supertrend"] = st_values
    df["supertrend_dir"] = supertrend_dir
    df["timestamp_ist"] = df["timestamp"].dt.tz_convert(IST).dt.strftime("%Y-%m-%d %H:%M IST")
    return df


def get_flips_with_min_count(network: str, pool: str, min_flips: int = 4, max_pages: int = 4):
    """Fetches 250+ 15m candles per page backwards until at least `min_flips` real flips are found."""
    combined = pd.DataFrame()
    before_ts = None

    for _ in range(max_pages):
        page_df = fetch_15m_ohlcv(network, pool, limit=250, before_ts=before_ts)
        if page_df.empty:
            break
        combined = pd.concat([page_df, combined], ignore_index=True)
        combined = combined.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)

        ind_df = calculate_indicators(combined, st_period=10, st_mult=3.0)
        valid = ind_df.dropna(subset=["supertrend"]).copy()
        flips = valid[valid["supertrend_dir"] != valid["supertrend_dir"].shift(1)].iloc[1:]  # skip warmup start row

        if len(flips) >= min_flips or len(page_df) < 200:
            return ind_df, flips

        before_ts = int(combined["timestamp"].iloc[0].timestamp())
        time.sleep(1.2)

    ind_df = calculate_indicators(combined, st_period=10, st_mult=3.0)
    valid = ind_df.dropna(subset=["supertrend"]).copy()
    flips = valid[valid["supertrend_dir"] != valid["supertrend_dir"].shift(1)].iloc[1:]
    return ind_df, flips


def main():
    all_flips = []

    for item in POOLS:
        print("=" * 115)
        print(f"COIN: {item['coin']} | Pool: {item['pool_name']} | https://dexscreener.com/{item['network']}/{item['pool']}")
        df, flips = get_flips_with_min_count(item["network"], item["pool"], min_flips=4, max_pages=4)
        print(f"Total 15m candles fetched: {len(df)} | Total Supertrend flips found: {len(flips)}")

        cols = ["timestamp_ist", "close", "supertrend", "supertrend_dir", "macd_line", "macd_signal", "histogram"]
        print(f"\n--- [{item['coin']}] Last 5 (15-Min) Candles ---")
        print(df[cols].tail(5).to_string(index=False))

        recent_flips = flips.tail(5).copy()
        recent_flips.insert(0, "coin", item["coin"])
        recent_flips["flip_to"] = recent_flips["supertrend_dir"].map({True: "GREEN (BULLISH)", False: "RED (BEARISH)"})
        all_flips.append(recent_flips[["coin", "timestamp_ist", "close", "supertrend", "flip_to", "macd_line", "histogram"]])

        time.sleep(1.2)

    print("\n" + "=" * 115)
    print("SUMMARY: SUPERTREND FLIPS BY COIN (FOR DEXSCREENER CROSS-CHECK)")
    print("=" * 115)
    if all_flips:
        summary_df = pd.concat(all_flips, ignore_index=True)
        print(summary_df.to_string(index=False))
    else:
        print("No Supertrend flips detected in fetched history.")


if __name__ == "__main__":
    main()
