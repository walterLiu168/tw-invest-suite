"""
FinMind batch fetcher — sponsor tier (6,000 req/hr).

Datasets used:
  TaiwanStockInfo            — company name (fallback)
  TaiwanStockPER             — P/E, P/B, dividend yield (1d cache)
  TaiwanStockDividend        — dividend history (30d cache)
  TaiwanStockFinancialStatements — quarterly P&L (30d cache)
  TaiwanStockMonthRevenue    — monthly revenue + YoY (7d cache)
  TaiwanStockNews            — news with source URL (4h/12h cache)

Rate strategy: 100 req/min (sponsor), enforced by simple token-bucket sleep.
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))
import finmind_client as fm
import cache_manager as cm


# Rate limiter: 60 req/min (safer, 3600/hr) to avoid FinMind IP ban.
# Sponsor tier is 6000/hr, but anti-abuse kicks in if we go too fast.
# Use threading.Lock so multiple workers share the rate limit correctly.
import threading
MIN_INTERVAL = 1.05  # seconds between requests = 57/min = 3420/hr (safe)
_last_call = [0.0]
_rate_lock = threading.Lock()


def _rate_limit():
    """Sleep to enforce safe rate (60 req/min) across all threads."""
    with _rate_lock:
        elapsed = time.time() - _last_call[0]
        if elapsed < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - elapsed)
        _last_call[0] = time.time()


def _call(dataset: str, ticker: str, start_date: str = "", end_date: str = "",
          use_data_id: bool = False) -> List[Dict]:
    _rate_limit()
    try:
        if use_data_id:
            return fm.query(dataset, data_id=ticker, start_date=start_date, end_date=end_date)
        return fm.query(dataset, stock_id=ticker, start_date=start_date, end_date=end_date)
    except Exception as e:
        # Log but don't crash — caller decides fallback
        return [{"_error": str(e), "_dataset": dataset}]


def fetch_pe(ticker: str) -> Optional[Dict]:
    """P/E + P/B + dividend_yield, last 30 days. Cache 1d."""
    cached = cm.get_fresh(ticker, "finmind_pe")
    if cached:
        return cached["data"]
    rows = _call("TaiwanStockPER", ticker,
                 start_date=(datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"))
    if rows and not any("_error" in r for r in rows):
        latest = rows[-1] if rows else {}
        cm.put(ticker, "finmind_pe", latest)
        return latest
    return None


def fetch_dividend(ticker: str) -> List[Dict]:
    """Dividend history (3y). Cache 30d."""
    cached = cm.get_fresh(ticker, "finmind_div")
    if cached:
        return cached["data"]
    rows = _call("TaiwanStockDividend", ticker,
                 start_date=(datetime.now() - timedelta(days=365 * 3)).strftime("%Y-%m-%d"))
    if rows and not any("_error" in r for r in rows):
        cm.put(ticker, "finmind_div", rows)
        return rows
    return []


def fetch_financials(ticker: str) -> List[Dict]:
    """Quarterly P&L (2y). Cache 30d."""
    cached = cm.get_fresh(ticker, "finmind_fin")
    if cached:
        return cached["data"]
    rows = _call("TaiwanStockFinancialStatements", ticker,
                 start_date=(datetime.now() - timedelta(days=365 * 2)).strftime("%Y-%m-%d"))
    if rows and not any("_error" in r for r in rows):
        cm.put(ticker, "finmind_fin", rows)
        return rows
    return []


def fetch_month_revenue(ticker: str) -> List[Dict]:
    """Monthly revenue (2y, for YoY). Cache 7d."""
    cached = cm.get_fresh(ticker, "finmind_month")
    if cached:
        return cached["data"]
    rows = _call("TaiwanStockMonthRevenue", ticker,
                 start_date=(datetime.now() - timedelta(days=365 * 2)).strftime("%Y-%m-%d"))
    if rows and not any("_error" in r for r in rows):
        # Compute YoY
        for r in rows:
            try:
                y = int(r["revenue_year"]); m = int(r["revenue_month"])
                prior_key = f"{y - 1}-{m:02d}"
                # find prior year same month
                for r2 in rows:
                    if (int(r2["revenue_year"]) == y - 1
                            and int(r2["revenue_month"]) == m):
                        prior = float(r2["revenue"])
                        if prior > 0:
                            r["yoy_pct"] = round((float(r["revenue"]) / prior - 1) * 100, 2)
                        break
            except (KeyError, ValueError):
                pass
        cm.put(ticker, "finmind_month", rows)
        return rows
    return []


def fetch_news(ticker: str, tier: str = "all") -> List[Dict]:
    """News (7d). tier='watchlist' (4h cache) or 'all' (12h cache)."""
    key = "finmind_news_watchlist" if tier == "watchlist" else "finmind_news_all"
    cached = cm.get_fresh(ticker, key)
    if cached:
        return cached["data"]
    rows = _call("TaiwanStockNews", ticker,
                 start_date=(datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d"))
    if rows and not any("_error" in r for r in rows):
        cm.put(ticker, key, rows)
        return rows
    return []


# ---- Batch runners (parallel) ----

def _fetch_one(ticker: str, fn_name: str) -> Tuple[str, str, any]:
    """Wrapper for parallel execution."""
    fn = {"pe": fetch_pe, "div": fetch_dividend, "fin": fetch_financials,
          "month": fetch_month_revenue, "news_watchlist": lambda t: fetch_news(t, "watchlist"),
          "news_all": lambda t: fetch_news(t, "all")}.get(fn_name)
    if not fn:
        return ticker, fn_name, None
    try:
        return ticker, fn_name, fn(ticker)
    except Exception as e:
        return ticker, fn_name, {"_error": str(e)}


def batch_fetch(tickers: List[str], fn_names: List[str], workers: int = 4) -> Dict[Tuple[str, str], Any]:
    """Fetch multiple data types for many tickers in parallel.

    Note: 4 workers at 0.65s interval = ~6.2 req/sec = 372/min.
    That's above FinMind 100/min limit when 4 workers each call sequentially.
    We rely on _rate_limit to keep total ≤ 100/min. So workers=2 is safer.
    Returns: {(ticker, fn_name): data}
    """
    results: Dict[Tuple[str, str], Any] = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_fetch_one, t, fn) for t in tickers for fn in fn_names]
        for fut in as_completed(futs):
            try:
                t, fn, data = fut.result()
                results[(t, fn)] = data
            except Exception as e:
                pass
    return results


if __name__ == "__main__":
    import sys
    ticker = sys.argv[1] if len(sys.argv) > 1 else "2330"
    print(f"=== FinMind batch test: {ticker} ===")
    for name, fn in [("pe", fetch_pe), ("div", fetch_dividend),
                     ("fin", fetch_financials), ("month", fetch_month_revenue),
                     ("news", lambda: fetch_news(ticker, "watchlist"))]:
        t0 = time.time()
        data = fn(ticker) if name != "news" else fn()
        print(f"  {name:6s}: {len(data) if isinstance(data, list) else (1 if data else 0)} rows, "
              f"{time.time() - t0:.2f}s")
