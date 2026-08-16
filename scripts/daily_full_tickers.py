"""
Daily full report — runs 1,943 tickers with cross-source data + skill analysis.

Pipeline:
  1. Load all tickers from DB (industry_type, 1,962 rows)
  2. Load watchlist (24 picks) from market_screen_picks
  3. Stage A: build data (cache-aware, parallel)
       - DB always
       - FinMind batch: 1,943 × (PE, div, fin, month) ≈ 1 hour
       - yfinance batch: 1,943 × .info ≈ 30-50 min (2 workers)
       - News tier: watchlist 4h, all 12h
  4. Stage B: cross-verify (logged in _debug/cross_verify.jsonl)
  5. Stage C: render HTML per ticker
  6. Stage D: build index.html (A-Z list + search)
  7. Stage E: publish to groovelab.dev + GitHub Pages
  8. Stage F: write run log

Run:
    python daily_full_tickers.py                  # all 1,943
    python daily_full_tickers.py --limit 50       # first 50 (smoke test)
    python daily_full_tickers.py --ticker 2330    # single ticker
    python daily_full_tickers.py --skip-render    # data only
"""
import sys
import time
import json
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
import pymysql
import cross_source_runner as csr
import yfinance_batch as yfb
import render_ticker_html as rth


HTML_DIR = Path(r"C:\Groove-Lab\analyze")
HTML_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug")


def get_all_tickers() -> List[str]:
    """Get all listed tickers (TWSE + TPEx) from DB industry_type."""
    conn = pymysql.connect(host='localhost', user='root', password='1234',
                            database='tw_elec', connect_timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT ticker FROM industry_type "
                "WHERE ticker REGEXP '^[0-9]{4}$|^[0-9]{4}[A-Z]$'")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


def get_watchlist() -> List[str]:
    """Get the 24 watchlist tickers."""
    conn = pymysql.connect(host='localhost', user='root', password='1234',
                            database='tw_elec', connect_timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT ticker FROM market_screen_picks "
                "WHERE run_id = (SELECT MAX(id) FROM market_screen_runs)")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


def _build_index_html(tickers: List[str], output_dir: str) -> None:
    """Build A-Z index.html of all ticker reports."""
    rows_html = []
    # Group by first digit
    conn = pymysql.connect(host='localhost', user='root', password='1234',
                            database='tw_elec', connect_timeout=5)
    cur = conn.cursor(pymysql.cursors.DictCursor)
    cur.execute("SELECT ticker, company, industry FROM industry_type "
                "WHERE ticker REGEXP '^[0-9]{4}$|^[0-9]{4}[A-Z]$'")
    info = {r["ticker"]: r for r in cur.fetchall()}
    conn.close()

    # Sort tickers naturally
    sorted_tickers = sorted(tickers, key=lambda t: (t.rstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
                                                      t))
    for t in sorted_tickers:
        info_t = info.get(t, {})
        name = info_t.get("company") or "—"
        industry = info_t.get("industry") or "—"
        rows_html.append(
            f'<tr><td><a href="{t}.html">{t}</a></td>'
            f'<td>{name}</td><td class="muted">{industry}</td></tr>'
        )

    table_html = "\n".join(rows_html)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head><meta charset="UTF-8">
<title>台股個股分析索引 · {len(tickers)} 檔</title>
<style>
body {{ font-family: -apple-system, "Microsoft JhengHei", system-ui, sans-serif;
       background: #0a0e1a; color: #e6ecf5; margin: 0; padding: 24px; }}
h1 {{ color: #5fb1ff; font-size: 1.6rem; }}
.topbar {{ display: flex; justify-content: space-between; align-items: center;
         margin-bottom: 20px; flex-wrap: wrap; gap: 12px; }}
.search-form {{ display: flex; gap: 6px; }}
.search-form input {{ background: #131b2e; color: #e6ecf5; border: 1px solid #1f2942;
                     border-radius: 6px; padding: 8px 12px; font-size: 1rem; width: 140px; }}
.search-form button {{ background: #5fb1ff; color: #000; border: none; border-radius: 6px;
                      padding: 8px 16px; font-size: 1rem; font-weight: 600; cursor: pointer; }}
table {{ width: 100%; border-collapse: separate; border-spacing: 0; font-size: 0.92rem; }}
th {{ background: rgba(95,177,255,0.15); color: #5fb1ff; text-align: left;
     padding: 8px 12px; position: sticky; top: 0; }}
td {{ padding: 6px 12px; border-bottom: 1px solid rgba(255,255,255,0.05); }}
tr:hover {{ background: rgba(95,177,255,0.05); }}
a {{ color: #5fb1ff; text-decoration: none; font-weight: 600; }}
a:hover {{ text-decoration: underline; }}
.muted {{ color: #8aa0c0; font-size: 0.85rem; }}
.meta {{ color: #8aa0c0; margin-bottom: 16px; }}
</style>
</head>
<body>
<div class="topbar">
  <h1>📊 台股個股分析索引</h1>
  <form class="search-form" action="https://groovelab.dev/analyze.html" method="get">
    <input name="ticker" placeholder="輸入股號" maxlength="6" required>
    <button type="submit">分析 →</button>
  </form>
</div>
<div class="meta">共 {len(tickers)} 檔 · 更新於 {now_str} · 資料源: yfinance + FinMind + DB</div>
<table>
<thead><tr><th>股號</th><th>公司</th><th>產業</th></tr></thead>
<tbody>{table_html}</tbody>
</table>
<footer style="color:#8aa0c0;text-align:center;margin-top:20px;font-size:0.85rem">
tw-invest-suite · cross-source full report
</footer>
</body></html>"""
    Path(output_dir, "index.html").write_text(html, encoding="utf-8")


def _assemble_one(t: str, watchlist_set: set, use_yfinance: bool = True) -> Dict:
    """Wrapper for parallel assemble."""
    tier = "watchlist" if t in watchlist_set else "all"
    try:
        data = csr.assemble(t, news_tier=tier, use_yfinance=use_yfinance)
        return t, data
    except Exception as e:
        return t, {"ticker": t, "_err": str(e)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0,
                        help="Process only first N tickers (smoke test)")
    parser.add_argument("--ticker", default="",
                        help="Process single ticker (smoke test)")
    parser.add_argument("--skip-render", action="store_true",
                        help="Skip HTML rendering (data collection only)")
    parser.add_argument("--workers", type=int, default=2,
                        help="Parallel workers for stage A (default 2 to avoid FinMind ban)")
    parser.add_argument("--no-yfinance", action="store_true",
                        help="Skip yfinance (DB + FinMind only, faster)")
    args = parser.parse_args()

    today = datetime.now().strftime("%Y%m%d")
    run_log = LOG_DIR / f"daily_run_{today}.log"
    run_log.parent.mkdir(parents=True, exist_ok=True)

    def log(msg):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line, flush=True)
        with open(run_log, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    log(f"=== Daily full report @ {datetime.now().isoformat(timespec='seconds')} ===")
    log(f"Args: {args}")

    # ---- Stage 0: get ticker list ----
    if args.ticker:
        tickers = [args.ticker]
        watchlist = {args.ticker}
    else:
        tickers = get_all_tickers()
        watchlist = set(get_watchlist())
        if args.limit:
            tickers = tickers[:args.limit]
    log(f"Tickers to process: {len(tickers)} (watchlist: {len(watchlist)})")
    log(f"Workers: {args.workers}")

    # ---- Stage A: build data via cross-source runner (parallel) ----
    log("Stage A: cross-source data assembly (parallel)...")
    t0 = time.time()
    all_data: Dict[str, Dict] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futs = {ex.submit(_assemble_one, t, watchlist, not args.no_yfinance): t for t in tickers}
        for fut in as_completed(futs):
            t, data = fut.result()
            all_data[t] = data
            done += 1
            if done % 50 == 0 or done == len(tickers):
                elapsed = time.time() - t0
                rate = done / elapsed if elapsed > 0 else 0
                eta = (len(tickers) - done) / rate if rate > 0 else 0
                log(f"  [{done:>4}/{len(tickers)}] {elapsed:>5.0f}s "
                    f"({rate:.1f}/s, ETA {eta/60:.1f}min) "
                    f"yfinance_dead={yfb.is_dead()}")
    log(f"Stage A done in {time.time()-t0:.0f}s")

    # ---- Stage B: cross-verify (handled inside assemble) ----
    log("Stage B: cross-verify (see _debug/cross_verify.jsonl)")

    # ---- Stage C: render HTML (parallel, 8 workers) ----
    if not args.skip_render:
        log("Stage C: rendering HTML per ticker (parallel)...")
        t0 = time.time()
        ok, fail = 0, 0
        import render_ticker_full as rtf

        def _render_one(t):
            return t, rtf.render_ticker_tabbed(t, all_data[t], output_dir=str(HTML_DIR))

        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = {ex.submit(_render_one, t): t for t in all_data}
            for fut in as_completed(futs):
                try:
                    t, path = fut.result()
                    ok += 1
                except Exception as e:
                    log(f"  RENDER ERR {futs[fut]}: {e}")
                    fail += 1
                if ok % 200 == 0 and ok > 0:
                    log(f"  rendered {ok}/{len(all_data)} ({time.time()-t0:.0f}s)")
        log(f"Stage C done in {time.time()-t0:.0f}s: {ok} ok, {fail} fail")

    # ---- Stage D: index.html ----
    if not args.skip_render:
        log("Stage D: building index.html...")
        try:
            _build_index_html(tickers, str(HTML_DIR))
            log("  index.html written")
        except Exception as e:
            log(f"  INDEX ERR: {e}")

    # ---- Stage E: publish ----
    log("Stage E: publish (rsync to groovelab + GitHub Pages)")
    try:
        import subprocess
        # rsync to groovelab
        result = subprocess.run([
            "rsync", "-avz", "--delete",
            str(HTML_DIR) + "/",
            "groovelab:/var/www/groovelab.dev/public_html/analyze/"
        ], capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            log(f"  rsync ok: {result.stdout.split(chr(10))[-2]}")
        else:
            log(f"  rsync stderr: {result.stderr[:300]}")
    except Exception as e:
        log(f"  PUBLISH ERR: {e}")

    log(f"=== Done at {datetime.now().isoformat(timespec='seconds')} ===")


if __name__ == "__main__":
    main()
