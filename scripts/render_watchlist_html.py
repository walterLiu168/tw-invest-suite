"""
Generate watchlist.html for groovelab.dev/watchlist.html.

Reads active picks + performance from MySQL `tw_elec` and renders an
inline-CSS HTML page. Writes to:
  - C:\\Users\\icemo\\.claude\\skills\\tw-invest-suite\\reports\\watchlist-YYYY-MM-DD.html
  - C:\\Groove-Lab\\watchlist.html  (live, served by groovelab)
"""
import os
import sys
import html
from datetime import datetime, date
from pathlib import Path

import pymysql

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import watchlist as wl  # noqa: E402


CSS = """
:root { --bg:#0b1020; --panel:#121a2e; --ink:#e6ecf5; --muted:#8aa0c0; --acc:#5fb1ff; --green:#58d68d; --red:#ec7063; --amber:#f5b041; }
* { box-sizing: border-box; }
body { margin: 0; padding: 24px; background: var(--bg); color: var(--ink); font-family: -apple-system, "Microsoft JhengHei", "Noto Sans TC", system-ui, sans-serif; }
header { display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-bottom: 20px; }
h1 { margin: 0; font-size: 1.6rem; letter-spacing: 0.5px; }
.subtitle { color: var(--muted); font-size: 0.95rem; }
.summary { display: flex; gap: 16px; flex-wrap: wrap; margin: 12px 0 24px; }
.card { background: var(--panel); border-radius: 10px; padding: 12px 16px; min-width: 120px; border: 1px solid #1f2942; }
.card .k { color: var(--muted); font-size: 0.8rem; }
.card .v { font-size: 1.4rem; font-weight: 600; margin-top: 4px; }
.bucket { margin: 28px 0 8px; font-size: 1.15rem; color: var(--acc); border-bottom: 1px solid #1f2942; padding-bottom: 6px; }
table { width: 100%; border-collapse: collapse; background: var(--panel); border-radius: 10px; overflow: hidden; margin-bottom: 12px; }
th, td { padding: 10px 12px; text-align: right; font-size: 0.92rem; }
th { background: #182241; color: var(--muted); font-weight: 500; text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.5px; }
td.l, th.l { text-align: left; }
tr:hover td { background: #182241; }
.pill { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.75rem; font-weight: 500; }
.pill-long { background: rgba(88, 214, 141, 0.18); color: var(--green); }
.pill-short { background: rgba(245, 176, 65, 0.18); color: var(--amber); }
.ret-up { color: var(--green); font-weight: 600; }
.ret-down { color: var(--red); font-weight: 600; }
.ret-flat { color: var(--muted); }
footer { margin-top: 32px; color: var(--muted); font-size: 0.8rem; text-align: center; }
a { color: var(--acc); text-decoration: none; }
a:hover { text-decoration: underline; }
"""


def fmt_pct(v):
    if v is None: return "—"
    return f"{v*100:+.2f}%"


def fmt_price(v):
    if v is None: return "—"
    return f"{v:,.1f}"


def main():
    data = wl.get_performance_report()
    rows = data["picks"]
    as_of = data["as_of"]
    today = date.today().strftime("%Y-%m-%d")

    if not rows:
        print("No active picks.")
        return

    by_bucket = {}
    for r in rows:
        by_bucket.setdefault(r["bucket"], []).append(r)

    rets = [r.get("ret_since_pick") for r in rows if r.get("ret_since_pick") is not None]
    avg = sum(rets) / len(rets) if rets else 0
    wins = sum(1 for r in rets if r > 0)
    winrate = wins / len(rets) * 100 if rets else 0

    body = []
    body.append(f'<h1>📊 台股市場掃描 Watchlist</h1>')
    body.append(f'<div class="subtitle">資料日 {today} · 最後更新 {as_of[:19]} · 24 檔精選</div>')
    body.append('<div class="summary">')
    body.append(f'<div class="card"><div class="k">活躍 picks</div><div class="v">{len(rows)}</div></div>')
    body.append(f'<div class="card"><div class="k">平均報酬</div><div class="v" style="color:{"var(--green)" if avg > 0 else "var(--red)"}">{avg*100:+.2f}%</div></div>')
    body.append(f'<div class="card"><div class="k">勝率</div><div class="v">{winrate:.0f}%</div></div>')
    body.append(f'<div class="card"><div class="k">分組</div><div class="v">{len(by_bucket)} 個</div></div>')
    body.append('</div>')

    for bucket in ["<100", "100-300", "300-1000", ">1000"]:
        items = by_bucket.get(bucket, [])
        if not items: continue
        label = {"<100": "💰 銅板股 (<100 元)", "100-300": "💵 中價股 (100-300 元)",
                 "300-1000": "💎 中高價 (300-1000 元)", ">1000": "🏆 高價股 (>1000 元)"}[bucket]
        body.append(f'<div class="bucket">{label}</div>')
        body.append('<table>')
        body.append('<thead><tr><th class="l">代號</th><th class="l">名稱</th><th class="l">類型</th><th>進場價</th><th>現價</th><th>報酬</th><th>最高</th><th>最低</th><th>回撤</th><th class="l">進場日</th></tr></thead>')
        body.append('<tbody>')
        for r in items:
            cur = r.get("current_close")
            pick = r.get("close_at_pick")
            ret = r.get("ret_since_pick")
            hi = r.get("high_since")
            lo = r.get("low_since")
            dd = r.get("drawdown")
            rd = r.get("run_date")
            ret_cls = "ret-up" if (ret is not None and ret > 0.0005) else "ret-down" if (ret is not None and ret < -0.0005) else "ret-flat"
            pill_cls = "pill-long" if r["horizon"] == "long" else "pill-short"
            pill_lbl = "長期" if r["horizon"] == "long" else "短中期"
            body.append(
                f'<tr><td class="l"><b>{html.escape(r["ticker"])}</b></td>'
                f'<td class="l">{html.escape(r["name"])}</td>'
                f'<td class="l"><span class="pill {pill_cls}">{pill_lbl}</span></td>'
                f'<td>{fmt_price(pick)}</td>'
                f'<td>{fmt_price(cur)}</td>'
                f'<td class="{ret_cls}">{fmt_pct(ret)}</td>'
                f'<td>{fmt_price(hi)}</td>'
                f'<td>{fmt_price(lo)}</td>'
                f'<td class="{ret_cls}">{fmt_pct(dd)}</td>'
                f'<td class="l">{rd}</td></tr>'
            )
        body.append('</tbody></table>')

    body.append('<footer>tw-invest-suite · ' + today + ' · 完整報告：<a href="https://walterLiu168.github.io/stock-report/market-screen-' + today + '.html">GitHub Pages</a></footer>')

    html_doc = (
        f'<!DOCTYPE html><html lang="zh-Hant"><head><meta charset="UTF-8">'
        f'<title>Watchlist · {today}</title>'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<style>{CSS}</style></head><body>'
        + "\n".join(body)
        + '</body></html>'
    )

    # Write to two locations
    reports_dir = Path.home() / ".claude" / "skills" / "tw-invest-suite" / "reports"
    out1 = reports_dir / f"watchlist-{today}.html"
    out1.write_text(html_doc, encoding="utf-8")
    print(f"  → {out1}")

    groove = Path(r"C:\Groove-Lab\watchlist.html")
    groove.write_text(html_doc, encoding="utf-8")
    print(f"  → {groove}")

    print(f"  rows: {len(rows)}, buckets: {len(by_bucket)}")
    print(f"  avg: {avg*100:+.2f}%, winrate: {winrate:.0f}%")


if __name__ == "__main__":
    main()
