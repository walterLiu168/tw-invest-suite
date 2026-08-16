"""FinMind news batch — runs 1,943 tickers to populate news cache.

News has 12h cache for non-watchlist, 4h for watchlist.
Sponsor tier: 6000/hr = 100/min. Use 0.7s/call (85/min) for safety.

Total: 1962 calls / 85 = 23 min for first run.
"""
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pymysql
import finmind_batch as fmb
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


def get_watchlist() -> set:
    conn = pymysql.connect(host='localhost', user='root', password='1234',
                            database='tw_elec', connect_timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT ticker FROM market_screen_picks "
                "WHERE run_id = (SELECT MAX(id) FROM market_screen_runs)")
    rows = {r[0] for r in cur.fetchall()}
    conn.close()
    return rows


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail-threshold", type=int, default=20,
                        help="Abort early if first N consecutive fetches all fail (FinMind ban detection)")
    args = parser.parse_args()

    tickers = get_all_tickers()
    watchlist = get_watchlist()
    print(f"[{datetime.now():%H:%M:%S}] FinMind news batch: {len(tickers)} tickers "
          f"({len(watchlist)} watchlist with 4h, rest 12h) "
          f"fail_threshold={args.fail_threshold}")

    ok, skip, fail = 0, 0, 0
    consecutive_fail = 0  # for ban detection
    aborted = False
    t0 = time.time()
    for i, t in enumerate(tickers, 1):
        tier = "watchlist" if t in watchlist else "all"
        cache_key = "finmind_news_watchlist" if tier == "watchlist" else "finmind_news_all"
        if cm.get_fresh(t, cache_key):
            skip += 1
            consecutive_fail = 0  # reset on cache hit
            continue
        try:
            data = fmb.fetch_news(t, tier=tier)
            if data and not any("_error" in r for r in (data if isinstance(data, list) else [data])):
                ok += 1
                consecutive_fail = 0
            else:
                fail += 1
                consecutive_fail += 1
        except Exception as e:
            fail += 1
            consecutive_fail += 1
        # Fast-abort on FinMind ban (consecutive fails from cache-miss only)
        if consecutive_fail >= args.fail_threshold:
            print(f"  [!] ABORT: {consecutive_fail} consecutive cache-miss fails — "
                  f"FinMind likely rate-limited/banned. "
                  f"Skipping remaining {len(tickers) - i} tickers. "
                  f"Re-run tomorrow after ban lifts.", flush=True)
            aborted = True
            break
        if i % 50 == 0 or i == len(tickers):
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(tickers) - i) / rate if rate > 0 else 0
            print(f"  [{i:>4}/{len(tickers)}] {elapsed:>5.0f}s "
                  f"({rate:.2f}/s, ETA {eta/60:.1f}min) "
                  f"ok={ok} skip={skip} fail={fail}", flush=True)
    state = "ABORTED" if aborted else "Done"
    print(f"[{datetime.now():%H:%M:%S}] {state}: ok={ok} skip={skip} fail={fail}")


if __name__ == "__main__":
    main()
