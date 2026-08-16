"""
Daily render of ALL 1,943 Taiwan tickers (DB-only, no FinMind/FinLab).

Generates:
    C:\\Groove-Lab\\analyze\\<ticker>.html   for each ticker (1,943 files)
    C:\\Users\\icemo\\.claude\\skills\\tw-invest-suite\\reports\\daily-all-YYYY-MM-DD.html (index)

Usage:
    python daily_all_tickers.py [--workers N] [--limit N]
"""
import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db_client as db
import render_ticker_db_only as rt


def get_all_tickers() -> list:
    """Get distinct stock tickers (4-digit stocks + 4+letter warrants) from market_snapshot."""
    rows = db.market_snapshot()
    return [r["Ticker"] for r in rows]


def render_one(args):
    """Render one ticker to HTML."""
    ticker, batch, history = args
    snap = batch["snap_map"].get(ticker)
    if not snap:
        return ticker, None, "no snapshot"
    ret_data = batch["rets_map"].get(ticker, {})
    chip = batch["chip_map"].get(ticker, {})
    try:
        html = rt.render_ticker_html_db_only(
            ticker=ticker,
            snap=snap,
            ret_data=ret_data,
            chip=chip,
            history=history,
        )
        if html is None:
            return ticker, None, "render returned None"
        return ticker, html, None
    except Exception as e:
        return ticker, None, str(e)


def main():
    parser = argparse.ArgumentParser(description="Daily render all Taiwan tickers (DB-only)")
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers (default 4)")
    parser.add_argument("--limit", type=int, default=0, help="Limit tickers (0 = all)")
    parser.add_argument("--out", default=r"C:\Groove-Lab\analyze", help="Output directory")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== tw-invest-suite · daily all-tickers · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===")
    tickers = get_all_tickers()
    if args.limit > 0:
        tickers = tickers[:args.limit]
    print(f"  Total tickers: {len(tickers)}")
    print(f"  Workers: {args.workers}")
    print(f"  Output: {out_dir}")

    # Pre-fetch batch data
    batch = rt.fetch_all_data_for_batch(tickers, workers=args.workers)
    # Filter tickers to only those with snapshot
    valid_tickers = [t for t in tickers if t in batch["snap_map"]]
    skipped = len(tickers) - len(valid_tickers)
    if skipped:
        print(f"  Skipping {skipped} tickers without snapshot")
    print(f"  Rendering {len(valid_tickers)} tickers...\n")

    # Pre-fetch history (1 query per ticker, but inside workers parallel)
    t0 = time.time()
    results = {"ok": 0, "err": 0, "errs": []}

    with ThreadPoolExecutor(max_workers=args.workers) as exe:
        # Submit: first fetch history, then render
        def task(ticker):
            history = rt.fetch_history_for_ticker(ticker)
            return render_one((ticker, batch, history))

        futs = {exe.submit(task, t): t for t in valid_tickers}
        done = 0
        for fut in as_completed(futs):
            ticker, html, err = fut.result()
            done += 1
            elapsed = time.time() - t0
            eta = (elapsed / done) * (len(valid_tickers) - done) if done else 0
            if err:
                results["err"] += 1
                results["errs"].append((ticker, err))
                status = f"⚠ {err[:30]}"
            else:
                results["ok"] += 1
                # Write to file
                (out_dir / f"{ticker}.html").write_text(html, encoding="utf-8")
                status = "✓"
            if done % 50 == 0 or done == len(valid_tickers):
                print(f"  [{done}/{len(valid_tickers)}] {status}  ({elapsed:.0f}s elapsed, ~{eta:.0f}s left)")

    elapsed = time.time() - t0
    print(f"\n=== Done in {elapsed:.0f}s ===")
    print(f"  OK: {results['ok']}")
    print(f"  Errors: {results['err']}")
    if results["errs"][:5]:
        print(f"  First 5 errors:")
        for t, e in results["errs"][:5]:
            print(f"    {t}: {e[:80]}")

    # Generate index
    write_index(out_dir, valid_tickers, results, elapsed)


def write_index(out_dir, tickers, results, elapsed):
    """Generate a simple index.html in the analyze directory."""
    sorted_t = sorted(tickers)
    total_size = sum((out_dir / f"{t}.html").stat().st_size for t in sorted_t if (out_dir / f"{t}.html").exists())
    total_mb = total_size / 1024 / 1024

    rows = []
    for t in sorted_t:
        path = out_dir / f"{t}.html"
        if path.exists():
            sz = path.stat().st_size / 1024
            rows.append(f'<tr><td><a href="{t}.html">{t}</a></td><td class="muted">{sz:.1f} KB</td></tr>')

    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>All Taiwan Stocks · Daily Index</title>
<style>
:root {{ --bg:#0a0e1a; --panel:#131b2e; --ink:#e6ecf5; --muted:#8aa0c0; --acc:#5fb1ff; --border:#1f2942; }}
body {{ margin: 0; padding: 24px; background: var(--bg); color: var(--ink); font-family: -apple-system, "Microsoft JhengHei", sans-serif; }}
h1 {{ color: var(--acc); }}
.search {{ background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 16px; margin-bottom: 16px; }}
.search input {{ background: var(--bg); color: var(--ink); border: 1px solid var(--border); border-radius: 4px; padding: 6px 10px; width: 160px; }}
.search button {{ background: var(--acc); color: #000; border: none; border-radius: 4px; padding: 6px 12px; margin-left: 4px; cursor: pointer; }}
.summary {{ display: flex; gap: 16px; flex-wrap: wrap; color: var(--muted); margin-bottom: 16px; font-size: 0.85rem; }}
table {{ width: 100%; border-collapse: collapse; background: var(--panel); border-radius: 8px; overflow: hidden; }}
th, td {{ padding: 6px 12px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.05); }}
th {{ background: rgba(255,255,255,0.04); font-size: 0.78rem; text-transform: uppercase; color: var(--muted); }}
td.muted {{ color: var(--muted); font-size: 0.78rem; }}
tr:hover td {{ background: rgba(95,177,255,0.06); }}
a {{ color: var(--acc); text-decoration: none; }}
.search-jump {{ position: sticky; top: 0; background: var(--bg); padding: 8px 0; border-bottom: 1px solid var(--border); margin-bottom: 8px; z-index: 5; }}
.search-jump a {{ margin-right: 6px; padding: 3px 8px; background: var(--panel); border-radius: 12px; font-size: 0.78rem; }}
</style>
</head>
<body>
<h1>📊 All Taiwan Stocks · Daily Index</h1>
<div class="search">
  <input id="q" placeholder="搜尋代號 e.g. 2324" autofocus>
  <button onclick="go()">跳轉 →</button>
</div>
<div class="summary">
  <span>📅 {today}</span> · <span>共 <b style="color:var(--acc)">{len(sorted_t)}</b> 檔</span> · 
  <span>OK <b style="color:#58d68d">{results['ok']}</b></span> · 
  <span>錯誤 <b style="color:#ec7063">{results['err']}</b></span> · 
  <span>總大小 <b>{total_mb:.1f} MB</b></span> · 
  <span>耗時 <b>{elapsed:.0f}s</b></span>
</div>
<div class="search-jump" id="jump"></div>
<table>
  <thead><tr><th style="width:140px">代號</th><th>大小</th></tr></thead>
  <tbody>
{chr(10).join(rows)}
  </tbody>
</table>
<script>
const rows = document.querySelectorAll('tbody tr');
const jump = document.getElementById('jump');
// Build A-Z / 0-9 jump links
const buckets = ['0','1','2','3','4','5','6','7','8','9','A','B','C','D','E','F','G','H','I','J','K','L','M','N','O','P','Q','R','S','T','U','V','W','X','Y','Z'];
buckets.forEach(b => {{
  const a = document.createElement('a');
  a.href = '#';
  a.textContent = b;
  a.onclick = e => {{
    e.preventDefault();
    for (const r of rows) {{
      if (r.textContent.trim().startsWith(b)) {{ r.scrollIntoView({{behavior:'smooth', block:'start'}}); break; }}
    }}
  }};
  jump.appendChild(a);
}});
function go() {{
  const v = document.getElementById('q').value.trim();
  if (v) window.location.href = v + '.html';
}}
document.getElementById('q').addEventListener('keydown', e => {{ if (e.key === 'Enter') go(); }});
</script>
</body>
</html>"""
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    print(f"  → {out_dir}/index.html")


if __name__ == "__main__":
    main()
