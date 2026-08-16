"""Yfinance-only batch — runs 1,943 tickers to populate yfinance cache.

Used to fill yfinance cache when FinMind is rate-limited or banned.
Safe rate: 1 worker, 1.0s/call. ~33 min for 1,943.
"""
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pymysql
import yfinance_batch as yfb
import cache_manager as cm


def get_all_tickers() -> list:
    conn = pymysql.connect(host='localhost', user='root', password='1234',
                            database='tw_elec', connect_timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT ticker FROM industry_type "
                "WHERE ticker REGEXP '^[0-9]{4}$|^[0-9]{4}[A-Z]$'")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


def main():
    tickers = get_all_tickers()
    print(f"[{datetime.now():%H:%M:%S}] Yfinance batch: {len(tickers)} tickers")
    ok, fail, skipped = 0, 0, 0
    t0 = time.time()
    for i, t in enumerate(tickers, 1):
        if cm.get_fresh(t, "yfinance"):
            skipped += 1
            continue
        try:
            data = yfb._fetch_one_with_fallback(t)
            if data.get("_source") in ("yfinance", "fallback"):
                ok += 1
            else:
                fail += 1
        except Exception as e:
            fail += 1
        if i % 50 == 0 or i == len(tickers):
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(tickers) - i) / rate if rate > 0 else 0
            print(f"  [{i:>4}/{len(tickers)}] {elapsed:>5.0f}s "
                  f"({rate:.2f}/s, ETA {eta/60:.1f}min) "
                  f"ok={ok} fail={fail} skip={skipped}", flush=True)
    print(f"[{datetime.now():%H:%M:%S}] Done: ok={ok} fail={fail} skip={skipped}")


if __name__ == "__main__":
    main()
