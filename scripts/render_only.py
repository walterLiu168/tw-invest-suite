"""Render-only mode — uses cache, no API calls.

Use this AFTER cache has been populated by batch_yfinance_only,
batch_finmind_only, and batch_finmind_news.

Renders 1,943 HTML files from cached data.
"""
import sys
import os
import html
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import pymysql
import cross_source_runner as csr
import render_ticker_full as rtf
import pipeline_state as ps


HTML_DIR = Path(r"C:\Groove-Lab\analyze")


def _render_one(t, data, output_dir, data_date, data_issue=False, numeric_warning=None):
    try:
        if data.get("_err"):
            raise ValueError(data["_err"])
        rtf.render_ticker_tabbed(t, data, output_dir=str(Path(output_dir)))
        notices = []
        if data_issue:
            notices.append(f'資料不完整：本次資料日 {data_date}，此股票最後報價日 {html.escape(str(data.get("latest_date") or "無"))}。可能停牌、下市或來源缺漏，請勿視為當日可交易報價。')
        if numeric_warning:
            notices.append('估值／基本面來源含無效數值，已標為缺漏：' + html.escape(', '.join(numeric_warning)))
        if notices:
            path = Path(output_dir) / f"{t}.html"
            notice = '<aside role="status" style="padding:12px;background:#fff3cd;color:#533f03">' + '<br>'.join(notices) + '</aside>'
            body = path.read_text(encoding="utf-8")
            path.write_text(body.replace("<body>", "<body>" + notice, 1), encoding="utf-8")
        return t, True
    except Exception as e:
        return t, str(e)



def get_all_tickers():
    conn = pymysql.connect(host='localhost', user='root', password='1234',
                            database='tw_elec', connect_timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT ticker FROM industry_type "
                "WHERE ticker REGEXP '^[0-9]{4}$|^[0-9]{4}[A-Z]$' ORDER BY ticker")
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
    data_date = os.environ.get("TW_DATA_DATE") or ps.db_snapshot()["data_date"]
    nightly_id = os.environ.get("TW_NIGHTLY_ID", "manual")
    if len(tickers) < 1900:
        raise RuntimeError(f"render universe too small: {len(tickers)}")
    watchlist = get_watchlist()
    print(f"[{datetime.now():%H:%M:%S}] Render-only: {len(tickers)} tickers "
          f"({len(watchlist)} watchlist with 4h news) "
          f"no_news={args.no_news} no_yfinance={args.no_yfinance}")

    # Stage A: assemble data from cache (fast, no API if cache hit)
    t0 = time.time()
    all_data = {}
    data_issues = []
    for i, t in enumerate(tickers, 1):
        tier = "watchlist" if t in watchlist else "all"
        try:
            all_data[t] = csr.assemble(t, news_tier=tier,
                                         use_yfinance=not args.no_yfinance,
                                         fetch_news=not args.no_news,
                                         cache_only=args.no_news and args.no_yfinance)
            if all_data[t].get("_db_err"):
                raise ValueError(all_data[t]["_db_err"])
            if all_data[t].get("latest_date") != data_date or not all_data[t].get("latest_close"):
                if t in watchlist:
                    raise ValueError("selected pick has missing/stale OHLCV")
                data_issues.append({"ticker": t, "latest_date": all_data[t].get("latest_date"), "latest_close": all_data[t].get("latest_close")})
        except Exception as e:
            all_data[t] = {"ticker": t, "_err": str(e)}
        if i % 200 == 0 or i == len(tickers):
            print(f"  assemble [{i}/{len(tickers)}] {time.time()-t0:.0f}s", flush=True)
    print(f"  Stage A (assemble): {time.time()-t0:.0f}s")

    # Stage C: render HTML in parallel
    t0 = time.time()
    ok, fail = 0, 0
    failures, artifacts = [], []
    issue_tickers = {i["ticker"] for i in data_issues}
    numeric_issues = {t: d.get("_meta", {}).get("numeric_warnings") for t, d in all_data.items()
                      if d.get("_meta", {}).get("numeric_warnings")}

    with ProcessPoolExecutor(max_workers=4) as ex:
        futs = {ex.submit(_render_one, t, data, str(HTML_DIR), data_date,
                          t in issue_tickers, numeric_issues.get(t)): t for t, data in all_data.items()}
        for fut in as_completed(futs):
            t, result = fut.result()
            if result is True:
                ok += 1
                artifacts.append(ps.artifact(HTML_DIR / f"{t}.html", f"analyze/{t}.html"))
            else:
                fail += 1
                failures.append({"ticker": t, "error": result})
            if (ok + fail) % 200 == 0:
                print(f"  render [{ok+fail}/{len(all_data)}] {time.time()-t0:.0f}s "
                      f"ok={ok} fail={fail}", flush=True)
    print(f"  Stage C (render): {time.time()-t0:.0f}s — {ok} ok, {fail} fail")

    # Stage D: index.html
    print(f"[{datetime.now():%H:%M:%S}] Building index.html...")
    from daily_full_tickers import _build_index_html
    _build_index_html(tickers, str(HTML_DIR))

    ps.atomic_json(HTML_DIR / "render_receipt.json", {
        "nightly_id": nightly_id, "data_date": data_date, "expected_count": len(tickers),
        "failures": failures, "artifacts": sorted(artifacts, key=lambda a: a["gh_path"]),
        "data_issues": data_issues, "fresh_count": len(tickers) - len(data_issues) - len(failures),
        "numeric_data_issues": numeric_issues,
    })
    if failures:
        raise RuntimeError(f"render failed for {len(failures)} tickers: {failures[:5]}")

    print(f"[{datetime.now():%H:%M:%S}] Done. {ok} HTML files in {HTML_DIR}")


if __name__ == "__main__":
    main()
