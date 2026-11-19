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
import db_client as db


# Yfinance state (shared across workers)
_yf_state = {
    "dead": False,
    "consecutive_fail": 0,
    "lock": threading.Lock(),
}

# Per-worker last call time (jitter)
_worker_last = {}
_worker_lock = threading.Lock()
_market_map = {}
_company_map = {}
_market_map_lock = threading.Lock()


# --- Listing venue resolution ---------------------------------------------
# FinMind's TaiwanStockInfo publishes exactly ONE complete listing snapshot,
# stamped with the current date, and keeps only the per-day diffs for earlier
# dates.  Measured 2026-11-20: one session carries 3358 rows, a past date
# carries one or two.  The snapshot lands roughly an hour after midnight, so
# the 00:00 certification catch-up always read an empty window and failed the
# whole valuation stage (ten failures between 2026-09-30 and 2026-11-20).
#
# A complete snapshot therefore carries thousands of rows while a diff day
# carries one or two, so MIN_LISTING_SNAPSHOT_ROWS separates "published" from
# "still being published" and from "diff only".
LISTING_WINDOW_DAYS = 7
MIN_LISTING_SNAPSHOT_ROWS = 1500
TWSE_LISTING_URL = 'https://openapi.twse.com.tw/v1/opendata/t187ap03_L'
TPEX_LISTING_URL = 'https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O'


def _listing_snapshot_from_provider():
    """Newest complete listing snapshot the provider currently exposes.

    Returns (rows, latest_day).  rows is empty when the provider exposes no
    complete snapshot yet — the daily snapshot is published about an hour
    after midnight, and before that only per-day diffs are visible.
    """
    import finmind_batch as fm
    from datetime import date, timedelta
    today = date.today()
    rows = fm._call('TaiwanStockInfo', '',
                    start_date=(today - timedelta(days=LISTING_WINDOW_DAYS)).isoformat(),
                    end_date=today.isoformat())
    if not rows or any('_error' in row for row in rows):
        return [], None
    per_day = {}
    for row in rows:
        try:
            day = date.fromisoformat(str(row.get('date', '')))
        except ValueError:
            continue
        if row.get('type') not in {'twse', 'tpex'}:
            continue
        per_day.setdefault(day, []).append(row)
    complete = [day for day, day_rows in per_day.items()
                if len(day_rows) >= MIN_LISTING_SNAPSHOT_ROWS]
    if not complete:
        return [], None
    latest = max(complete)
    return per_day[latest], latest


def _listing_snapshot_from_exchanges(today):
    """Listing venue straight from the exchanges' own open data.

    The exchanges publish on no snapshot schedule, so this keeps the 00:00
    catch-up alive while the provider's daily snapshot is still being built.
    The two open-data lists carry listed companies only; the provider adds
    the ETF/ETN codes on top of them.
    """
    import requests
    rows = []
    try:
        twse = requests.get(TWSE_LISTING_URL, timeout=30).json()
        tpex = requests.get(TPEX_LISTING_URL, timeout=30).json()
    except Exception as exc:
        raise RuntimeError(f'Exchange listing open data unavailable: {exc}') from exc
    for record in twse:
        code = str(record.get('公司代號', '')).strip()
        if code:
            rows.append({'stock_id': code, 'stock_name': str(record.get('公司名稱', '')).strip(),
                         'type': 'twse', 'date': today})
    for record in tpex:
        code = str(record.get('SecuritiesCompanyCode', '')).strip()
        if code:
            rows.append({'stock_id': code, 'stock_name': str(record.get('CompanyName', '')).strip(),
                         'type': 'tpex', 'date': today})
    return rows


def refresh_market_map(rows=None):
    """Resolve listing venue from fresh canonical provider metadata."""
    from datetime import date, timedelta
    today = date.today()
    window = today - timedelta(days=LISTING_WINDOW_DAYS)
    if rows is None:
        try:
            selected, latest = _listing_snapshot_from_provider()
        except Exception as exc:
            raise RuntimeError(f'Listing venue metadata unavailable: {exc}') from exc
        source = 'provider'
        if not selected:
            try:
                selected = _listing_snapshot_from_exchanges(today)
            except Exception as exc:
                raise RuntimeError('Listing venue metadata unavailable') from exc
            source = 'exchanges'
            latest = today
            if len(selected) < MIN_LISTING_SNAPSHOT_ROWS:
                raise RuntimeError('Listing venue metadata unavailable')
        valid = [(latest, row) for row in selected]
    else:
        source = 'injected'
        valid = []
        for row in rows:
            try:
                day = date.fromisoformat(str(row.get('date', '')))
            except ValueError:
                continue
            if window <= day <= today and row.get('type') in {'twse', 'tpex'}:
                valid.append((day, row))
        if not valid:
            raise RuntimeError('Listing venue metadata is stale or invalid')
        latest = max(day for day, _ in valid)
    if not valid:
        raise RuntimeError('Listing venue metadata unavailable')
    venues = {}
    for day, row in valid:
        if day == latest:
            venues.setdefault(str(row['stock_id']).strip(), set()).add(row['type'])
    if any(len(values) != 1 for values in venues.values()):
        raise ValueError('Conflicting current listing venues')
    mapped = {ticker: '.TW' if next(iter(values)) == 'twse' else '.TWO'
              for ticker, values in venues.items()}
    _market_map.clear()
    _market_map.update(mapped)
    _company_map.clear()
    _company_map.update({str(row['stock_id']).strip(): row.get('stock_name')
                         for day, row in valid if day == latest})
    return {'source': source, 'source_date': latest.isoformat(), 'mapped_tickers': len(mapped)}


def _format_ticker_yf(ticker: str) -> str:
    """Preserve the security code and use its verified listing venue."""
    if "." in ticker:
        return ticker
    if not _market_map:
        with _market_map_lock:
            if not _market_map:
                refresh_market_map()
    if ticker not in _market_map:
        raise ValueError(f'No current listed venue for {ticker}')
    return ticker + _market_map[ticker]


def _format_ticker_back(ticker_yf: str) -> str:
    """Strip .TW / .TWO for caching."""
    return ticker_yf.rsplit('.',1)[0] if ticker_yf.endswith(('.TW','.TWO')) else ticker_yf


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


def _fetch_one_with_fallback(ticker: str, force: bool = False) -> Dict:
    """Fetch yfinance .info with FinMind/DB fallback per field."""
    ticker_clean = ticker.strip()
    yf_sym = _format_ticker_yf(ticker_clean)
    cached = cm.get_fresh(ticker_clean, "yfinance")
    if cached and not force:
        return cached["data"]

    if is_dead():
        return _build_fallback(ticker_clean)

    data: Dict = {"_source": "yfinance", "ticker": ticker_clean}
    try:
        import yfinance as yf
        _jitter()
        t = yf.Ticker(yf_sym)
        info = t.info
        if not info or str(info.get('symbol', '')).upper() != yf_sym.upper():
            raise ValueError('Yahoo returned an empty or different security')
        data['_symbol'] = yf_sym
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
    raw_roe = data.get('returnOnEquity')
    import math
    roe = raw_roe if isinstance(raw_roe, (int,float)) and not isinstance(raw_roe,bool) and math.isfinite(raw_roe) else None
    cm.put(ticker_clean, 'yfinance_roe', {'returnOnEquity':roe,'_symbol':yf_sym,'_source':'yfinance'})
    return data


def _build_fallback(ticker: str, partial: Optional[Dict] = None) -> Dict:
    """Build data from FinMind + DB when yfinance fails."""
    import pymysql
    import finmind_client as fm
    data: Dict = partial or {"_source": "fallback", "ticker": ticker}
    data['_source'] = 'fallback'

    # 1. DB industry_type
    try:
        conn = db.connect(connect_timeout=5)
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
        # The market PER snapshot is maintained separately. Yahoo workers
        # must not start parallel FinMind downloads on an error burst.
        cached_per = cm.get_fresh(ticker, 'finmind_pe')
        per_rows = [cached_per['data']] if cached_per else []
        if per_rows and not any("_error" in r for r in per_rows):
            latest = per_rows[-1]
            data.setdefault("trailingPE", latest.get("PER"))
            data.setdefault("priceToBook", latest.get("PBR"))
            if latest.get("dividend_yield") is not None:
                data.setdefault("dividendYield", float(latest["dividend_yield"]) / 100)
            data["_finmind_per"] = latest
    except Exception:
        pass

    # 3. Already verified bulk metadata (no API calls from Yahoo workers).
    if not data.get("longName"):
        data['longName'] = _company_map.get(ticker)

    return data


def batch_fetch(tickers: List[str], workers: int = 2, force: bool = False) -> Dict[str, Dict]:
    """Fetch yfinance .info for many tickers. workers=2 by default for safety.

    Returns: {ticker: data_dict}
    """
    reset()
    refresh_market_map()
    results: Dict[str, Dict] = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_fetch_one_with_fallback, t, force=force): t for t in tickers}
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
