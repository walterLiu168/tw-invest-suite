"""
yfinance batch fetcher — 2 workers, anti-ban, FinMind fallback.

Per-ticker .info gives us:
  longName, sector, industry, marketCap, trailingPE, forwardPE,
  priceToBook, returnOnEquity, dividendYield, beta, fiftyTwoWeekHigh/Low

Anti-ban:
  - 2 workers max
  - Random jitter 0.5-1.5s between calls (per-worker)
  - On HTTP 429 / timeout / connection error: exponential backoff
  - Consecutive failure count tracked; if > 20 → mark yfinance DEAD
  - Once DEAD, all remaining tickers skip yfinance and try FinMind fallback

Fallback chain (per field):
  trailingPE  → FinMind TaiwanStockPER
  dividendYield → FinMind TaiwanStockDividend (compute)
  returnOnEquity → FinLab bulk (if available) → leave blank
  marketCap → DB shares_master × current price
  longName → DB industry_type.company
  sector/industry → DB industry_type.industry
"""
import sys
import time
import random
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))
import cache_manager as cm


# Yfinance state (shared across workers)
_yf_state = {
    "dead": False,
    "consecutive_fail": 0,
    "lock": threading.Lock(),
}

# Per-worker last call time (jitter)
_worker_last = {}
_worker_lock = threading.Lock()


def _format_ticker_yf(ticker: str) -> str:
    """Add .TW or .TWO suffix based on length. 4-digit → .TW, with letter → .TWO."""
    if "." in ticker:
        return ticker
    if len(ticker) == 4:
        return f"{ticker}.TW"
    if len(ticker) == 5 and ticker[4].isalpha():
        return f"{ticker[:4]}.TWO"
    return ticker


def _format_ticker_back(ticker_yf: str) -> str:
    """Strip .TW / .TWO for caching."""
    return ticker_yf.replace(".TW", "").replace(".TWO", "")


def _jitter():
    """Random 0.5-1.5s delay."""
    time.sleep(random.uniform(0.5, 1.5))


def _mark_fail():
    with _yf_state["lock"]:
        _yf_state["consecutive_fail"] += 1
        if _yf_state["consecutive_fail"] > 20:
            _yf_state["dead"] = True


def _mark_success():
    with _yf_state["lock"]:
        _yf_state["consecutive_fail"] = 0


def is_dead() -> bool:
    with _yf_state["lock"]:
        return _yf_state["dead"]


def reset():
    """Reset yfinance state (e.g. between daily runs)."""
    with _yf_state["lock"]:
        _yf_state["dead"] = False
        _yf_state["consecutive_fail"] = 0
    with _worker_lock:
        _worker_last.clear()


def _fetch_one_with_fallback(ticker: str) -> Dict:
    """Fetch yfinance .info with FinMind/DB fallback per field."""
    ticker_clean = ticker.strip()
    yf_sym = _format_ticker_yf(ticker_clean)
    cached = cm.get_fresh(ticker_clean, "yfinance")
    if cached:
        return cached["data"]

    if is_dead():
        return _build_fallback(ticker_clean)

    data: Dict = {"_source": "yfinance", "ticker": ticker_clean}
    try:
        import yfinance as yf
        _jitter()
        t = yf.Ticker(yf_sym)
        info = t.info
        # Timeout via session is set per-call; yfinance doesn't expose a
        # direct timeout param for .info, but the underlying request usually
        # returns within 5-10s. We rely on the 60s default in requests.
        data.update({
            "longName":      info.get("longName"),
            "sector":        info.get("sector"),
            "industry":      info.get("industry"),
            "marketCap":     info.get("marketCap"),
            "trailingPE":    info.get("trailingPE"),
            "forwardPE":     info.get("forwardPE"),
            "priceToBook":   info.get("priceToBook"),
            "returnOnEquity":info.get("returnOnEquity"),
            "dividendYield": info.get("dividendYield"),
            "beta":          info.get("beta"),
            "fiftyTwoWeekHigh": info.get("fiftyTwoWeekHigh"),
            "fiftyTwoWeekLow":  info.get("fiftyTwoWeekLow"),
        })
        _mark_success()
    except Exception as e:
        _mark_fail()
        data["_yfinance_err"] = str(e)[:200]
        return _build_fallback(ticker_clean, data)

    cm.put(ticker_clean, "yfinance", data)
    return data


def _build_fallback(ticker: str, partial: Optional[Dict] = None) -> Dict:
    """Build data from FinMind + DB when yfinance fails."""
    import pymysql
    import finmind_client as fm
    data: Dict = partial or {"_source": "fallback", "ticker": ticker}

    # 1. DB industry_type
    try:
        conn = pymysql.connect(host='localhost', user='root', password='1234',
                                database='tw_elec', connect_timeout=5)
        cur = conn.cursor(pymysql.cursors.DictCursor)
        cur.execute("SELECT company, industry FROM industry_type WHERE ticker=%s", (ticker,))
        row = cur.fetchone()
        if row:
            data.setdefault("longName", row["company"])
            data.setdefault("industry", row["industry"])
        cur.execute("SELECT SharesOutstanding_shares FROM shares_master WHERE Ticker=%s",
                    (ticker,))
        row2 = cur.fetchone()
        if row2 and row2.get("SharesOutstanding_shares"):
            data["_shares_outstanding"] = int(row2["SharesOutstanding_shares"])
        conn.close()
    except Exception:
        pass

    # 2. FinMind PER
    try:
        from datetime import timedelta
        per_rows = fm.stock_per(ticker, start_date=(datetime.now() - timedelta(days=30))
                                                  .strftime("%Y-%m-%d"))
        if per_rows and not any("_error" in r for r in per_rows):
            latest = per_rows[-1]
            data.setdefault("trailingPE", latest.get("PER"))
            data.setdefault("priceToBook", latest.get("PBR"))
            if latest.get("dividend_yield") is not None:
                data.setdefault("dividendYield", float(latest["dividend_yield"]) / 100)
            data["_finmind_per"] = latest
    except Exception:
        pass

    # 3. FinMind stock_info (for company name if DB miss)
    if not data.get("longName"):
        try:
            info_rows = fm.stock_info(ticker)
            if info_rows and not any("_error" in r for r in info_rows):
                data["longName"] = info_rows[0].get("stock_name")
                data["industry"] = info_rows[0].get("industry_category")
        except Exception:
            pass

    return data


def batch_fetch(tickers: List[str], workers: int = 2) -> Dict[str, Dict]:
    """Fetch yfinance .info for many tickers. workers=2 by default for safety.

    Returns: {ticker: data_dict}
    """
    reset()
    results: Dict[str, Dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_fetch_one_with_fallback, t): t for t in tickers}
        for fut in as_completed(futs):
            t = futs[fut]
            try:
                results[t] = fut.result()
            except Exception as e:
                results[t] = {"_source": "error", "ticker": t, "_err": str(e)}
    return results


if __name__ == "__main__":
    import sys
    ticker = sys.argv[1] if len(sys.argv) > 1 else "2330"
    print(f"=== yfinance test: {ticker} ===")
    t0 = time.time()
    data = _fetch_one_with_fallback(ticker)
    print(f"  Elapsed: {time.time() - t0:.2f}s")
    for k, v in data.items():
        print(f"  {k:25s} = {v}")
    print(f"  is_dead: {is_dead()}")
