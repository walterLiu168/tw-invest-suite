"""Versioned optional valuation-cache refresh used by the 22:30 Scheduler task."""
import logging
from contextlib import contextmanager
from datetime import date, datetime
import math
import os
from pathlib import Path
import time

import db_client as db
import yfinance_batch as yfb
import cache_manager as cache
import pipeline_state as ps


@contextmanager
def valuation_lock():
    import ctypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel.CreateMutexW(None, False, 'Global\\TwInvestSuiteValuation')
    if not handle:
        raise OSError('Cannot open valuation refresh mutex')
    acquired = False
    try:
        deadline = time.monotonic() + 54*60
        while time.monotonic() < deadline:
            result = kernel.WaitForSingleObject(ctypes.c_void_p(handle), 1000)
            if result in (0, 0x80):
                acquired = True
                break
            if result != 0x102:
                raise OSError('Valuation refresh mutex failed')
        if not acquired:
            raise TimeoutError('Another valuation refresh exceeded its deadline')
        yield
    finally:
        if acquired:
            kernel.ReleaseMutex(ctypes.c_void_p(handle))
        kernel.CloseHandle(ctypes.c_void_p(handle))


def cache_coverage(tickers, target_date):
    fresh = []
    missing = []
    for ticker in tickers:
        entry = cache.get_fresh(ticker, 'yfinance') or {}
        data = entry.get('data') or {}
        try:
            fetched = datetime.fromisoformat(entry.get('fetched_at',''))
            valid_time = date.fromisoformat(target_date) <= fetched.date() and fetched <= datetime.now()
        except ValueError:
            valid_time = False
        financial = [data.get(key) for key in ('marketCap','trailingPE','priceToBook','returnOnEquity')]
        usable = any(isinstance(value, (int,float)) and not isinstance(value,bool) and math.isfinite(value)
                     for value in financial)
        if (valid_time and usable and
                data.get('_source') == 'yfinance' and data.get('_symbol') == ticker + yfb._market_map.get(ticker,'?')):
            fresh.append(ticker)
        else:
            missing.append(ticker)
    return {'data_date':target_date,'expected_tickers':len(tickers),'fresh_tickers':len(fresh),'missing_tickers':missing}


def refresh(tickers, target_date):
    with valuation_lock():
        yfb.refresh_market_map()
        coverage = cache_coverage(tickers,target_date)
        if coverage['fresh_tickers'] < 1900:
            pending = coverage['missing_tickers']
            logging.info('Valuation refresh: %s pending/%s tickers, two workers',len(pending),len(tickers))
            results = yfb.batch_fetch(pending,workers=2,force=True)
            counts = {kind:sum(item.get('_source')==kind for item in results.values())
                      for kind in ('yfinance','fallback','error')}
            logging.info('Provider results %s; provider_dead=%s',counts,yfb.is_dead())
            coverage = cache_coverage(tickers,target_date)
        coverage.update(nightly_id=os.environ.get('TW_NIGHTLY_ID','manual'),checked_at=datetime.now().isoformat(),
                        status='ok' if coverage['fresh_tickers']>=1900 else 'failed')
        filename = 'finance_fetch.json' if os.environ.get('TW_NIGHTLY_ID') else 'finance_refresh_latest.json'
        ps.atomic_json(ps.RUNTIME/'_debug'/filename,coverage)
        logging.info('Actual verified cache coverage %s/%s; missing=%s',coverage['fresh_tickers'],len(tickers),len(coverage['missing_tickers']))
        return 0 if coverage['status']=='ok' else 2


def main():
    logs = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug")
    logs.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", handlers=[logging.FileHandler(logs / f"yfinance_{time.strftime('%Y%m%d_%H%M%S')}.log", encoding="utf-8"), logging.StreamHandler()])
    with db.get_cursor() as cursor:
        cursor.execute("SELECT ticker FROM industry_type WHERE ticker REGEXP '^[0-9]{4}$|^[0-9]{4}[A-Z]$' ORDER BY ticker")
        tickers = [row["ticker"] for row in cursor.fetchall()]
    if not tickers:
        raise ValueError("Empty valuation-refresh universe")
    from market_calendar import is_session
    if not is_session(date.today()):
        logging.info('Non-trading session: preserve periodic financial cache; skip downloads')
        return 0
    target_date = os.environ.get('TW_DATA_DATE') or date.today().isoformat()
    date.fromisoformat(target_date)
    return refresh(tickers,target_date)


if __name__ == "__main__":
    raise SystemExit(main())
