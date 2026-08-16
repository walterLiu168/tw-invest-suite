"""FinMind-only batch — runs 1,943 tickers to populate FinMind cache.

Safe rate: 1 worker, 1.05s/call (57/min = 3420/hr, well under 6000/hr sponsor).

Fetches 4 datasets per ticker:
  - TaiwanStockPER (1d cache)
  - TaiwanStockMonthRevenue (7d cache)
  - TaiwanStockDividend (30d cache)
  - TaiwanStockFinancialStatements (30d cache)

News is fetched separately (12h cache, see batch_finmind_news.py).

Total: 4 × 1962 = 7848 calls / 57/min = 138 min = 2.3 hours.
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


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--fail-threshold", type=int, default=30,
                        help="Abort early if any dataset has N consecutive cache-miss fails (ban detection)")
    args = parser.parse_args()

    tickers = get_all_tickers()
    print(f"[{datetime.now():%H:%M:%S}] FinMind batch: {len(tickers)} tickers × 4 datasets "
          f"fail_threshold={args.fail_threshold}")
    fetches = [
        ("pe",    "finmind_pe",   fmb.fetch_pe),
        ("month", "finmind_month", fmb.fetch_month_revenue),
        ("div",   "finmind_div",  fmb.fetch_dividend),
        ("fin",   "finmind_fin",  fmb.fetch_financials),
    ]
    stats = {name: {"ok": 0, "skip": 0, "fail": 0, "consec_fail": 0} for name, _, _ in fetches}
    t0 = time.time()
    total_calls = 0
    aborted_datasets = set()
    for i, t in enumerate(tickers, 1):
        for name, cache_key, fn in fetches:
            if name in aborted_datasets:
                continue  # already aborted for this dataset, skip
            if cm.get_fresh(t, cache_key):
                stats[name]["skip"] += 1
                stats[name]["consec_fail"] = 0
                continue
            try:
                data = fn(t)
                if data and (not isinstance(data, list) or
                             (data and not any("_error" in r for r in (data if isinstance(data, list) else [data])))):
                    stats[name]["ok"] += 1
                    stats[name]["consec_fail"] = 0
                else:
                    stats[name]["fail"] += 1
                    stats[name]["consec_fail"] += 1
            except Exception as e:
                stats[name]["fail"] += 1
                stats[name]["consec_fail"] += 1
            total_calls += 1
            # Per-dataset fail-fast
            if stats[name]["consec_fail"] >= args.fail_threshold:
                print(f"  [!] ABORT dataset '{name}': {stats[name]['consec_fail']} consecutive fails — "
                      f"FinMind likely banned. Will skip rest of this dataset.", flush=True)
                aborted_datasets.add(name)
        # If all 4 datasets aborted, stop entirely
        if len(aborted_datasets) == len(fetches):
            print(f"  [!] All 4 FinMind datasets aborted at ticker {i}/{len(tickers)}. Stopping.", flush=True)
            break
        if i % 50 == 0 or i == len(tickers):
            elapsed = time.time() - t0
            rate = total_calls / elapsed if elapsed > 0 else 0
            remaining = max(0, len(tickers) - i) * (len(fetches) - len(aborted_datasets))
            eta = remaining / rate if rate > 0 else 0
            print(f"  [{i:>4}/{len(tickers)}] {elapsed:>5.0f}s "
                  f"({rate:.2f}/s, ETA {eta/60:.1f}min) "
                  f"calls={total_calls} aborted={list(aborted_datasets)} "
                  f"ok={ {k: v['ok'] for k, v in stats.items()} }",
                  flush=True)
    print(f"[{datetime.now():%H:%M:%S}] Done. Total: {total_calls} calls (aborted: {aborted_datasets or 'none'})")
    for k, v in stats.items():
        marker = " [ABORTED]" if k in aborted_datasets else ""
        print(f"  {k}{marker}: ok={v['ok']} skip={v['skip']} fail={v['fail']}")


if __name__ == "__main__":
    main()
