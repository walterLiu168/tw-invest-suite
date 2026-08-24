"""render_chips_advanced.py — 從 chips-advanced.json 產 chips-advanced.html
4 個 tab:
  - 法人 20 日均價 (現價 vs 法人 VWAP 折溢價)
  - 力道標 (今日 / 5 日均日 ratio)
  - 雷達 (force_strong_buy/sell + below/above_inst_cost)
"""
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "public" / "data" / "chips-advanced.json"
OUT = ROOT / "public" / "chips-advanced.html"


def fmt_shares(n):
    if n is None: return "—"
    lots = n / 1000.0
    sign = "+" if n > 0 else ("−" if n < 0 else "")
    if abs(lots) >= 10000: return f"{sign}{lots/10000:.1f}萬張"
    if abs(lots) >= 1000: return f"{sign}{lots/1000:.1f}k張"
    return f"{sign}{int(lots)}張"


def fmt_pct(n, d=2):
    if n is None: return "—"
    sign = "+" if n > 0 else ("−" if n < 0 else "")
    return f"{sign}{abs(n):.{d}f}%"


def card(p, mode):
    """mode: 'vwap' | 'force' | 'radar'"""
    t = p["ticker"]; n = p["name"][:14]; ind = p.get("industry", "")[:12]
    if mode == "vwap":
        chips = f'''
            <div class="chip"><div class="k">現價</div><div class="v">{p.get("price", 0):.2f}</div></div>
            <div class="chip"><div class="k">法人 20 日 VWAP</div><div class="v">{p.get("vwap_buy_20d", 0):.2f}</div></div>
            <div class="chip"><div class="k">折溢價</div><div class="v {('v-pos' if (p.get('vs_vwap_pct') or 0) > 0 else 'v-neg')}">{fmt_pct(p.get('vs_vwap_pct'))}</div></div>
            <div class="chip"><div class="k">20 日累計 3 法人</div><div class="v {('v-pos' if (p.get('cum_20d_shares') or 0) > 0 else 'v-neg')}">{fmt_shares(p.get('cum_20d_shares'))}</div></div>'''
    elif mode == "force":
        force = p.get("force_ratio") or 0
        fdir = "v-pos" if (p.get("cum_5d_shares") or 0) > 0 else "v-neg"
        chips = f'''
            <div class="chip"><div class="k">力道 (今/5d 均)</div><div class="v {fdir}">{force:.1f} 倍</div></div>
            <div class="chip"><div class="k">今日 3 法人</div><div class="v {fdir}">{fmt_shares(p.get('cum_5d_shares'))}</div></div>
            <div class="chip"><div class="k">20 日累計</div><div class="v {('v-pos' if (p.get('cum_20d_shares') or 0) > 0 else 'v-neg')}">{fmt_shares(p.get('cum_20d_shares'))}</div></div>
            <div class="chip"><div class="k">現價</div><div class="v">{p.get('price', 0):.2f}</div></div>'''
    else:  # radar — show everything
        chips = f'''
            <div class="chip"><div class="k">力道</div><div class="v">{p.get('force_ratio') or 0:.1f}×</div></div>
            <div class="chip"><div class="k">vs 法人 VWAP</div><div class="v {('v-pos' if (p.get('vs_vwap_pct') or 0) > 0 else 'v-neg')}">{fmt_pct(p.get('vs_vwap_pct'))}</div></div>
            <div class="chip"><div class="k">5d 3 法人</div><div class="v {('v-pos' if (p.get('cum_5d_shares') or 0) > 0 else 'v-neg')}">{fmt_shares(p.get('cum_5d_shares'))}</div></div>
            <div class="chip"><div class="k">20d 3 法人</div><div class="v {('v-pos' if (p.get('cum_20d_shares') or 0) > 0 else 'v-neg')}">{fmt_shares(p.get('cum_20d_shares'))}</div></div>'''
    return f'''
        <a class="card" href="analyze/{t}.html" target="_blank" rel="noopener">
          <div class="card-accent"></div>
          <div class="card-head">
            <span class="ticker">{t}</span>
            <span class="name">{n}</span>
          </div>
          <div class="card-ind muted">{ind}</div>
          <div class="card-chips">{chips}
          </div>
        </a>'''


def render_grid(items, mode, limit=60):
    items = items[:limit]
    if not items:
        return '<div class="empty">無資料</div>'
    return "\n".join(card(p, mode) for p in items)


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    today = data["date"]
    dates = data["trading_dates_20d"]
    feats = data["features"]
    radar = data["radar"]

    # 各 tab 排序
    vwap_below = sorted([f for f in feats if f.get("vs_vwap_pct") is not None and f["vs_vwap_pct"] <= -3], key=lambda x: x["vs_vwap_pct"])
    vwap_above = sorted([f for f in feats if f.get("vs_vwap_pct") is not None and f["vs_vwap_pct"] >= 3], key=lambda x: -x["vs_vwap_pct"])
    force_buy = sorted([x for x in feats if (x.get("force_ratio") or 0) >= 2 and x.get("cum_5d_shares", 0) > 0], key=lambda x: -(x.get("force_ratio") or 0))
    force_sell = sorted([x for x in feats if (x.get("force_ratio") or 0) >= 2 and x.get("cum_5d_shares", 0) < 0], key=lambda x: -(x.get("force_ratio") or 0))
    radar_buy = radar.get("force_strong_buy", [])[:60]
    radar_sell = radar.get("force_strong_sell", [])[:60]

    body = f'''
    <div class="tab-content active" data-bucket="vwap-below">
      <h2 class="bucket-title">現價低於法人 20 日均價 <small>折價 ≥ 3% · 法人加碼買進成本區</small></h2>
      <div class="grid">{render_grid(vwap_below, "vwap")}</div>
    </div>
    <div class="tab-content" data-bucket="vwap-above">
      <h2 class="bucket-title">現價高於法人 20 日均價 <small>溢價 ≥ 3% · 法人已獲利了結</small></h2>
      <div class="grid">{render_grid(vwap_above, "vwap")}</div>
    </div>
    <div class="tab-content" data-bucket="force-buy">
      <h2 class="bucket-title">力道強 · 買盤 <small>今日 3 法人 ≥ 5 日均日 2 倍 且 5 日合計買超</small></h2>
      <div class="grid">{render_grid(force_buy, "force")}</div>
    </div>
    <div class="tab-content" data-bucket="force-sell">
      <h2 class="bucket-title">力道強 · 賣盤 <small>今日 3 法人 ≥ 5 日均日 2 倍 且 5 日合計賣超</small></h2>
      <div class="grid">{render_grid(force_sell, "force")}</div>
    </div>
    <div class="tab-content" data-bucket="radar-buy">
      <h2 class="bucket-title">籌碼雷達 · 強買 <small>力道 ≥ 2× + 5d 買超 + 20d 法人加碼</small></h2>
      <div class="grid">{render_grid(radar_buy, "radar")}</div>
    </div>
    <div class="tab-content" data-bucket="radar-sell">
      <h2 class="bucket-title">籌碼雷達 · 強賣 <small>力道 ≥ 2× + 5d 賣超 + 20d 法人撤離</small></h2>
      <div class="grid">{render_grid(radar_sell, "radar")}</div>
    </div>
    '''

    html = f'''<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>籌碼進階 · tw-invest-suite</title>
<meta name="description" content="法人 20 日均價 · 力道標 · 籌碼雷達">
<meta name="theme-color" content="#0a0e1a">
<meta property="og:title" content="籌碼進階 · tw-invest-suite">
<meta property="og:description" content="法人 20 日 VWAP、力道標、多條件籌碼雷達">
<meta property="og:image" content="https://walterliu168.github.io/tw-invest-suite/data/og.png">
<link rel="manifest" href="manifest.json">
<link rel="stylesheet" href="assets/textsize.css">
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><text y='26' font-size='28'>📡</text></svg>">
<style>
:root {{ --bg:#0a0e1a; --panel:#131b2e; --panel2:#1a2440; --ink:#e6ecf5; --muted:#8aa0c0; --acc:#5fb1ff; --cyan:#39c5cf; --border:#1f2942; --red:#ec7063; --red-soft:#5a2a25; --green:#58d68d; --green-soft:#1f3a2a; --amber:#f5b041; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; padding: 0; background: var(--bg); color: var(--ink); font-family: -apple-system, "Microsoft JhengHei", "Noto Sans TC", system-ui, sans-serif; line-height: 1.5; }}
a {{ color: inherit; text-decoration: none; }}
a:hover .card {{ border-color: var(--acc); transform: translateY(-1px); }}
.hdr {{ max-width: 1200px; margin: 0 auto; padding: 32px 24px 12px; }}
.hdr h1 {{ margin: 0 0 6px; font-size: 1.6rem; }}
.hdr .sub {{ color: var(--muted); font-size: 0.92rem; margin: 0; }}
.hdr .meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; font-size: 0.82rem; }}
.hdr .pill {{ background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 4px 12px; color: var(--muted); }}
.hdr .pill b {{ color: var(--ink); }}
.nav {{ max-width: 1200px; margin: 0 auto; padding: 0 24px 12px; display: flex; flex-wrap: wrap; gap: 6px; }}
.nav a {{ padding: 5px 12px; border: 1px solid var(--border); border-radius: 8px; color: var(--muted); font-size: 0.85rem; }}
.nav a:hover {{ background: var(--panel); color: var(--ink); text-decoration: none; }}
.tabs {{ max-width: 1200px; margin: 0 auto; padding: 0 24px; display: flex; flex-wrap: wrap; gap: 4px; }}
.tab {{ background: var(--panel); color: var(--muted); border: 1px solid var(--border); padding: 7px 14px; border-radius: 8px; cursor: pointer; font-size: 0.85rem; font-weight: 500; }}
.tab:hover {{ color: var(--ink); }}
.tab.active {{ background: var(--cyan); color: #000; border-color: var(--cyan); font-weight: 600; }}
.tab .cnt {{ background: rgba(0,0,0,0.25); padding: 1px 7px; border-radius: 8px; font-size: 0.7rem; margin-left: 4px; }}
.tab.active .cnt {{ background: rgba(255,255,255,0.3); color: #000; }}
main {{ max-width: 1200px; margin: 0 auto; padding: 16px 24px 60px; }}
.bucket-title {{ font-size: 1rem; color: var(--cyan); margin: 0 0 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }}
.bucket-title small {{ color: var(--muted); font-weight: 400; font-size: 0.78rem; }}
.tab-content {{ display: none; }}
.tab-content.active {{ display: block; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px; }}
.card {{ display: block; background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px 12px 18px; position: relative; transition: all 0.15s; overflow: hidden; }}
.card-accent {{ position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: var(--cyan); }}
.card-head {{ display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 4px; }}
.ticker {{ font-size: 1.1rem; font-weight: 700; color: var(--acc); font-family: 'Consolas', monospace; }}
.name {{ color: var(--ink); font-weight: 500; font-size: 0.9rem; }}
.card-ind {{ font-size: 0.75rem; margin-bottom: 8px; }}
.card-chips {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 4px; }}
.chip {{ background: var(--panel2); border: 1px solid var(--border); border-radius: 6px; padding: 5px 7px; }}
.chip .k {{ color: var(--muted); font-size: 0.66rem; }}
.chip .v {{ font-size: 0.88rem; font-weight: 600; margin-top: 1px; font-variant-numeric: tabular-nums; }}
.v-pos {{ color: var(--red); }}
.v-neg {{ color: var(--green); }}
.empty {{ color: var(--muted); text-align: center; padding: 40px; }}
footer {{ max-width: 1200px; margin: 0 auto 40px; padding: 0 24px; color: var(--muted); font-size: 0.82rem; text-align: center; }}
footer a {{ color: var(--acc); }}
</style>
</head>
<body>

<div class="hdr">
  <h1>📡 籌碼進階</h1>
  <p class="sub">法人 20 日均價 · 力道標 · 籌碼雷達 — 多條件篩選 + 雷達</p>
  <div class="meta">
    <div class="pill">📅 資料日 <b>{today}</b></div>
    <div class="pill">📊 20 日區間 <b>{" · ".join(dates[::-1][:5])}…</b></div>
    <div class="pill">🏷 涵蓋 <b>{len(feats)} 檔</b></div>
  </div>
</div>

<div class="nav">
  <a href="readme.html">🏠 首頁</a>
  <a href="watchlist.html">📊 24 檔精選</a>
  <a href="sectors.html">🌊 板塊輪動</a>
  <a href="chips.html">💎 籌碼排行</a>
  <a href="analyze/patterns.html">🎯 型態搜尋</a>
</div>

<div class="tabs">
  <button class="tab active" data-tab="vwap-below">法人均價之下 <span class="cnt">{len(vwap_below)}</span></button>
  <button class="tab" data-tab="vwap-above">法人均價之上 <span class="cnt">{len(vwap_above)}</span></button>
  <button class="tab" data-tab="force-buy">力道強買 <span class="cnt">{len(force_buy)}</span></button>
  <button class="tab" data-tab="force-sell">力道強賣 <span class="cnt">{len(force_sell)}</span></button>
  <button class="tab" data-tab="radar-buy">雷達強買 <span class="cnt">{len(radar_buy)}</span></button>
  <button class="tab" data-tab="radar-sell">雷達強賣 <span class="cnt">{len(radar_sell)}</span></button>
</div>

<main>
{body}
</main>

<footer>
  籌碼資料源：FinMind TaiwanStockInstitutionalInvestorsBuySell + TaiwanStockPrice（每日全市場下載）<br>
  報告為研究參考，非投資建議 · 過往績效不保證未來表現<br>
  <a href="https://github.com/walterLiu168/tw-invest-suite">📦 Source</a>
</footer>

<script>
document.querySelectorAll('.tab').forEach(function (b) {{
  b.addEventListener('click', function () {{
    var k = b.getAttribute('data-tab');
    document.querySelectorAll('.tab').forEach(function (x) {{ x.classList.toggle('active', x === b); }});
    document.querySelectorAll('.tab-content').forEach(function (c) {{
      c.classList.toggle('active', c.getAttribute('data-bucket') === k);
    }});
  }});
}});
</script>
<script src="assets/textsize.js"></script>

</body>
</html>'''
    OUT.write_text(html, encoding="utf-8")
    print(f"[html] {OUT}  ({OUT.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
