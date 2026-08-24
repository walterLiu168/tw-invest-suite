"""render_concepts.py — 從 concept-stocks.json + chips.json 產出 concepts.html
10 個熱門概念股，每個顯示：
  - 概念名 + icon + 描述
  - 該概念成分股，今日 / 5 日 法人淨買超加總
  - 點概念 → 展開成分股清單
"""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "public" / "data"
CONCEPT_JSON = DATA / "concept-stocks.json"
CHIPS_JSON = DATA / "chips.json"
OUT = ROOT / "public" / "concepts.html"


def fmt_shares(n):
    if n is None: return "—"
    lots = n / 1000.0
    a = abs(lots)
    if n > 0:
        if a >= 10000: return f"+{a/10000:.1f}萬張"
        if a >= 1000:  return f"+{a/1000:.1f}k張"
        return f"+{int(a)}張"
    if n < 0:
        if a >= 10000: return f"\u2212{a/10000:.1f}萬張"
        if a >= 1000:  return f"\u2212{a/1000:.1f}k張"
        return f"\u2212{int(a)}張"
    return "0張"


def main():
    if not CONCEPT_JSON.exists():
        print(f"[err] {CONCEPT_JSON} not found — run concept_stocks.py first", file=sys.stderr)
        sys.exit(1)
    cs = json.loads(CONCEPT_JSON.read_text(encoding="utf-8"))
    concepts = cs["concepts"]
    t2c = cs["ticker_to_concepts"]

    # chips data
    chips = {}
    if CHIPS_JSON.exists():
        c = json.loads(CHIPS_JSON.read_text(encoding="utf-8"))
        all_picks = c["tabs"]["all_buy"] + c["tabs"]["all_sell"]
        chips = {p["ticker"]: p for p in all_picks}

    today = datetime.now().strftime("%Y-%m-%d")

    def render_concept(name, info):
        tickers = info["tickers"]
        # aggregate 5d 法人 (3 法人)
        f_sum = t_sum = d_sum = 0.0
        f_n = t_n = d_n = 0
        for tk in tickers:
            p = chips.get(tk)
            if not p: continue
            if p.get("f_5d_shares") is not None:
                f_sum += p["f_5d_shares"]; f_n += 1
            if p.get("t_5d_shares") is not None:
                t_sum += p["t_5d_shares"]; t_n += 1
            if p.get("d_5d_shares") is not None:
                d_sum += p["d_5d_shares"]; d_n += 1
        three = f_sum + t_sum + d_sum
        three_class = "v-pos" if three > 0 else ("v-neg" if three < 0 else "")

        # 成分股卡片
        comp_html = ""
        for tk in sorted(tickers, key=lambda x: -(chips.get(x, {}).get("three_5d_shares", -1e9) if chips.get(x) else 0)):
            p = chips.get(tk)
            if not p:
                comp_html += f'<a class="comp-card" href="analyze/{tk}.html" target="_blank">' \
                              f'<span class="ct">{tk}</span><span class="cn muted">—</span>' \
                              f'<span class="cv muted">無 5 日資料</span></a>'
                continue
            f3 = p["f_5d_shares"]; t3 = p["t_5d_shares"]; d3 = p["d_5d_shares"]
            def cls(n): return "v-pos" if n > 0 else ("v-neg" if n < 0 else "")
            comp_html += f'''
            <a class="comp-card" href="analyze/{tk}.html" target="_blank" rel="noopener">
              <span class="ct">{tk}</span>
              <span class="cn">{p["name"][:14]}</span>
              <span class="ci muted">{p.get("industry_zh","")}</span>
              <span class="cv {cls(f3)}">{fmt_shares(f3)}</span>
            </a>'''
        return f'''
        <details class="concept-block" {"open" if i == 0 else ""}>
          <summary>
            <span class="ci-icon">{info["icon"]}</span>
            <span class="cn-name">{name}</span>
            <span class="cn-desc muted">{info["desc"]} · {len(tickers)} 檔</span>
            <span class="cn-stat {three_class}">3 法人 {fmt_shares(three)} 張</span>
            <span class="cn-arrow">▾</span>
          </summary>
          <div class="comp-grid">{comp_html}</div>
        </details>'''

    blocks = []
    for i, (name, info) in enumerate(concepts.items()):
        blocks.append(render_concept(name, info))

    body = "\n".join(blocks)
    date_str = today

    html = f'''<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>概念股 · tw-invest-suite</title>
<meta name="description" content="台股 10 大熱門概念股：半導體、AI、蘋果供應鏈、5G、銅箔基板、矽智財、機器人、記憶體、電動車、重電綠能">
<meta name="theme-color" content="#0a0e1a">
<meta property="og:title" content="概念股 · tw-invest-suite">
<meta property="og:image" content="https://walterliu168.github.io/tw-invest-suite/data/og.png">
<link rel="manifest" href="manifest.json">
<link rel="stylesheet" href="assets/textsize.css">
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><text y='26' font-size='28'>🔥</text></svg>">
<style>
:root {{ --bg:#0a0e1a; --panel:#131b2e; --panel2:#1a2440; --ink:#e6ecf5; --muted:#8aa0c0; --acc:#5fb1ff; --cyan:#39c5cf; --border:#1f2942; --red:#ec7063; --red-soft:#5a2a25; --green:#58d68d; --green-soft:#1f3a2a; --amber:#f5b041; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; padding: 0; background: var(--bg); color: var(--ink); font-family: -apple-system, "Microsoft JhengHei", "Noto Sans TC", system-ui, sans-serif; line-height: 1.5; }}
a {{ color: inherit; text-decoration: none; }}
.hdr {{ max-width: 1200px; margin: 0 auto; padding: 32px 24px 12px; }}
.hdr h1 {{ margin: 0 0 6px; font-size: 1.6rem; }}
.hdr .sub {{ color: var(--muted); font-size: 0.92rem; margin: 0; }}
.hdr .meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; font-size: 0.82rem; }}
.hdr .pill {{ background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 4px 12px; color: var(--muted); }}
.hdr .pill b {{ color: var(--ink); }}
main {{ max-width: 1200px; margin: 0 auto; padding: 16px 24px 60px; }}
.concept-block {{ background: var(--panel); border: 1px solid var(--border); border-radius: 12px; margin-bottom: 12px; overflow: hidden; }}
.concept-block summary {{ list-style: none; cursor: pointer; padding: 14px 18px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }}
.concept-block summary::-webkit-details-marker {{ display: none; }}
.concept-block summary:hover {{ background: var(--panel2); }}
.ci-icon {{ font-size: 1.4rem; }}
.cn-name {{ font-size: 1.1rem; font-weight: 600; color: var(--ink); }}
.cn-desc {{ font-size: 0.85rem; flex: 1; min-width: 200px; }}
.cn-stat {{ font-weight: 700; font-size: 1rem; font-variant-numeric: tabular-nums; }}
.v-pos {{ color: var(--red); }}
.v-neg {{ color: var(--green); }}
.cn-arrow {{ color: var(--muted); font-size: 1.1rem; transition: transform 0.15s; }}
details[open] .cn-arrow {{ transform: rotate(180deg); }}
.comp-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 8px; padding: 0 18px 16px; }}
.comp-card {{ display: grid; grid-template-columns: 70px 1fr auto; align-items: center; gap: 8px; padding: 8px 12px; background: var(--panel2); border: 1px solid var(--border); border-radius: 6px; transition: all 0.15s; }}
.comp-card:hover {{ border-color: var(--acc); transform: translateY(-1px); }}
.ct {{ color: var(--acc); font-weight: 700; font-family: 'Consolas', monospace; font-size: 0.95rem; }}
.cn {{ color: var(--ink); font-size: 0.85rem; }}
.ci {{ font-size: 0.7rem; }}
.cv {{ font-size: 0.85rem; font-weight: 600; font-variant-numeric: tabular-nums; text-align: right; }}
.concept-badges {{ display: flex; flex-wrap: wrap; gap: 3px; margin-top: 4px; }}
.concept-badge {{ display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 0.65rem; font-weight: 600; background: rgba(95,177,255,0.15); color: var(--acc); border: 1px solid rgba(95,177,255,0.3); }}
footer {{ max-width: 1200px; margin: 0 auto 40px; padding: 0 24px; color: var(--muted); font-size: 0.82rem; text-align: center; }}
footer a {{ color: var(--acc); }}
</style>
</head>
<body>

<nav class="module-tabs">
  <a class="mod-tab" href="readme.html">🏠 首頁</a>
  <a class="mod-tab" href="watchlist.html">📊 24 檔精選</a>
  <a class="mod-tab" href="sectors.html">🌊 板塊輪動</a>
  <a class="mod-tab" href="chips.html">💎 籌碼排行</a>
  <a class="mod-tab active" href="concepts.html">🔥 概念股</a>
  <a class="mod-tab" href="chips-advanced.html">📡 籌碼進階</a>
  <a class="mod-tab" href="chips-history.html">🕐 歷史回看</a>
  <a class="mod-tab" href="monitor.html">📲 籌碼監控</a>
</nav>

<div class="hdr">
  <h1>🔥 概念股</h1>
  <p class="sub">台股 10 大熱門概念股 — 半導體 / AI / 蘋果 / 5G / 銅箔基板 / 矽智財 / 機器人 / 記憶體 / 電動車 / 重電綠能</p>
  <div class="meta">
    <div class="pill">📅 資料日 <b>{date_str}</b></div>
    <div class="pill">🏷 涵蓋 <b>{len(concepts)} 個概念 / {len(t2c)} 檔</b></div>
  </div>
</div>

<main>
{body}
</main>

<footer>
  概念股標籤以台股社群/法人常用為主，手動維護 (concept_stocks.py)<br>
  每個概念顯示 5 日法人合計流向，依 3 法人降冪排序<br>
  <a href="https://github.com/walterLiu168/tw-invest-suite">📦 Source</a>
</footer>

<script src="assets/textsize.js"></script>

</body>
</html>'''
    OUT.write_text(html, encoding="utf-8")
    print(f"[concepts.html] {OUT}  ({OUT.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
