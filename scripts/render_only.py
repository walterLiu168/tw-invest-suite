"""Render-only mode — uses cache, no API calls.

Use this AFTER cache has been populated by batch_yfinance_only,
batch_finmind_only, and batch_finmind_news.

Renders 1,943 HTML files from cached data.
"""
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pymysql
import cross_source_runner as csr
import render_ticker_full as rtf


HTML_DIR = Path(r"C:\Groove-Lab\analyze")


def get_all_tickers():
    conn = pymysql.connect(host='localhost', user='root', password='1234',
                            database='tw_elec', connect_timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT ticker FROM industry_type "
                "WHERE ticker REGEXP '^[0-9]{4}$|^[0-9]{4}[A-Z]$'")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


def get_watchlist():
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
    parser.add_argument("--no-news", action="store_true",
                        help="Skip FinMind news (fast, no FinMind API call)")
    parser.add_argument("--no-yfinance", action="store_true",
                        help="Skip yfinance (DB + FinMind only)")
    args = parser.parse_args()

    tickers = get_all_tickers()
    watchlist = get_watchlist()
    print(f"[{datetime.now():%H:%M:%S}] Render-only: {len(tickers)} tickers "
          f"({len(watchlist)} watchlist with 4h news) "
          f"no_news={args.no_news} no_yfinance={args.no_yfinance}")

    # Stage A: assemble data from cache (fast, no API if cache hit)
    t0 = time.time()
    all_data = {}
    for i, t in enumerate(tickers, 1):
        tier = "watchlist" if t in watchlist else "all"
        try:
            all_data[t] = csr.assemble(t, news_tier=tier,
                                         use_yfinance=not args.no_yfinance,
                                         fetch_news=not args.no_news)
        except Exception as e:
            all_data[t] = {"ticker": t, "_err": str(e)}
        if i % 200 == 0 or i == len(tickers):
            print(f"  assemble [{i}/{len(tickers)}] {time.time()-t0:.0f}s", flush=True)
    print(f"  Stage A (assemble): {time.time()-t0:.0f}s")

    # Stage C: render HTML in parallel
    t0 = time.time()
    ok, fail = 0, 0

    def _render_one(t):
        try:
            rtf.render_ticker_tabbed(t, all_data[t], output_dir=str(HTML_DIR))
            return t, True
        except Exception as e:
            return t, str(e)

    with ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(_render_one, t): t for t in all_data}
        for fut in as_completed(futs):
            t, result = fut.result()
            if result is True:
                ok += 1
            else:
                fail += 1
            if (ok + fail) % 200 == 0:
                print(f"  render [{ok+fail}/{len(all_data)}] {time.time()-t0:.0f}s "
                      f"ok={ok} fail={fail}", flush=True)
    print(f"  Stage C (render): {time.time()-t0:.0f}s — {ok} ok, {fail} fail")

    # Stage D: index.html
    print(f"[{datetime.now():%H:%M:%S}] Building index.html...")
    from daily_full_tickers import _build_index_html
    _build_index_html(tickers, str(HTML_DIR))

    print(f"[{datetime.now():%H:%M:%S}] Done. {ok} HTML files in {HTML_DIR}")


if __name__ == "__main__":
    main()
