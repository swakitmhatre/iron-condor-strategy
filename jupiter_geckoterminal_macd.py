import base64
import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import requests

try:
    from solders.keypair import Keypair
    from solders.transaction import VersionedTransaction
    HAS_SOLDERS = True
except ImportError:
    HAS_SOLDERS = False

# --- CONFIGURATION & CONSTANTS ---
NETWORK = "solana"
BASE_URL = "https://api.geckoterminal.com/api/v2"
HEADERS = {"Accept": "application/json;version=20230302"}

JUPITER_SWAP_BASE = "https://api.jup.ag/swap/v2"
SOL_MINT = "So11111111111111111111111111111111111111112"

# Set to True once you have JUPITER_API_KEY, SOLANA_PRIVATE_KEY (base58), and funded SOL/USDC
LIVE_TRADING = False
TRADE_AMOUNT_SOL = 0.05
SLIPPAGE_BPS = 150

# Free tier rate-limit safeguard (~1.1 seconds between requests)
REQUEST_DELAY = 1.1
IST_OFFSET = timedelta(hours=5, minutes=30)

POOL_FETCH_INTERVAL = 900       # 15 Minutes for raw pool discovery
INDICATOR_CHECK_INTERVAL = 300  # 5 Minutes for active crossover monitoring
LOOKBACK_OVERWRITE_CANDLES = 5  # Fetch last 3-5 candles to overwrite late indexer updates
MAX_CACHED_CANDLES = 300

STATE_FILE = "/home/ubuntu/iron-condor-strategy/positions_state.json"


def api_get(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    url = f"{BASE_URL}/{endpoint}"
    try:
        time.sleep(REQUEST_DELAY)
        response = requests.get(url, headers=HEADERS, params=params, timeout=20)
        if response.status_code == 429:
            print("[!] Free tier rate limit hit (429). Backing off for 30 seconds...")
            time.sleep(30)
            return api_get(endpoint, params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"[Error] API request failed for {url}: {e}")
        return None


def convert_to_ist(utc_dt: Any) -> str:
    """Converts a UTC datetime, pandas Timestamp, or epoch seconds to IST string."""
    if utc_dt is None:
        return ""
    if isinstance(utc_dt, (int, float)):
        if np.isnan(utc_dt):
            return ""
        utc_dt = datetime.fromtimestamp(float(utc_dt), tz=timezone.utc)
    elif isinstance(utc_dt, pd.Timestamp):
        if pd.isna(utc_dt):
            return ""
        utc_dt = utc_dt.to_pydatetime()
    elif isinstance(utc_dt, datetime):
        if utc_dt.tzinfo is None:
            utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    else:
        return str(utc_dt)

    ist_dt = utc_dt.astimezone(timezone(IST_OFFSET))
    return ist_dt.strftime("%Y-%m-%d %H:%M:%S IST")


def is_solana_sol_pair(attr: Dict[str, Any]) -> bool:
    """
    Ensures the pool is explicitly paired against SOL (e.g. 'TOKEN / SOL')
    and ignores non-SOL quote pairs or cross-chain lookalikes.
    """
    name = attr.get("name", "").strip().upper()
    return "/ SOL" in name or name.endswith("SOL")


# --- STATE PERSISTENCE FOR AWS CRASH / REBOOT RECOVERY ---

def load_bot_state(state_path: str = STATE_FILE) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    if not os.path.exists(state_path):
        return {}, []
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        open_pos = data.get("open_positions")
        closed = data.get("closed_trades")
        return (
            open_pos if isinstance(open_pos, dict) else {},
            closed if isinstance(closed, list) else [],
        )
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[!] Warning: Could not load state file {state_path} ({exc}). Starting fresh.")
        return {}, []


def save_bot_state(
    open_positions: Dict[str, Dict[str, Any]],
    closed_trades: List[Dict[str, Any]],
    state_path: str = STATE_FILE,
) -> None:
    parent_dir = os.path.dirname(state_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    tmp_path = f"{state_path}.tmp"
    payload = {
        "open_positions": open_positions,
        "closed_trades": closed_trades,
    }
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, state_path)


# --- JUPITER SWAP EXECUTOR (ENTRY & EXIT ORDERS) ---

class JupiterExecutor:
    def __init__(
        self,
        live_trading: bool = LIVE_TRADING,
        trade_amount_sol: float = TRADE_AMOUNT_SOL,
        slippage_bps: int = SLIPPAGE_BPS,
    ) -> None:
        self.live_trading = live_trading
        self.trade_amount_sol = trade_amount_sol
        self.slippage_bps = slippage_bps
        self.api_key = os.getenv("JUPITER_API_KEY", "")
        self.priv_key_b58 = os.getenv("SOLANA_PRIVATE_KEY", "")
        self.keypair: Optional[Keypair] = None

        if self.live_trading:
            if not HAS_SOLDERS:
                raise RuntimeError("Missing 'solders'. Install with: pip install solders")
            if not self.api_key or not self.priv_key_b58:
                raise RuntimeError("Set JUPITER_API_KEY and SOLANA_PRIVATE_KEY env vars when LIVE_TRADING=True.")
            self.keypair = Keypair.from_base58_string(self.priv_key_b58)

    @property
    def taker_pubkey(self) -> str:
        return str(self.keypair.pubkey()) if self.keypair else "PAPER_WALLET"

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            h["x-api-key"] = self.api_key
        return h

    def _swap(self, input_mint: str, output_mint: str, amount_raw: int) -> Dict[str, Any]:
        if not self.live_trading:
            return {
                "status": "PAPER_FILLED",
                "tx_sig": "PAPER_SIMULATED_TX",
                "out_amount_raw": 0,
            }

        order_resp = requests.get(
            f"{JUPITER_SWAP_BASE}/order",
            headers=self._headers(),
            params={
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": str(int(amount_raw)),
                "slippageBps": int(self.slippage_bps),
                "taker": self.taker_pubkey,
            },
            timeout=20,
        )
        order_resp.raise_for_status()
        order_data = order_resp.json()

        raw_tx_b64 = order_data.get("transaction")
        request_id = order_data.get("requestId")
        if not raw_tx_b64:
            raise RuntimeError(f"Jupiter /order missing transaction: {json.dumps(order_data)[:250]}")

        tx = VersionedTransaction.from_bytes(base64.b64decode(raw_tx_b64))
        signed_tx = VersionedTransaction(tx.message, [self.keypair])
        signed_b64 = base64.b64encode(bytes(signed_tx)).decode("utf-8")

        exec_body: Dict[str, Any] = {"signedTransaction": signed_b64}
        if request_id:
            exec_body["requestId"] = request_id

        exec_resp = requests.post(
            f"{JUPITER_SWAP_BASE}/execute",
            headers=self._headers(),
            json=exec_body,
            timeout=30,
        )
        exec_resp.raise_for_status()
        exec_data = exec_resp.json()
        return {
            "status": exec_data.get("status", "SUBMITTED"),
            "tx_sig": exec_data.get("signature") or exec_data.get("txid") or "UNKNOWN_TX",
            "out_amount_raw": int(order_data.get("outAmount") or 0),
        }

    def buy_entry(self, token_mint: str, entry_price: float) -> Dict[str, Any]:
        lamports = int(self.trade_amount_sol * 1_000_000_000)
        res = self._swap(input_mint=SOL_MINT, output_mint=token_mint, amount_raw=lamports)
        out_raw = int(res.get("out_amount_raw") or 0)
        if out_raw <= 0 and entry_price > 0:
            # Paper mode fallback unit estimate
            out_raw = max(1, int((self.trade_amount_sol * 150.0 / entry_price) * 1_000_000))
        res["tokens_raw"] = out_raw
        return res

    def sell_exit(self, token_mint: str, tokens_raw: int) -> Dict[str, Any]:
        return self._swap(input_mint=token_mint, output_mint=SOL_MINT, amount_raw=max(1, int(tokens_raw)))


# --- STEP 1: ALL 4 RAW POOL DISCOVERY ENDPOINTS ---

def fetch_candidate_pools() -> List[Dict[str, Any]]:
    pools: List[Dict[str, Any]] = []
    seen_addresses = set()

    # 1. Trending Pools by Network
    print("[*] Fetching Trending Pools by Network...")
    for page in range(1, 4):
        data = api_get(f"networks/{NETWORK}/trending_pools", params={"page": page})
        if data and "data" in data:
            for p in data["data"]:
                if p["id"] not in seen_addresses:
                    seen_addresses.add(p["id"])
                    pools.append(p)
        time.sleep(REQUEST_DELAY)

    # 2. New Pools by Network
    print("[*] Fetching New Pools by Network...")
    for page in range(2, 5):
        data = api_get(f"networks/{NETWORK}/new_pools", params={"page": page})
        if data and "data" in data:
            for p in data["data"]:
                if p["id"] not in seen_addresses:
                    seen_addresses.add(p["id"])
                    pools.append(p)
        time.sleep(REQUEST_DELAY)

    # 3. Top Pools by Network
    print("[*] Fetching Top Pools by Network...")
    for page in range(1, 4):
        data = api_get(f"networks/{NETWORK}/pools", params={"page": page})
        if data and "data" in data:
            for p in data["data"]:
                if p["id"] not in seen_addresses:
                    seen_addresses.add(p["id"])
                    pools.append(p)
        time.sleep(REQUEST_DELAY)

    # 4. Top Pools by DEX (Raydium, Orca, Meteora)
    dex_list = ["raydium", "orca", "meteora"]
    for dex in dex_list:
        print(f"[*] Fetching Top Pools for DEX: {dex}...")
        for page in range(1, 3):
            data = api_get(f"networks/{NETWORK}/dexes/{dex}/pools", params={"page": page})
            if data and "data" in data:
                for p in data["data"]:
                    if p["id"] not in seen_addresses:
                        seen_addresses.add(p["id"])
                        pools.append(p)
            time.sleep(REQUEST_DELAY)

    print(f"[*] Total Unique Raw Pools Collected Across All 4 Endpoints: {len(pools)}")
    return pools


def fetch_token_deep_info(token_address: str) -> Dict[str, Any]:
    data = api_get(f"networks/{NETWORK}/tokens/{token_address}/info")
    if data and "data" in data:
        return data["data"].get("attributes", {})
    return {}


def filter_pools(pools: List[Dict[str, Any]], relax_filters: bool = False) -> List[Dict[str, Any]]:
    """
    Applies filters a -> q in sequence.
    If relax_filters is True (no tokens passed strict checks), criteria g -> q are bypassed.
    """
    filtered_list: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    passed_al_count = 0

    for pool in pools:
        attr = pool.get("attributes", {})
        if not is_solana_sol_pair(attr):
            continue
        relationships = pool.get("relationships", {})

        pool_address = pool.get("id")
        pool_name = attr.get("name", "Unknown Pool")
        created_at_str = attr.get("pool_created_at")
        liquidity_usd = float(attr.get("reserve_in_usd") or 0)
        market_cap = float(attr.get("market_cap_usd") or attr.get("fdv_usd") or 0)
        volume_24h = float(attr.get("volume_usd", {}).get("h24", 0) or 0)
        volume_6h = float(attr.get("volume_usd", {}).get("h6", 0) or 0)

        tx_24h = attr.get("transactions", {}).get("h24", {})
        buyers_24h = tx_24h.get("buyers", 0) or 0
        tx_count_24h = (tx_24h.get("buys", 0) or 0) + (tx_24h.get("sells", 0) or 0)

        if not created_at_str:
            continue
        created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        age_hours = (now - created_at).total_seconds() / 3600.0

        # Criteria a -> f
        if not (1 <= age_hours <= 24):
            continue
        if not (30000 <= market_cap <= 5000000):
            continue
        if liquidity_usd < 30000:
            continue
        if volume_24h < 50000 or volume_6h < 20000:
            continue
        if tx_count_24h < 500:
            continue

        buyers_6h = attr.get("transactions", {}).get("h6", {}).get("buyers", 0) or 0
        buyers_1h = attr.get("transactions", {}).get("h1", {}).get("buyers", 0) or 0
        if not (buyers_24h >= 300 and buyers_6h >= 50 and buyers_1h >= 20):
            continue

        try:
            base_token_rel = relationships.get("base_token", {}).get("data", {})
            token_address = base_token_rel.get("id", "").split("_")[-1]
        except Exception:
            continue

        if not token_address:
            continue

        if relax_filters:
            filtered_list.append({
                "pool_address": pool_address,
                "pool_name": pool_name,
                "token_address": token_address,
                "age_hours": age_hours,
                "liquidity": liquidity_usd,
                "market_cap": market_cap,
            })
            continue

        # Criteria g -> l
        price_change_6h = float(attr.get("price_change_percentage", {}).get("h6", 0) or 0)
        if price_change_6h < 5.0:
            continue

        token_info = fetch_token_deep_info(token_address)

        holders_data = token_info.get("holders", {})
        top_holder_pct = 100.0
        if isinstance(holders_data, dict):
            dist_pct = holders_data.get("distribution_percentage")
            if isinstance(dist_pct, dict) and dist_pct.get("top_10") is not None:
                top_holder_pct = float(dist_pct.get("top_10"))
        else:
            alt_pct = token_info.get("top_10_holder_percent")
            if alt_pct is not None:
                top_holder_pct = float(alt_pct)

        if top_holder_pct > 10.0:
            continue

        price_change_1h = float(attr.get("price_change_percentage", {}).get("h1", 0) or 0)
        price_change_24h = float(attr.get("price_change_percentage", {}).get("h24", 0) or 0)
        if not (price_change_1h > 0 and price_change_6h > 0 and price_change_24h > 0):
            continue

        buys_24h = tx_24h.get("buys", 0) or 0
        sells_24h = tx_24h.get("sells", 0) or 0
        buy_sell_ratio = (buys_24h / sells_24h) if sells_24h > 0 else 0
        if buy_sell_ratio < 1.5:
            continue

        makers_unique = tx_24h.get("users", 0) or 0
        if makers_unique < 2500:
            continue

        liq_mcap_ratio = (liquidity_usd / market_cap) if market_cap > 0 else 0
        if liq_mcap_ratio <= 0.05:
            continue

        passed_al_count += 1

        # Criteria m -> q
        mint_auth = token_info.get("mint_authority")
        freeze_auth = token_info.get("freeze_authority")
        twitter_handle = token_info.get("twitter_handle")
        lp_burned = token_info.get("is_lp_burned", False)
        lp_locked = token_info.get("is_lp_locked", False)

        if not (lp_locked or lp_burned):
            continue
        if not twitter_handle or str(twitter_handle).lower() in ["none", "null", ""]:
            continue
        if mint_auth is not None and mint_auth != "":
            continue
        if freeze_auth is not None and str(freeze_auth).lower() not in ["none", "null", ""]:
            continue

        filtered_list.append({
            "pool_address": pool_address,
            "pool_name": pool_name,
            "token_address": token_address,
            "age_hours": age_hours,
            "liquidity": liquidity_usd,
            "market_cap": market_cap,
        })

    mode_label = "Relaxed (Bypassing G-Q)" if relax_filters else "Strict (A-Q Enforced)"
    print(f"[*] Filter Stats [{mode_label}] -> Passed A-L: {passed_al_count} | Final Filtered: {len(filtered_list)}")
    return filtered_list


# --- STEP 2: DYNAMIC TIMEFRAMES, INCREMENTAL CACHE + 3-CANDLE LOOKBACK & SAFE INDICATORS ---

def get_candlestick_timeframe(age_hours: float) -> Tuple[str, int]:
    if 2 <= age_hours <= 8:
        return "minute", 5
    if age_hours > 8:
        return "minute", 15
    return "minute", 5


def fetch_ohlcv(
    pool_address: str,
    timeframe: str,
    aggregate: int,
    limit: int = 100,
    before_timestamp: Optional[int] = None,
) -> pd.DataFrame:
    clean_pool_addr = pool_address.split("_")[-1] if "_" in pool_address else pool_address
    endpoint = f"networks/{NETWORK}/pools/{clean_pool_addr}/ohlcv/{timeframe}"
    params: Dict[str, Any] = {"aggregate": aggregate, "limit": limit}
    if before_timestamp is not None:
        params["before_timestamp"] = int(before_timestamp)

    data = api_get(endpoint, params=params)
    if data and "data" in data:
        attributes = data["data"].get("attributes", {})
        ohlcv_list = attributes.get("ohlcv_list", [])
        if not ohlcv_list:
            return pd.DataFrame(columns=["ts_epoch", "timestamp", "open", "high", "low", "close", "volume"])

        df = pd.DataFrame(ohlcv_list, columns=["ts_epoch", "open", "high", "low", "close", "volume"])
        df["ts_epoch"] = pd.to_numeric(df["ts_epoch"], errors="coerce")
        for col in ("open", "high", "low", "close", "volume"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.dropna(subset=["ts_epoch", "open", "high", "low", "close"]).copy()
        df["ts_epoch"] = df["ts_epoch"].astype("int64")
        df["timestamp"] = pd.to_datetime(df["ts_epoch"], unit="s", utc=True)
        df = df.sort_values("ts_epoch").drop_duplicates("ts_epoch", keep="last").reset_index(drop=True)
        return df
    return pd.DataFrame(columns=["ts_epoch", "timestamp", "open", "high", "low", "close", "volume"])


def update_ohlcv_incremental(
    pool_address: str,
    timeframe: str,
    aggregate: int,
    cached_df: Optional[pd.DataFrame],
) -> pd.DataFrame:
    """
    1. Genesis fetch: pulls initial history (limit=100) on first run.
    2. 5-minute append loop + 3-candle lookback overwrite: fetches latest candles (limit=5)
       and overwrites matching timestamps in cached_df so late indexer updates replace stale bars.
    """
    if cached_df is None or cached_df.empty:
        genesis_df = fetch_ohlcv(pool_address, timeframe, aggregate, limit=100)
        return genesis_df.tail(MAX_CACHED_CANDLES).reset_index(drop=True)

    lookback_df = fetch_ohlcv(pool_address, timeframe, aggregate, limit=LOOKBACK_OVERWRITE_CANDLES)
    if lookback_df.empty:
        return cached_df.tail(MAX_CACHED_CANDLES).reset_index(drop=True)

    merged = pd.concat([cached_df, lookback_df], ignore_index=True)
    merged = merged.sort_values("ts_epoch").drop_duplicates("ts_epoch", keep="last").reset_index(drop=True)
    return merged.tail(MAX_CACHED_CANDLES).reset_index(drop=True)


def calculate_indicators(
    df: pd.DataFrame,
    current_market_cap: Optional[float] = None,
    pool_name: str = "UNKNOWN",
) -> pd.DataFrame:
    """
    Calculates MACD(8, 17, 9), RSI(14), and Supertrend(10, 3) safely on short or long histories
    without index errors.
    """
    if df.empty:
        return df

    out = df.copy().reset_index(drop=True)
    n = len(out)

    latest_close = float(out["close"].iloc[-1])
    if current_market_cap and current_market_cap > 0 and latest_close > 0:
        scaling_factor = current_market_cap / latest_close
        series = out["close"] * scaling_factor
        high_series = out["high"] * scaling_factor
        low_series = out["low"] * scaling_factor
    else:
        series = out["close"]
        high_series = out["high"]
        low_series = out["low"]

    # 1. MACD (8, 17, 9) — safe on any n >= 1
    ema_fast = series.ewm(span=8, adjust=False, min_periods=1).mean()
    ema_slow = series.ewm(span=17, adjust=False, min_periods=1).mean()
    out["macd_line"] = ema_fast - ema_slow
    out["macd_signal"] = out["macd_line"].ewm(span=9, adjust=False, min_periods=1).mean()
    out["histogram"] = out["macd_line"] - out["macd_signal"]

    # 2. RSI (14) — safe on short candle counts without division-by-zero errors
    delta = series.diff()
    gain = delta.clip(lower=0.0).rolling(window=14, min_periods=1).mean()
    loss = (-delta.clip(upper=0.0)).rolling(window=14, min_periods=1).mean()
    rs = np.where(loss == 0.0, np.where(gain == 0.0, 50.0, 100.0), gain / loss)
    out["rsi"] = 100.0 - (100.0 / (1.0 + rs))

    # 3. TradingView / DexScreener Supertrend (10, 3) — safe even when n < 10
    period = 10
    multiplier = 3.0
    prev_close = series.shift(1).fillna(series)
    tr = pd.concat(
        [
            high_series - low_series,
            (high_series - prev_close).abs(),
            (low_series - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = pd.Series(np.nan, index=out.index, dtype="float64")
    if n >= period:
        atr.iloc[period - 1] = tr.iloc[:period].mean()
        alpha = 1.0 / period
        for i in range(period, n):
            atr.iloc[i] = alpha * tr.iloc[i] + (1.0 - alpha) * atr.iloc[i - 1]
    else:
        atr = tr.ewm(span=period, adjust=False, min_periods=1).mean()

    basic_upper = (hl2 := (high_series + low_series) / 2.0) + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)

    up_list = basic_upper.tolist()
    dn_list = basic_lower.tolist()
    closes = series.tolist()

    final_upper = [np.nan] * n
    final_lower = [np.nan] * n
    supertrend_dir = [False] * n
    st_values = [np.nan] * n

    start_idx = period - 1 if n >= period else 0
    final_upper[start_idx] = up_list[start_idx]
    final_lower[start_idx] = dn_list[start_idx]
    supertrend_dir[start_idx] = bool(closes[start_idx] > up_list[start_idx])
    st_values[start_idx] = final_lower[start_idx] if supertrend_dir[start_idx] else final_upper[start_idx]

    for i in range(start_idx + 1, n):
        if up_list[i] < final_upper[i - 1] or closes[i - 1] > final_upper[i - 1]:
            final_upper[i] = up_list[i]
        else:
            final_upper[i] = final_upper[i - 1]

        if dn_list[i] > final_lower[i - 1] or closes[i - 1] < final_lower[i - 1]:
            final_lower[i] = dn_list[i]
        else:
            final_lower[i] = final_lower[i - 1]

        if supertrend_dir[i - 1]:
            supertrend_dir[i] = False if closes[i] < final_lower[i] else True
        else:
            supertrend_dir[i] = True if closes[i] > final_upper[i] else False

        st_values[i] = final_lower[i] if supertrend_dir[i] else final_upper[i]

    out["supertrend"] = st_values
    out["supertrend_dir"] = supertrend_dir
    out["calc_series"] = series
    return out


# --- STEP 3: CROSSOVER EVALUATION ---

def check_positive_crossover(curr: pd.Series, prev: Optional[pd.Series] = None) -> bool:
    if curr["macd_line"] <= curr["macd_signal"]:
        return False
    if curr["macd_line"] <= 0:
        return False
    if curr["histogram"] <= 0.10 * abs(curr["macd_line"]):
        return False
    if prev is not None and curr["histogram"] <= prev["histogram"]:
        return False
    if not curr["supertrend_dir"]:
        return False
    return True


def check_negative_crossover(row: pd.Series, prev_rows: List[Dict[str, Any]]) -> bool:
    if len(prev_rows) < 2:
        return False
    curr = row["histogram"]
    prev1 = prev_rows[-1]["histogram"]
    prev2 = prev_rows[-2]["histogram"]
    if row["macd_line"] < row["macd_signal"]:
        return True
    if row["macd_line"] < 0:
        return True
    if prev1 != 0 and curr < (prev1 - (0.18 * prev1)):
        return True
    if curr < prev1 < prev2:
        return True
    if not row["supertrend_dir"]:
        return True
    return False


# --- MAIN DUAL-SCHEDULE EXECUTION LOOP ---

def main() -> None:
    print(f"[{convert_to_ist(datetime.now(timezone.utc))}] Starting Solana Meme Coin Quant Bot...")

    jupiter = JupiterExecutor(
        live_trading=LIVE_TRADING,
        trade_amount_sol=TRADE_AMOUNT_SOL,
        slippage_bps=SLIPPAGE_BPS,
    )
    open_positions, closed_trades = load_bot_state()
    print(f"[*] State loaded: {len(open_positions)} open position(s), {len(closed_trades)} historical trade(s).")

    candidate_pools: List[Dict[str, Any]] = []
    filtered_pools: List[Dict[str, Any]] = []
    ohlcv_cache: Dict[str, pd.DataFrame] = {}
    last_pool_fetch_time = 0.0

    while True:
        current_time = time.time()

        # 1. Refresh raw pool candidates every 15 minutes
        if current_time - last_pool_fetch_time >= POOL_FETCH_INTERVAL or not candidate_pools:
            print("\n[*] Running 15-Minute Raw Pool Discovery & Filtering Routine...")
            candidate_pools = fetch_candidate_pools()
            filtered_pools = filter_pools(candidate_pools, relax_filters=False)

            if not filtered_pools:
                print("[*] No tokens met strict A->Q filters. Activating relaxation fallback (bypassing G-Q)...")
                filtered_pools = filter_pools(candidate_pools, relax_filters=True)

            last_pool_fetch_time = current_time

        # Ensure any pool with an open position after a reboot is still monitored for SELL_EXIT
        monitored_pools: Dict[str, Dict[str, Any]] = {}
        for item in filtered_pools:
            monitored_pools[item["pool_address"]] = item
        for p_addr, pos in open_positions.items():
            if p_addr not in monitored_pools:
                monitored_pools[p_addr] = {
                    "pool_address": p_addr,
                    "pool_name": pos.get("Pool Name", p_addr),
                    "token_address": pos.get("Token Address", ""),
                    "age_hours": pos.get("Age Hours", 4.0),
                    "liquidity": 0.0,
                    "market_cap": 0.0,
                }

        print(f"\n[*] [{convert_to_ist(datetime.now(timezone.utc))}] Checking Crossovers for {len(monitored_pools)} pool(s)...")

        all_current_signals_detailed: List[Dict[str, Any]] = []
        latest_prices: Dict[str, float] = {}

        for p_addr, item in monitored_pools.items():
            pool_name = item["pool_name"]
            token_addr = item.get("token_address", "")
            age = float(item.get("age_hours", 4.0))
            tf, agg = get_candlestick_timeframe(age)
            cache_key = f"{p_addr}_{agg}{tf[0]}"

            print(f"\n[*] Evaluating {pool_name} ({p_addr}) [{agg}{tf[0]}]")
            updated_df = update_ohlcv_incremental(p_addr, tf, agg, ohlcv_cache.get(cache_key))
            ohlcv_cache[cache_key] = updated_df

            if updated_df.empty or len(updated_df) < 3:
                print(f"[!] Skipping {pool_name}: insufficient OHLCV candles ({len(updated_df)})")
                continue

            df = calculate_indicators(updated_df, current_market_cap=item.get("market_cap"), pool_name=pool_name)
            latest_prices[p_addr] = float(df["close"].iloc[-1])

            start_idx = max(10, 20 if len(df) >= 20 else 2)
            active_entry_idx: Optional[int] = None
            active_entry_price: float = 0.0

            for i in range(start_idx, len(df)):
                prev_prev = df.iloc[i - 2]
                prev = df.iloc[i - 1]
                curr = df.iloc[i]

                is_pos_cross = check_positive_crossover(curr, prev)
                is_neg_cross = check_negative_crossover(curr, [prev_prev.to_dict(), prev.to_dict()])

                curr_price = float(curr["close"])
                curr_ts_ist = convert_to_ist(curr["timestamp"])

                if p_addr not in open_positions and is_pos_cross:
                    try:
                        order_res = jupiter.buy_entry(token_mint=token_addr, entry_price=curr_price)
                    except Exception as exc:
                        print(f"[!] BUY_ENTRY order error for {pool_name}: {exc}")
                        continue

                    open_positions[p_addr] = {
                        "Pool Name": pool_name,
                        "Pool Address": p_addr,
                        "Token Address": token_addr,
                        "Age Hours": age,
                        "Entry (IST)": curr_ts_ist,
                        "Entry Price": curr_price,
                        "Tokens Raw": order_res.get("tokens_raw", 0),
                        "Entry Tx": order_res.get("tx_sig", ""),
                        "Status": order_res.get("status", "OPEN"),
                    }
                    save_bot_state(open_positions, closed_trades)
                    print(f"[+] BUY_ENTRY executed for {pool_name} @ {curr_price:.8f} | Tx: {open_positions[p_addr]['Entry Tx']}")

                elif p_addr in open_positions and is_neg_cross:
                    pos = open_positions.pop(p_addr)
                    entry_px = float(pos.get("Entry Price") or curr_price)
                    try:
                        exit_res = jupiter.sell_exit(
                            token_mint=pos.get("Token Address") or token_addr,
                            tokens_raw=int(pos.get("Tokens Raw") or 1),
                        )
                        exit_tx = exit_res.get("tx_sig", "")
                    except Exception as exc:
                        print(f"[!] SELL_EXIT order error for {pool_name}: {exc}")
                        exit_tx = "EXIT_ORDER_ERROR"

                    pnl_pct = ((curr_price - entry_px) / entry_px) * 100.0 if entry_px > 0 else 0.0
                    closed_trades.append({
                        "Pool Name": pos.get("Pool Name", pool_name),
                        "DexScreener Address": p_addr,
                        "Entry (IST)": pos.get("Entry (IST)", ""),
                        "Exit (IST)": curr_ts_ist,
                        "PnL (%)": round(pnl_pct, 2),
                        "Entry Tx": pos.get("Entry Tx", ""),
                        "Exit Tx": exit_tx,
                    })
                    save_bot_state(open_positions, closed_trades)
                    print(f"[-] SELL_EXIT executed for {pool_name} @ {curr_price:.8f} | PnL: {pnl_pct:+.2f}% | Tx: {exit_tx}")

            # If still holding an open long position after historical loop, populate Table 2
            if p_addr in open_positions:
                pos = open_positions[p_addr]
                active_entry_price = float(pos.get("Entry Price") or df["close"].iloc[-1])
                # Find matching entry candle index if inside current df window, else start from latest candle
                entry_matches = df.index[df["timestamp"].apply(convert_to_ist) == pos.get("Entry (IST)")].tolist()
                active_entry_idx = entry_matches[-1] if entry_matches else (len(df) - 1)

                active_df = df.iloc[active_entry_idx:]
                for _, row in active_df.iterrows():
                    candle_close = float(row["close"])
                    live_pnl_pct = ((candle_close - active_entry_price) / active_entry_price) * 100.0 if active_entry_price > 0 else 0.0
                    st_status = "BULLISH" if row.get("supertrend_dir", True) else "BEARISH"

                    all_current_signals_detailed.append({
                        "Pool Name": pool_name,
                        "DexScreener Pool Address": p_addr,
                        "Timestamp (IST)": convert_to_ist(row["timestamp"]),
                        "Open": f"{row['open']:.8f}",
                        "High": f"{row['high']:.8f}",
                        "Low": f"{row['low']:.8f}",
                        "Close": f"{row['close']:.8f}",
                        "MACD": f"{row.get('macd_line', 0):.6f}",
                        "MACD Signal": f"{row.get('macd_signal', 0):.6f}",
                        "Histogram": f"{row.get('histogram', 0):.6f}",
                        "Supertrend": f"{row.get('supertrend', 0):.8f} ({st_status})",
                        "RSI": f"{row.get('rsi', 0):.1f}",
                        "Live PnL (%)": f"{live_pnl_pct:+.2f}%",
                    })

        # --- OPEN POSITIONS LOG (PERSISTED IN positions_state.json) ---
        print("\n" + "=" * 130)
        print("OPEN POSITIONS LOG (RECOVERED FROM positions_state.json ON REBOOT)")
        print("=" * 130)
        if open_positions:
            open_rows = []
            for p_addr, pos in open_positions.items():
                entry_px = float(pos.get("Entry Price") or 0.0)
                mark_px = latest_prices.get(p_addr, entry_px)
                u_pnl = ((mark_px - entry_px) / entry_px) * 100.0 if entry_px > 0 else 0.0
                open_rows.append({
                    "Pool Name": pos.get("Pool Name", p_addr),
                    "Entry (IST)": pos.get("Entry (IST)", ""),
                    "Entry Price": f"{entry_px:.8f}",
                    "Mark Price": f"{mark_px:.8f}",
                    "Unrealized PnL (%)": f"{u_pnl:+.2f}%",
                    "Status": pos.get("Status", "OPEN"),
                    "Entry Tx": pos.get("Entry Tx", ""),
                })
            print(pd.DataFrame(open_rows).to_string(index=False))
        else:
            print("No currently open long positions.")

        # --- TABLE 1: HISTORICAL COMPLETED LONG TRADES ---
        print("\n" + "=" * 130)
        print("TABLE 1: HISTORICAL POSITIVE MACD CROSSOVER TRADES & POOL ADDRESSES (IST Timestamps)")
        print("=" * 130)
        if closed_trades:
            print(pd.DataFrame(closed_trades).to_string(index=False))
        else:
            print("No completed historical crossover trades found in current dataset.")

        # --- TABLE 2: CURRENT ACTIVE POSITIVE MACD CROSSOVER ---
        print("\n" + "=" * 130)
        print("TABLE 2: CURRENT ACTIVE POSITIVE MACD CROSSOVERS (LONG ONLY)")
        print("=" * 130)
        if all_current_signals_detailed:
            print(pd.DataFrame(all_current_signals_detailed).to_string(index=False))
        else:
            print("No current positive crossover detected on latest candles for any token.")
        print("=" * 130 + "\n")

        print("[*] Indicator check completed. Sleeping for 5 minutes before next 5-min candle evaluation...")
        time.sleep(INDICATOR_CHECK_INTERVAL)


if __name__ == "__main__":
    main()
