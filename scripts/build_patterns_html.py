"""
Build patterns.html — 8 pattern chips + top 30 list per pattern + backtest stats.
Reads patterns.json and emits a single HTML page.
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path


CSS = """
/* 台灣顏色慣例（與美股相反）：
   --red  = 紅色 (用於「上漲/正面/多頭」)
   --green = 綠色 (用於「下跌/負面/空頭」)
   變數名跟顏色值一致，selector 自行選擇正確變數 */
:root { --bg:#0a0e1a; --panel:#131b2e; --ink:#e6ecf5; --muted:#8aa0c0; --acc:#5fb1ff; --green:#58d68d; --red:#ec7063; --amber:#f5b041; --purple:#bc8cff; --cyan:#39c5cf; --border:#1f2942; }
* { box-sizing: border-box; }
body { margin: 0; padding: 0; background: var(--bg); color: var(--ink); font-family: -apple-system, "Microsoft JhengHei", "Noto Sans TC", system-ui, sans-serif; line-height: 1.6; }
.topbar { position: sticky; top: 0; z-index: 100; background: rgba(10, 14, 26, 0.95); backdrop-filter: blur(8px); border-bottom: 1px solid var(--border); padding: 12px 20px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
.brand { font-size: 1.2rem; font-weight: 600; color: var(--acc); }
.brand small { color: var(--muted); font-weight: 400; font-size: 0.7rem; margin-left: 8px; }
.search-form { display: flex; gap: 6px; }
.search-form input { background: var(--panel); color: var(--ink); border: 1px solid var(--border); border-radius: 6px; padding: 6px 10px; font-size: 0.85rem; width: 110px; font-family: inherit; }
.search-form button { background: var(--acc); color: #000; border: none; border-radius: 6px; padding: 6px 12px; font-size: 0.85rem; font-weight: 600; cursor: pointer; }
.chips { display: flex; flex-wrap: wrap; gap: 8px; padding: 16px 20px; background: rgba(0,0,0,0.2); border-bottom: 1px solid var(--border); }
.chip { padding: 10px 18px; border-radius: 22px; background: var(--panel); color: var(--ink); cursor: pointer; font-size: 0.95rem; border: 1px solid var(--border); transition: all 0.2s; user-select: none; }
.chip:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(95,177,255,0.2); }
.chip.active { background: var(--acc); color: #000; border-color: var(--acc); }
.chip .count { background: rgba(0,0,0,0.3); padding: 1px 8px; border-radius: 10px; font-size: 0.8rem; margin-left: 6px; }
.pattern-section { padding: 20px; max-width: 1400px; margin: 0 auto; }
.pattern-header { background: linear-gradient(135deg, rgba(95,177,255,0.1), rgba(57,197,207,0.05)); border: 1px solid var(--border); border-radius: 10px; padding: 20px 24px; margin-bottom: 16px; }
.pattern-title { font-size: 1.5rem; font-weight: 700; color: var(--acc); margin-bottom: 4px; }
.pattern-desc { color: var(--muted); font-size: 0.95rem; }
.backtest-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin: 16px 0; }
.bt-card { background: var(--panel); border-radius: 8px; padding: 12px 16px; border: 1px solid var(--border); }
.bt-card .label { color: var(--muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.4px; }
.bt-card .val { font-size: 1.4rem; font-weight: 700; margin-top: 4px; }
.bt-card .sub { color: var(--muted); font-size: 0.7rem; margin-top: 2px; }
/* 高勝率 = 正面 = 紅 / 低勝率 = 負面 = 綠 (台灣) */
.win-high { color: var(--red); }
.win-low { color: var(--green); }
.stock-table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 0.88rem; margin-top: 12px; background: rgba(0,0,0,0.15); border-radius: 6px; overflow: hidden; }
.stock-table th { background: rgba(255,255,255,0.04); color: var(--muted); font-weight: 600; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.4px; padding: 8px 10px; text-align: right; }
.stock-table th:first-child, .stock-table td:first-child { text-align: left; }
.stock-table td { padding: 8px 10px; border-bottom: 1px solid rgba(255,255,255,0.04); text-align: right; }
.stock-table tr:last-child td { border-bottom: none; }
.stock-table tr:hover { background: rgba(95,177,255,0.05); }
/* 漲 = 紅 / 跌 = 綠 (台灣) */
.stock-table td.pos { color: var(--red); font-weight: 600; }
.stock-table td.neg { color: var(--green); font-weight: 600; }
.stock-table a { color: var(--acc); text-decoration: none; font-weight: 600; }
.stock-table a:hover { text-decoration: underline; }
.verdict { padding: 12px 16px; border-radius: 8px; margin: 12px 0; font-size: 0.95rem; line-height: 1.7; }
/* 勝 = 紅 / 敗 = 綠 (台灣) */
.verdict.win { background: rgba(236,112,99,0.12); border-left: 4px solid var(--red); }
.verdict.lose { background: rgba(88,214,141,0.12); border-left: 4px solid var(--green); }
.verdict.neutral { background: rgba(95,177,255,0.12); border-left: 4px solid var(--acc); }
footer { padding: 24px; color: var(--muted); font-size: 0.8rem; text-align: center; }
.meta { color: var(--muted); font-size: 0.85rem; }
"""


def _esc(s) -> str:
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _verdict_for_pattern(pkey: str, win_rate: float) -> tuple:
    """Return (verdict_text, css_class) based on win rate."""
    if win_rate >= 60:
        return (f"✅ 歷史勝率 {win_rate}%，這個型態在台股有統計優勢", "win")
    elif win_rate >= 50:
        return (f"🟡 歷史勝率 {win_rate}%，這個型態略微正向，沒有顯著優勢", "neutral")
    else:
        return (f"⚠️ 歷史勝率 {win_rate}%，這個型態在台股表現較弱", "lose")


def _build_pattern_section(pkey: str, pinfo: dict, top_stocks: list, backtest: dict) -> str:
    bt = backtest.get(pkey, {})
    bt20 = bt.get("count_20d", {})
    bt60 = bt.get("count_60d", {})
    win_rate = bt20.get("win_rate", 0)
    avg20 = bt20.get("avg", 0)
    verdict_text, verdict_cls = _verdict_for_pattern(pkey, win_rate)

    # Stock rows
    rows = []
    for s in top_stocks:
        ret_20d = s.get("ret_20d", 0)
        ret_60d = s.get("ret_60d", 0)
        ret_240d = s.get("ret_240d", 0)
        fnet = s.get("fnet", 0)
        fnet_s = f"{fnet/1000:+,.0f}" if fnet else "0"
        cls = "pos" if ret_20d > 0 else "neg"
        cls60 = "pos" if ret_60d > 0 else "neg"
        cls240 = "pos" if ret_240d > 0 else "neg"
        cls_fnet = "pos" if fnet > 0 else "neg"
        roe = s.get("roe", 0)
        roe_s = f"{roe:.0f}%" if roe else "—"
        pe = s.get("pe")
        pe_s = f"{pe:.1f}" if pe else "—"
        pb = s.get("pb")
        pb_s = f"{pb:.2f}" if pb else "—"
        rows.append(f"""
        <tr>
          <td><a href="https://groovelab.dev/analyze/{_esc(s['ticker'])}.html">{_esc(s['ticker'])}</a></td>
          <td class="num">{s.get('close', 0):.2f}</td>
          <td class="num {s.get('change_pct', 0) > 0 and 'pos' or 'neg'}">{s.get('change_pct', 0):+.2f}%</td>
          <td class="num {cls}">{ret_20d:+.1f}%</td>
          <td class="num {cls60}">{ret_60d:+.1f}%</td>
          <td class="num {cls240}">{ret_240d:+.1f}%</td>
          <td class="num">{s.get('rsi', 0):.0f}</td>
          <td class="num">{s.get('volume', 0):,}</td>
          <td class="num {cls_fnet}">{fnet_s}</td>
          <td class="num">{roe_s}</td>
          <td class="num">{pe_s}</td>
          <td class="num">{pb_s}</td>
        </tr>""")

    # Backtest mini cards
    bt_cards = f"""
    <div class="backtest-grid">
      <div class="bt-card">
        <div class="label">20 日 forward 勝率</div>
        <div class="val {('win-high' if win_rate >= 55 else 'win-low' if win_rate < 45 else '')}">{win_rate}%</div>
        <div class="sub">{bt20.get('count', 0)} trades (240 日回測)</div>
      </div>
      <div class="bt-card">
        <div class="label">20 日平均報酬</div>
        <div class="val {('win-high' if avg20 > 0 else 'win-low')}">{avg20:+.2f}%</div>
        <div class="sub">中位數 {bt20.get('median', 0):+.2f}%</div>
      </div>
      <div class="bt-card">
        <div class="label">20 日最佳/最差</div>
        <div class="val win-high">{bt20.get('max', 0):+.1f}%</div>
        <div class="sub win-low">最差 {bt20.get('min', 0):+.1f}%</div>
      </div>
      <div class="bt-card">
        <div class="label">60 日 forward 勝率</div>
        <div class="val">{bt60.get('win_rate', 0)}%</div>
        <div class="sub">{bt60.get('count', 0)} trades</div>
      </div>
    </div>"""

    table = f"""
    <table class="stock-table">
      <thead>
        <tr>
          <th>股號</th><th>現價</th><th>當日%</th>
          <th>20日%</th><th>60日%</th><th>240日%</th>
          <th>RSI</th><th>成交量</th><th>外資(張)</th>
          <th>ROE</th><th>P/E</th><th>P/B</th>
        </tr>
      </thead>
      <tbody>{''.join(rows)}</tbody>
    </table>"""

    return f"""
    <div id="p-{pkey}" class="pattern-section">
      <div class="pattern-header">
        <div class="pattern-title">{_esc(pinfo['name_zh'])} — {_esc(pinfo['desc'])}</div>
        <div class="meta">{pinfo['count']} 檔符合 · 回測使用過去 240 日資料 · 樣本每 5 日取一次</div>
      </div>
      {bt_cards}
      <div class="verdict {verdict_cls}">{verdict_text}</div>
      {table}
    </div>"""


def build_html(patterns_json: dict) -> str:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    as_of = patterns_json.get("as_of_date", "—")
    total = patterns_json.get("total_tickers", 0)
    build_time = patterns_json.get("build_time_seconds", 0)

    # Top chips with counts
    chips_html = []
    for pkey, pinfo in patterns_json["patterns"].items():
        chip_class = "chip"
        chips_html.append(
            f'<a href="#p-{pkey}" class="{chip_class}" '
            f'style="text-decoration:none;color:inherit">'
            f'{_esc(pinfo["name_zh"])}'
            f'<span class="count">{pinfo["count"]}</span></a>'
        )
    chips_block = "".join(chips_html)

    # Pattern sections
    sections = []
    for pkey, pinfo in patterns_json["patterns"].items():
        if pinfo["count"] == 0:
            continue
        top_stocks = patterns_json["top_stocks"].get(pkey, [])
        backtest = patterns_json.get("backtest", {})
        sections.append(_build_pattern_section(pkey, pinfo, top_stocks, backtest))

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>型態搜尋 · {_esc(as_of)} · {total} 檔</title>
<style>{CSS}</style>
</head>
<body>
<div class="topbar">
  <div class="brand">📊 型態搜尋 <small>tw-invest-suite · {as_of} · {total} 檔</small></div>
  <form class="search-form" action="https://groovelab.dev/analyze.html" method="get">
    <input name="ticker" placeholder="個股查詢" maxlength="6" required>
    <button type="submit">查詢 →</button>
  </form>
</div>
<div class="chips">{chips_block}</div>
<main>
  {''.join(sections)}
  <footer>
    tw-invest-suite · {now_str} · 從 MySQL `daily_data2_full` 計算 + yfinance 補 ROE/P/E/P/B · 過去 240 日 walk-forward 回測
  </footer>
</main>
</body>
</html>"""


def main():
    json_path = Path(r"C:\Groove-Lab\analyze\patterns.json")
    out_path = Path(r"C:\Groove-Lab\analyze\patterns.html")

    if not json_path.exists():
        print(f"ERR: {json_path} not found. Run pattern_classifier.py first.")
        sys.exit(1)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    html = build_html(data)
    out_path.write_text(html, encoding="utf-8")
    print(f"Built: {out_path} ({len(html):,} bytes)")


if __name__ == "__main__":
    main()
