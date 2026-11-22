import base64
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
import json
import os
import time
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

# --- CONFIGURATION ---
NETWORK = "solana"
GECKO_BASE_URL = "https://api.geckoterminal.com/api/v2"
GECKO_HEADERS = {"Accept": "application/json;version=20230302"}

JUPITER_ORDER_URL = "https://api.jup.ag/swap/v2/order"
JUPITER_EXECUTE_URL = "https://api.jup.ag/swap/v2/execute"
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")

SOL_MINT = "So11111111111111111111111111111111111111112"
LAMPORTS_PER_SOL = Decimal("1000000000")

# Trading & Risk Controls
LIVE_TRADING = False
MAX_ACTIVE_COINS = 2                     # Up to 2 coins (50% each); remaining capital stays idle
MAX_CAPITAL_PCT_PER_COIN = Decimal("0.50")
FEE_RESERVE_SOL = Decimal("0.02")        # Reserve SOL for rent/tx fees
PAPER_TOTAL_CAPITAL_SOL = Decimal("1.00")
SLIPPAGE_BPS = 150                       # 1.50%
PRIORITIZATION_FEE_LAMPORTS = 200_000    # Low controlled cap (0.0002 SOL)
PRIORITIZATION_TYPE = "maxCap"           # "maxCap" or "exactFee"
ORDER_MAX_RETRIES = 3
ORDER_RETRY_DELAY_SEC = 2.5

MIN_CANDLES_FOR_INDICATORS = 35
REQUEST_DELAY = 1.1
IST_OFFSET = timedelta(hours=5, minutes=30)
POOL_FETCH_INTERVAL = 900
INDICATOR_CHECK_INTERVAL = 300
STATE_FILE = "/home/ubuntu/iron-condor-strategy/positions_state.json"


def d(val: Any, default: str = "0") -> Decimal:
    if val is None or val == "":
        return Decimal(default)
    try:
        dec = Decimal(str(val))
        return Decimal(default) if not dec.is_finite() else dec
    except Exception:
        return Decimal(default)


def sol_to_lamports(sol_amount: Decimal) -> int:
    clamped = max(Decimal("0"), sol_amount.quantize(Decimal("0.000000001"), rounding=ROUND_DOWN))
    return int((clamped * LAMPORTS_PER_SOL).to_integral_value(rounding=ROUND_DOWN))


def lamports_to_sol(lamports: int) -> Decimal:
    return (Decimal(int(lamports)) / LAMPORTS_PER_SOL).quantize(Decimal("0.000000001"), rounding=ROUND_DOWN)


def convert_to_ist(utc_dt: Any) -> str:
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
    elif isinstance(utc_dt, datetime) and utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    return utc_dt.astimezone(timezone(IST_OFFSET)).strftime("%Y-%m-%d %H:%M:%S IST")


def api_get(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    url = f"{GECKO_BASE_URL}/{endpoint}"
    try:
        time.sleep(REQUEST_DELAY)
        resp = requests.get(url, headers=GECKO_HEADERS, params=params, timeout=20)
        if resp.status_code == 429:
            print("[!] Rate limit (429). Sleeping 30s...")
            time.sleep(30)
            return api_get(endpoint, params)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as exc:
        print(f"[Error] GeckoTerminal request failed ({url}): {exc}")
        return None


def is_solana_sol_pair(attr: Dict[str, Any]) -> bool:
    name = str(attr.get("name", "")).strip().upper()
    return "/ SOL" in name or name.endswith("SOL")


def load_bot_state(state_path: str = STATE_FILE) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    if not os.path.exists(state_path):
        return {}, []
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return (
            data.get("open_positions") if isinstance(data.get("open_positions"), dict) else {},
            data.get("closed_trades") if isinstance(data.get("closed_trades"), list) else [],
        )
    except Exception as exc:
        print(f"[!] State load warning ({exc}). Starting clean.")
        return {}, []


def save_bot_state(
    open_positions: Dict[str, Dict[str, Any]],
    closed_trades: List[Dict[str, Any]],
    state_path: str = STATE_FILE,
) -> None:
    parent = os.path.dirname(state_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    tmp = f"{state_path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"open_positions": open_positions, "closed_trades": closed_trades}, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, state_path)


class JupiterTrader:
    def __init__(self) -> None:
        self.live = LIVE_TRADING
        self.api_key = os.getenv("JUPITER_API_KEY", "")
        self.priv_key = os.getenv("SOLANA_PRIVATE_KEY", "")
        self.keypair: Optional[Keypair] = None
        self.paper_balance_sol = PAPER_TOTAL_CAPITAL_SOL

        if self.live:
            if not HAS_SOLDERS:
                raise RuntimeError("Install 'solders' (`pip install solders`) for live Jupiter signing.")
            if not self.api_key or not self.priv_key:
                raise RuntimeError("Set JUPITER_API_KEY and SOLANA_PRIVATE_KEY when LIVE_TRADING=True.")
            self.keypair = Keypair.from_base58_string(self.priv_key)

    @property
    def taker_pubkey(self) -> str:
        return str(self.keypair.pubkey()) if self.keypair else "PAPER_WALLET"

    def get_wallet_sol_balance(self) -> Decimal:
        if not self.live:
            return self.paper_balance_sol
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "getBalance",
            "params": [self.taker_pubkey],
        }
        resp = requests.post(SOLANA_RPC_URL, json=payload, timeout=15)
        resp.raise_for_status()
        lamports = int(((resp.json().get("result") or {}).get("value")) or 0)
        return lamports_to_sol(lamports)

    def calc_allocatable_sol(self, open_positions: Dict[str, Dict[str, Any]]) -> Decimal:
        """
        Enforces max 50% of total capital per coin and supports up to MAX_ACTIVE_COINS (2).
        Any remaining capital stays idle.
        """
        if len(open_positions) >= MAX_ACTIVE_COINS:
            return Decimal("0")

        wallet_sol = self.get_wallet_sol_balance()
        allocated_open_sol = sum((d(p.get("Allocated SOL")) for p in open_positions.values()), Decimal("0"))
        total_capital_sol = max(Decimal("0"), wallet_sol + allocated_open_sol)
        per_coin_cap_sol = (total_capital_sol * MAX_CAPITAL_PCT_PER_COIN).quantize(
            Decimal("0.000001"), rounding=ROUND_DOWN
        )

        spendable_now_sol = max(Decimal("0"), wallet_sol - FEE_RESERVE_SOL)
        return min(per_coin_cap_sol, spendable_now_sol).quantize(Decimal("0.000001"), rounding=ROUND_DOWN)

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            h["x-api-key"] = self.api_key
        return h

    def _swap_with_retry(self, input_mint: str, output_mint: str, amount_raw: int) -> Dict[str, Any]:
        if amount_raw <= 0:
            raise ValueError("Swap amount in smallest units must be > 0.")

        if not self.live:
            return {
                "status": "PAPER_FILLED",
                "tx_sig": "PAPER_TX",
                "out_amount_raw": 0,
                "in_amount_raw": amount_raw,
            }

        last_err: Optional[Exception] = None
        for attempt in range(1, ORDER_MAX_RETRIES + 1):
            try:
                order_params = {
                    "inputMint": input_mint,
                    "outputMint": output_mint,
                    "amount": str(int(amount_raw)),
                    "slippageBps": int(SLIPPAGE_BPS),
                    "taker": self.taker_pubkey,
                    "prioritizationFeeLamports": int(PRIORITIZATION_FEE_LAMPORTS),
                    "prioritizationType": PRIORITIZATION_TYPE,
                }
                order_resp = requests.get(
                    JUPITER_ORDER_URL,
                    headers=self._headers(),
                    params=order_params,
                    timeout=20,
                )
                order_resp.raise_for_status()
                order_data = order_resp.json()

                raw_tx_b64 = order_data.get("transaction")
                request_id = order_data.get("requestId")
                if not raw_tx_b64:
                    raise RuntimeError(f"Missing transaction in /order response: {json.dumps(order_data)[:250]}")

                tx = VersionedTransaction.from_bytes(base64.b64decode(raw_tx_b64))
                signed_tx = VersionedTransaction(tx.message, [self.keypair])
                signed_b64 = base64.b64encode(bytes(signed_tx)).decode("utf-8")

                exec_body: Dict[str, Any] = {"signedTransaction": signed_b64}
                if request_id:
                    exec_body["requestId"] = request_id

                exec_resp = requests.post(
                    JUPITER_EXECUTE_URL,
                    headers=self._headers(),
                    json=exec_body,
                    timeout=30,
                )
                exec_resp.raise_for_status()
                exec_data = exec_resp.json()
                return {
                    "status": exec_data.get("status", "SUBMITTED"),
                    "tx_sig": exec_data.get("signature") or exec_data.get("txid") or "SUBMITTED_TX",
                    "out_amount_raw": int(order_data.get("outAmount") or 0),
                    "in_amount_raw": int(order_data.get("inAmount") or amount_raw),
                }
            except Exception as exc:
                last_err = exc
                print(f"[!] Jupiter swap attempt {attempt}/{ORDER_MAX_RETRIES} failed: {exc}")
                if attempt < ORDER_MAX_RETRIES:
                    time.sleep(ORDER_RETRY_DELAY_SEC * attempt)

        raise RuntimeError(f"Jupiter swap failed after {ORDER_MAX_RETRIES} retries: {last_err}")

    def buy_entry(
        self,
        token_mint: str,
        alloc_sol: Decimal,
        entry_price_usd: Decimal,
        sol_usd_price: Decimal = Decimal("150"),
    ) -> Dict[str, Any]:
        lamports = sol_to_lamports(alloc_sol)
        res = self._swap_with_retry(input_mint=SOL_MINT, output_mint=token_mint, amount_raw=lamports)

        if not self.live:
            self.paper_balance_sol = max(Decimal("0"), self.paper_balance_sol - alloc_sol)
            est_raw = (
                int(((alloc_sol * sol_usd_price / entry_price_usd) * Decimal("1000000")).to_integral_value(rounding=ROUND_DOWN))
                if entry_price_usd > 0
                else 1
            )
            res["tokens_raw"] = max(1, est_raw)
        else:
            res["tokens_raw"] = max(1, int(res.get("out_amount_raw") or 0))

        res["allocated_sol"] = alloc_sol
        return res

    def sell_exit(self, token_mint: str, tokens_raw: int, alloc_sol: Decimal, pnl_pct: Decimal) -> Dict[str, Any]:
        res = self._swap_with_retry(input_mint=token_mint, output_mint=SOL_MINT, amount_raw=max(1, int(tokens_raw)))
        if not self.live:
            returned_sol = (alloc_sol * (Decimal("1") + (pnl_pct / Decimal("100")))).quantize(
                Decimal("0.000000001"), rounding=ROUND_DOWN
            )
            self.paper_balance_sol = max(Decimal("0"), self.paper_balance_sol + returned_sol)
        return res


# --- POOL DISCOVERY & FILTERING ---

def fetch_candidate_pools() -> List[Dict[str, Any]]:
    pools: List[Dict[str, Any]] = []
    seen = set()

    for endpoint, pages in [
        (f"networks/{NETWORK}/trending_pools", range(1, 4)),
        (f"networks/{NETWORK}/new_pools", range(2, 5)),
        (f"networks/{NETWORK}/pools", range(1, 4)),
    ]:
        for page in pages:
            data = api_get(endpoint, params={"page": page})
            if data and "data" in data:
                for p in data["data"]:
                    if p["id"] not in seen:
                        seen.add(p["id"])
                        pools.append(p)

    for dex in ("raydium", "orca", "meteora"):
        for page in range(1, 3):
            data = api_get(f"networks/{NETWORK}/dexes/{dex}/pools", params={"page": page})
            if data and "data" in data:
                for p in data["data"]:
                    if p["id"] not in seen:
                        seen.add(p["id"])
                        pools.append(p)

    return pools


def fetch_token_deep_info(token_address: str) -> Dict[str, Any]:
    data = api_get(f"networks/{NETWORK}/tokens/{token_address}/info")
    if data and "data" in data:
        return data["data"].get("attributes", {})
    return {}


def filter_pools(pools: List[Dict[str, Any]], relax_filters: bool = False) -> List[Dict[str, Any]]:
    filtered: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    for pool in pools:
        attr = pool.get("attributes", {})
        if not is_solana_sol_pair(attr):
            continue

        created_at_str = attr.get("pool_created_at")
        if not created_at_str:
            continue
        created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        age_hours = (now - created_at).total_seconds() / 3600.0

        liquidity_usd = float(attr.get("reserve_in_usd") or 0)
        market_cap = float(attr.get("market_cap_usd") or attr.get("fdv_usd") or 0)
        vol_24h = float((attr.get("volume_usd") or {}).get("h24", 0) or 0)
        vol_6h = float((attr.get("volume_usd") or {}).get("h6", 0) or 0)

        tx = attr.get("transactions") or {}
        tx_24h = tx.get("h24") or {}
        buys_24h = tx_24h.get("buys", 0) or 0
        sells_24h = tx_24h.get("sells", 0) or 0
        tx_count_24h = buys_24h + sells_24h
        buyers_24h = tx_24h.get("buyers", 0) or 0
        buyers_6h = (tx.get("h6") or {}).get("buyers", 0) or 0
        buyers_1h = (tx.get("h1") or {}).get("buyers", 0) or 0

        if not (1 <= age_hours <= 24):
            continue
        if not (30000 <= market_cap <= 5000000):
            continue
        if liquidity_usd < 30000:
            continue
        if vol_24h < 50000 or vol_6h < 20000:
            continue
        if tx_count_24h < 500:
            continue
        if not (buyers_24h >= 300 and buyers_6h >= 50 and buyers_1h >= 20):
            continue

        base_token_id = (((pool.get("relationships") or {}).get("base_token") or {}).get("data") or {}).get("id", "")
        token_address = base_token_id.split("_")[-1] if base_token_id else ""
        if not token_address:
            continue

        if relax_filters:
            filtered.append({
                "pool_address": pool.get("id"),
                "pool_name": attr.get("name", "Unknown Pool"),
                "token_address": token_address,
                "age_hours": age_hours,
                "market_cap": market_cap,
            })
            continue

        chg = attr.get("price_change_percentage") or {}
        chg_1h = float(chg.get("h1", 0) or 0)
        chg_6h = float(chg.get("h6", 0) or 0)
        chg_24h = float(chg.get("h24", 0) or 0)
        if chg_6h < 5.0 or not (chg_1h > 0 and chg_6h > 0 and chg_24h > 0):
            continue

        buy_sell_ratio = (buys_24h / sells_24h) if sells_24h > 0 else 0.0
        if buy_sell_ratio < 1.5:
            continue

        makers_unique = tx_24h.get("users", 0) or 0
        if makers_unique < 2500:
            continue

        liq_mcap_ratio = (liquidity_usd / market_cap) if market_cap > 0 else 0.0
        if liq_mcap_ratio <= 0.05:
            continue

        t_info = fetch_token_deep_info(token_address)
        holders_data = t_info.get("holders") or {}
        top_holder_pct = 100.0
        if isinstance(holders_data, dict):
            top_10_val = (holders_data.get("distribution_percentage") or {}).get("top_10")
            if top_10_val is not None:
                top_holder_pct = float(top_10_val)
        elif t_info.get("top_10_holder_percent") is not None:
            top_holder_pct = float(t_info.get("top_10_holder_percent"))
        if top_holder_pct > 10.0:
            continue

        if not (t_info.get("is_lp_locked", False) or t_info.get("is_lp_burned", False)):
            continue
        twitter = t_info.get("twitter_handle")
        if not twitter or str(twitter).lower() in ("none", "null", ""):
            continue
        mint_auth = t_info.get("mint_authority")
        if mint_auth is not None and mint_auth != "":
            continue
        freeze_auth = t_info.get("freeze_authority")
        if freeze_auth is not None and str(freeze_auth).lower() not in ("none", "null", ""):
            continue

        filtered.append({
            "pool_address": pool.get("id"),
            "pool_name": attr.get("name", "Unknown Pool"),
            "token_address": token_address,
            "age_hours": age_hours,
            "market_cap": market_cap,
        })

    return filtered


# --- CANDLES & INDICATORS (REQUIRES AT LEAST 35 CANDLES) ---

def get_candlestick_timeframe(age_hours: float) -> Tuple[str, int]:
    if 2 <= age_hours <= 8:
        return "minute", 5
    return "minute", 15


def fetch_ohlcv(pool_address: str, timeframe: str, aggregate: int, limit: int = 100) -> pd.DataFrame:
    clean_addr = pool_address.split("_")[-1] if "_" in pool_address else pool_address
    data = api_get(f"networks/{NETWORK}/pools/{clean_addr}/ohlcv/{timeframe}", params={"aggregate": aggregate, "limit": limit})
    if not data or "data" not in data:
        return pd.DataFrame()
    ohlcv_list = ((data["data"].get("attributes") or {}).get("ohlcv_list")) or []
    if not ohlcv_list:
        return pd.DataFrame()

    df = pd.DataFrame(ohlcv_list, columns=["ts_epoch", "open", "high", "low", "close", "volume"])
    for col in ("ts_epoch", "open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["ts_epoch", "open", "high", "low", "close"]).copy()
    df["ts_epoch"] = df["ts_epoch"].astype("int64")
    df["timestamp"] = pd.to_datetime(df["ts_epoch"], unit="s", utc=True)
    return df.sort_values("ts_epoch").drop_duplicates("ts_epoch", keep="last").reset_index(drop=True)


def update_ohlcv_incremental(
    pool_address: str,
    timeframe: str,
    aggregate: int,
    cached_df: Optional[pd.DataFrame],
) -> pd.DataFrame:
    if cached_df is None or cached_df.empty:
        return fetch_ohlcv(pool_address, timeframe, aggregate, limit=100)
    recent_df = fetch_ohlcv(pool_address, timeframe, aggregate, limit=5)
    if recent_df.empty:
        return cached_df.tail(300).reset_index(drop=True)
    merged = pd.concat([cached_df, recent_df], ignore_index=True)
    return merged.sort_values("ts_epoch").drop_duplicates("ts_epoch", keep="last").tail(300).reset_index(drop=True)


def calculate_indicators(df: pd.DataFrame, current_market_cap: Optional[float] = None) -> Optional[pd.DataFrame]:
    """
    Point 10: If filtered coin has fewer than 35 candles, skip indicator calculation
    and return None so the trade is left alone cleanly.
    """
    if df is None or df.empty or len(df) < MIN_CANDLES_FOR_INDICATORS:
        return None

    out = df.copy().reset_index(drop=True)
    latest_close = float(out["close"].iloc[-1])
    if current_market_cap and current_market_cap > 0 and latest_close > 0:
        scale = current_market_cap / latest_close
        series = out["close"] * scale
        high_series = out["high"] * scale
        low_series = out["low"] * scale
    else:
        series = out["close"]
        high_series = out["high"]
        low_series = out["low"]

    ema_fast = series.ewm(span=8, adjust=False).mean()
    ema_slow = series.ewm(span=17, adjust=False).mean()
    out["macd_line"] = ema_fast - ema_slow
    out["macd_signal"] = out["macd_line"].ewm(span=9, adjust=False).mean()
    out["histogram"] = out["macd_line"] - out["macd_signal"]

    delta = series.diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, np.nan)
    out["rsi"] = 100 - (100 / (1 + rs))

    period = 10
    multiplier = 3
    hl2 = (high_series + low_series) / 2.0
    tr = pd.concat(
        [
            high_series - low_series,
            (high_series - series.shift(1)).abs(),
            (low_series - series.shift(1)).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr = pd.Series(np.nan, index=out.index, dtype="float64")
    atr.iloc[period - 1] = tr.iloc[:period].mean()
    alpha = 1.0 / period
    for i in range(period, len(out)):
        atr.iloc[i] = alpha * tr.iloc[i] + (1.0 - alpha) * atr.iloc[i - 1]

    basic_upper = (hl2 + multiplier * atr).tolist()
    basic_lower = (hl2 - multiplier * atr).tolist()
    closes = series.tolist()
    n = len(out)

    final_upper = [np.nan] * n
    final_lower = [np.nan] * n
    st_dir = [False] * n
    st_values = [np.nan] * n

    start_idx = period - 1
    final_upper[start_idx] = basic_upper[start_idx]
    final_lower[start_idx] = basic_lower[start_idx]
    st_dir[start_idx] = bool(closes[start_idx] > basic_upper[start_idx])
    st_values[start_idx] = final_lower[start_idx] if st_dir[start_idx] else final_upper[start_idx]

    for i in range(start_idx + 1, n):
        if basic_upper[i] < final_upper[i - 1] or closes[i - 1] > final_upper[i - 1]:
            final_upper[i] = basic_upper[i]
        else:
            final_upper[i] = final_upper[i - 1]

        if basic_lower[i] > final_lower[i - 1] or closes[i - 1] < final_lower[i - 1]:
            final_lower[i] = basic_lower[i]
        else:
            final_lower[i] = final_lower[i - 1]

        if st_dir[i - 1]:
            st_dir[i] = False if closes[i] < final_lower[i] else True
        else:
            st_dir[i] = True if closes[i] > final_upper[i] else False

        st_values[i] = final_lower[i] if st_dir[i] else final_upper[i]

    out["supertrend"] = st_values
    out["supertrend_dir"] = st_dir
    return out


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


# --- MAIN LOOP (SUPPORTS UP TO 2 ACTIVE CROSSOVERS, 50% CAPITAL EACH, >= 35 CANDLES) ---

def main() -> None:
    print(f"[{convert_to_ist(datetime.now(timezone.utc))}] Starting bot...")
    trader = JupiterTrader()
    open_positions, closed_trades = load_bot_state()

    candidate_pools: List[Dict[str, Any]] = []
    filtered_pools: List[Dict[str, Any]] = []
    ohlcv_cache: Dict[str, pd.DataFrame] = {}
    last_pool_fetch = 0.0

    while True:
        now_ts = time.time()
        if not candidate_pools or (now_ts - last_pool_fetch) >= POOL_FETCH_INTERVAL:
            candidate_pools = fetch_candidate_pools()
            filtered_pools = filter_pools(candidate_pools, relax_filters=False)
            if not filtered_pools:
                filtered_pools = filter_pools(candidate_pools, relax_filters=True)
            last_pool_fetch = now_ts

        monitored: Dict[str, Dict[str, Any]] = {p["pool_address"]: p for p in filtered_pools}
        for p_addr, pos in open_positions.items():
            if p_addr not in monitored:
                monitored[p_addr] = {
                    "pool_address": p_addr,
                    "pool_name": pos.get("Pool Name", p_addr),
                    "token_address": pos.get("Token Address", ""),
                    "age_hours": pos.get("Age Hours", 4.0),
                    "market_cap": 0.0,
                }

        active_table_rows: List[Dict[str, Any]] = []
        latest_prices: Dict[str, Decimal] = {}

        for p_addr, item in monitored.items():
            pool_name = item["pool_name"]
            token_addr = item.get("token_address", "")
            age = float(item.get("age_hours", 4.0))
            tf, agg = get_candlestick_timeframe(age)
            cache_key = f"{p_addr}_{agg}{tf[0]}"

            df_raw = update_ohlcv_incremental(p_addr, tf, agg, ohlcv_cache.get(cache_key))
            ohlcv_cache[cache_key] = df_raw

            # Point 10: leave trade alone if fewer than 35 candles
            if len(df_raw) < MIN_CANDLES_FOR_INDICATORS:
                print(f"[!] Skipping {pool_name}: only {len(df_raw)} candles (< {MIN_CANDLES_FOR_INDICATORS}). Trade left untouched.")
                continue

            df = calculate_indicators(df_raw, current_market_cap=item.get("market_cap"))
            if df is None or len(df) < MIN_CANDLES_FOR_INDICATORS:
                continue

            latest_prices[p_addr] = d(df["close"].iloc[-1])
            start_idx = max(10, 20)

            for i in range(start_idx, len(df)):
                prev_prev = df.iloc[i - 2]
                prev = df.iloc[i - 1]
                curr = df.iloc[i]

                is_pos = check_positive_crossover(curr, prev)
                is_neg = check_negative_crossover(curr, [prev_prev.to_dict(), prev.to_dict()])

                px = d(curr["close"])
                ts_ist = convert_to_ist(curr["timestamp"])

                if p_addr not in open_positions and is_pos:
                    alloc_sol = trader.calc_allocatable_sol(open_positions)
                    if alloc_sol <= Decimal("0"):
                        # Max 2 coins (50% each) reached or no spendable SOL left (stays idle)
                        continue
                    try:
                        order_res = trader.buy_entry(
                            token_mint=token_addr,
                            alloc_sol=alloc_sol,
                            entry_price_usd=px,
                        )
                    except Exception as exc:
                        print(f"[!] BUY_ENTRY failed for {pool_name}: {exc}")
                        continue

                    open_positions[p_addr] = {
                        "Pool Name": pool_name,
                        "Pool Address": p_addr,
                        "Token Address": token_addr,
                        "Age Hours": age,
                        "Entry (IST)": ts_ist,
                        "Entry Price": str(px),
                        "Allocated SOL": str(alloc_sol),
                        "Tokens Raw": int(order_res.get("tokens_raw") or 1),
                        "Entry Tx": order_res.get("tx_sig", ""),
                    }
                    save_bot_state(open_positions, closed_trades)
                    print(f"[BUY_ENTRY] {pool_name} | Alloc: {alloc_sol} SOL @ {px} | Tx: {open_positions[p_addr]['Entry Tx']}")

                elif p_addr in open_positions and is_neg:
                    pos = open_positions.pop(p_addr)
                    entry_px = d(pos.get("Entry Price"), str(px))
                    alloc_sol = d(pos.get("Allocated SOL"), "0")
                    pnl_pct = (((px - entry_px) / entry_px) * Decimal("100")) if entry_px > 0 else Decimal("0")

                    try:
                        exit_res = trader.sell_exit(
                            token_mint=pos.get("Token Address") or token_addr,
                            tokens_raw=int(pos.get("Tokens Raw") or 1),
                            alloc_sol=alloc_sol,
                            pnl_pct=pnl_pct,
                        )
                        exit_tx = exit_res.get("tx_sig", "")
                    except Exception as exc:
                        print(f"[!] SELL_EXIT failed for {pool_name}: {exc}")
                        exit_tx = "SELL_FAILED"

                    closed_trades.append({
                        "Pool Name": pos.get("Pool Name", pool_name),
                        "Entry (IST)": pos.get("Entry (IST)", ""),
                        "Exit (IST)": ts_ist,
                        "Allocated SOL": str(alloc_sol),
                        "PnL (%)": f"{pnl_pct.quantize(Decimal('0.01')):+.2f}%",
                        "Entry Tx": pos.get("Entry Tx", ""),
                        "Exit Tx": exit_tx,
                    })
                    save_bot_state(open_positions, closed_trades)
                    print(f"[SELL_EXIT] {pool_name} @ {px} | PnL: {pnl_pct:+.2f}% | Tx: {exit_tx}")

            if p_addr in open_positions:
                pos = open_positions[p_addr]
                entry_px = d(pos.get("Entry Price"), str(df["close"].iloc[-1]))
                matches = df.index[df["timestamp"].apply(convert_to_ist) == pos.get("Entry (IST)")].tolist()
                entry_idx = matches[-1] if matches else (len(df) - 1)
                for _, row in df.iloc[entry_idx:].iterrows():
                    c_px = d(row["close"])
                    live_pnl = (((c_px - entry_px) / entry_px) * Decimal("100")) if entry_px > 0 else Decimal("0")
                    active_table_rows.append({
                        "Pool Name": pool_name,
                        "Timestamp (IST)": convert_to_ist(row["timestamp"]),
                        "Close": f"{c_px:.8f}",
                        "MACD": f"{float(row['macd_line']):.6f}",
                        "Signal": f"{float(row['macd_signal']):.6f}",
                        "Hist": f"{float(row['histogram']):.6f}",
                        "Supertrend": f"{float(row['supertrend']):.8f} ({'BULL' if row['supertrend_dir'] else 'BEAR'})",
                        "RSI": f"{float(row['rsi']):.1f}",
                        "Alloc SOL": pos.get("Allocated SOL", "0"),
                        "Live PnL (%)": f"{live_pnl.quantize(Decimal('0.01')):+.2f}%",
                    })

        print("\n--- OPEN POSITIONS LOG ---")
        if open_positions:
            open_rows = []
            for p_addr, pos in open_positions.items():
                e_px = d(pos.get("Entry Price"), "0")
                m_px = latest_prices.get(p_addr, e_px)
                u_pnl = (((m_px - e_px) / e_px) * Decimal("100")) if e_px > 0 else Decimal("0")
                open_rows.append({
                    "Pool Name": pos.get("Pool Name", p_addr),
                    "Entry (IST)": pos.get("Entry (IST)", ""),
                    "Alloc SOL": pos.get("Allocated SOL", "0"),
                    "Entry Price": f"{e_px:.8f}",
                    "Mark Price": f"{m_px:.8f}",
                    "Unrealized PnL (%)": f"{u_pnl.quantize(Decimal('0.01')):+.2f}%",
                    "Entry Tx": pos.get("Entry Tx", ""),
                })
            print(pd.DataFrame(open_rows).to_string(index=False))
        else:
            print("No open positions.")

        print("\n--- TABLE 1: HISTORICAL COMPLETED TRADES ---")
        if closed_trades:
            print(pd.DataFrame(closed_trades).to_string(index=False))
        else:
            print("No completed trades yet.")

        print("\n--- TABLE 2: CURRENT ACTIVE POSITIVE CROSSOVERS ---")
        if active_table_rows:
            print(pd.DataFrame(active_table_rows).to_string(index=False))
        else:
            print("No active positive crossovers.")

        time.sleep(INDICATOR_CHECK_INTERVAL)


if __name__ == "__main__":
    main()
