"""
Render a single-ticker deep-dive HTML for groovelab.dev/analyze/<ticker>.html.

Usage:
    python render_ticker_html.py <ticker> [--out PATH] [--no-save]

Output:
    - C:\\Groove-Lab\\analyze\\<ticker>.html  (live, served by groovelab tunnel)
    - C:\\Users\\icemo\\.claude\\skills\\tw-invest-suite\\reports\\analyze-<ticker>-<date>.html
"""
import argparse
import html as _html_lib
import os
import sys
import re as _re
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_stock as a
import db_client as db
import market_screen as ms
import zen_analyzer as zen
import deep_dive_prompts as ddp


CSS = """
:root { --bg:#0a0e1a; --panel:#131b2e; --ink:#e6ecf5; --muted:#8aa0c0; --acc:#5fb1ff;
  /* Taiwan convention: 紅漲 (up=positive) = #ec7063, 綠跌 (down=negative) = #58d68d */
  --red:#ec7063;   /* used for POSITIVE/up — Taiwan 紅漲 */
  --green:#58d68d; /* used for NEGATIVE/down — Taiwan 綠跌 */
  --amber:#f5b041; --purple:#bc8cff; --cyan:#39c5cf; --border:#1f2942; }
* { box-sizing: border-box; }
body { margin: 0; padding: 0; background: var(--bg); color: var(--ink); font-family: -apple-system, "Microsoft JhengHei", "Noto Sans TC", system-ui, sans-serif; line-height: 1.6; }
.topbar { position: sticky; top: 0; z-index: 100; background: rgba(10, 14, 26, 0.95); backdrop-filter: blur(8px); border-bottom: 1px solid var(--border); padding: 12px 20px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
.brand { font-size: 1.2rem; font-weight: 600; color: var(--acc); }
.brand small { color: var(--muted); font-weight: 400; font-size: 0.7rem; margin-left: 8px; }
.search-form { display: flex; gap: 6px; }
.search-form input { background: var(--panel); color: var(--ink); border: 1px solid var(--border); border-radius: 6px; padding: 6px 10px; font-size: 0.85rem; width: 110px; font-family: inherit; }
.search-form button { background: var(--acc); color: #000; border: none; border-radius: 6px; padding: 6px 12px; font-size: 0.85rem; font-weight: 600; cursor: pointer; }
.search-form button:hover { background: var(--cyan); }
.skillbar { display: flex; flex-wrap: wrap; gap: 6px; padding: 10px 20px; background: rgba(0,0,0,0.2); border-bottom: 1px solid var(--border); }
.sk { background: var(--panel); color: var(--muted); padding: 3px 8px; border-radius: 8px; border: 1px solid var(--border); font-size: 0.72rem; }
main { padding: 20px; max-width: 1100px; margin: 0 auto; }
.hero { display: flex; align-items: baseline; justify-content: space-between; flex-wrap: wrap; gap: 12px; padding: 16px 20px; background: linear-gradient(135deg, rgba(95,177,255,0.1), rgba(57,197,207,0.05)); border: 1px solid var(--border); border-radius: 10px; margin-bottom: 20px; }
.hero .ticker { font-size: 2rem; font-weight: 700; color: var(--acc); }
.hero .name { font-size: 1.3rem; color: var(--ink); margin-left: 8px; }
.hero .industry { color: var(--muted); font-size: 0.9rem; margin-top: 4px; }
.hero .price { font-size: 1.8rem; font-weight: 700; }
.hero .price.up { color: var(--red); }
.hero .price.down { color: var(--green); }
.summary-bar { display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 10px; margin-bottom: 20px; }
.card { background: var(--panel); border-radius: 8px; padding: 12px 14px; border: 1px solid var(--border); }
.card .k { color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.4px; }
.card .v { font-size: 1.2rem; font-weight: 700; margin-top: 4px; }
.card .v.pos { color: var(--red); }
.card .v.neg { color: var(--green); }
.card .v.muted { color: var(--muted); }
.section { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 16px 20px; margin-bottom: 14px; }
.section h2 { color: var(--acc); font-size: 1.05rem; margin: 0 0 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.section table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 0.85rem; margin: 4px 0 6px; background: rgba(0,0,0,0.15); border-radius: 6px; overflow: hidden; }
.section th, .section td { padding: 8px 10px; text-align: right; border-bottom: 1px solid rgba(255,255,255,0.05); }
.section th { color: var(--muted); font-weight: 600; background: rgba(255,255,255,0.03); text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.4px; }
.section td:first-child, .section th:first-child { text-align: left; }
.section tr:last-child td { border-bottom: none; }
.section td.num { font-variant-numeric: tabular-nums; font-weight: 500; }
.section td.pos { color: var(--red); font-weight: 600; }
.section td.neg { color: var(--green); font-weight: 600; }
.section .callout { background: linear-gradient(135deg, rgba(95,177,255,0.1), rgba(57,197,207,0.05)); border: 1px solid rgba(95,177,255,0.3); border-radius: 8px; padding: 10px 12px; margin: 8px 0; font-size: 0.88rem; line-height: 1.7; }
.section .callout .k { color: var(--muted); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.4px; margin-right: 4px; }
.section .callout .v { font-weight: 600; color: var(--ink); }
.section .callout .v.pos { color: var(--red); }
.section .callout .v.neg { color: var(--green); }
.section .meta { color: var(--muted); font-size: 0.78rem; margin-top: 6px; }
.tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }
.tag { display: inline-block; padding: 3px 8px; border-radius: 6px; font-size: 0.75rem; background: var(--border); color: var(--ink); }
/* tag-green / tag-red：語意命名（好/壞），CSS 顏色依台灣慣例
   tag-green = 正面/看多 → 紅色 / tag-red = 負面/看空 → 綠色 */
.tag-green { background: rgba(236,112,99,0.18); color: var(--red); }
.tag-red { background: rgba(88,214,141,0.18); color: var(--green); }
.tag-yellow { background: rgba(245,176,65,0.18); color: var(--amber); }
.tag-blue { background: rgba(95,177,255,0.18); color: var(--acc); }
.tag-cyan { background: rgba(57,197,207,0.18); color: var(--cyan); }
.tag-purple { background: rgba(188,140,255,0.18); color: var(--purple); }
.news-item { padding: 6px 0; border-bottom: 1px dashed rgba(255,255,255,0.06); font-size: 0.85rem; }
.news-item:last-child { border-bottom: none; }
.news-item a { color: var(--acc); text-decoration: none; }
.dd-prompt { background: rgba(57,197,207,0.06); border: 1px solid var(--cyan); border-radius: 6px; padding: 8px; margin-top: 8px; }
.dd-prompt pre { font-size: 0.72rem; line-height: 1.4; white-space: pre-wrap; word-wrap: break-word; max-height: 320px; overflow-y: auto; margin: 0; }
.copy-btn { background: var(--cyan); color: #000; border: none; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 0.75rem; font-weight: 600; margin-bottom: 4px; }
.copy-btn:hover { background: #fff; }
.obs { color: var(--ink); font-size: 0.88rem; line-height: 1.7; }
.obs li { padding: 3px 0; }
footer { padding: 24px; color: var(--muted); font-size: 0.8rem; text-align: center; }
.zen-bullish { color: var(--red); }
.zen-bearish { color: var(--green); }
.zen-neutral { color: var(--muted); }
.muted { color: var(--muted); }
.disclaimer { background: rgba(245,176,65,0.06); border: 1px solid var(--amber); border-radius: 6px; padding: 10px 14px; margin-top: 18px; color: var(--amber); font-size: 0.85rem; }
@media (max-width: 700px) {
  .hero { flex-direction: column; align-items: flex-start; }
  .summary-bar { grid-template-columns: repeat(2, 1fr); }
}
"""


def _esc(s) -> str:
    return _html_lib.escape(str(s)) if s else ""


def render_md_table(md: str) -> str:
    """Convert a markdown pipe table to a styled HTML table."""
    if not md or "|" not in md:
        return md
    lines = [l for l in md.split("\n") if l.strip().startswith("|")]
    if len(lines) < 2:
        return md
    sep_idx = None
    for i, l in enumerate(lines):
        if _re.match(r"^\|[\s\-:|]+\|?\s*$", l):
            sep_idx = i; break
    if sep_idx is None:
        return md
    header_cells = [c.strip() for c in lines[sep_idx - 1].strip("|").split("|")]
    body_rows = []
    for l in lines[sep_idx + 1:]:
        cells = [c.strip() for c in l.strip("|").split("|")]
        if len(cells) != len(header_cells):
            cells = (cells + [""] * len(header_cells))[:len(header_cells)]
        body_rows.append(cells)
    def cell_html(raw, is_first):
        s = raw
        is_bold = s.startswith("**") and s.endswith("**") and len(s) > 4
        if is_bold: s = s[2:-2]
        sign_cls = ""
        m = _re.match(r"^([+\-]?)([\d.,]+)(%?)$", s.strip())
        if m and not is_first:
            try:
                sign = m.group(1) or ""
                val = float((sign + m.group(2)).replace(",", ""))
                if val > 0: sign_cls = "pos"
                elif val < 0: sign_cls = "neg"
            except: pass
        s_esc = _esc(s)
        if is_bold: s_esc = f"<strong>{s_esc}</strong>"
        cls_parts = []
        if not is_first: cls_parts.append("num")
        if sign_cls: cls_parts.append(sign_cls)
        cls_attr = f' class="{" ".join(cls_parts)}"' if cls_parts else ""
        return f"<td{cls_attr}>{s_esc}</td>"
    out = ['<table>']
    out.append('<thead><tr>' + "".join(f"<th>{_esc(h)}</th>" for h in header_cells) + '</tr></thead>')
    out.append('<tbody>')
    for row in body_rows:
        out.append('<tr>' + "".join(cell_html(c, i == 0) for i, c in enumerate(row)) + '</tr>')
    out.append('</tbody></table>')
    return "\n".join(out)


def beautify(html_str: str) -> str:
    if not html_str: return html_str
    out, lines, i = [], html_str.split("\n"), 0
    while i < len(lines):
        l = lines[i]
        if l.lstrip().startswith("|") and i + 1 < len(lines) and _re.match(r"^\s*\|[\s\-:|]+\|?\s*$", lines[i+1]):
            block = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                block.append(lines[i]); i += 1
            out.append(render_md_table("\n".join(block)))
        else:
            out.append(l); i += 1
    return "\n".join(out)


SKILL_LINKS = [
    ("tw-invest-suite", "主控"), ("finlab", "ROE/營收"), ("finmind", "台股API"),
    ("tw-stock-info", "即時報價"), ("twse-api", "TWSE"), ("yahoo-finance", "Yahoo"),
    ("wall-street-tw-stock-analysis", "華爾街"), ("hedge-fund-expert-team", "大師"),
    ("stock-selection-decision", "選股"), ("minerva", "Minerva"),
    ("zen", "纏論"), ("ticker-dashboard", "Dashboard"),
    ("ai-telegram-research-check", "Research"), ("ui-development", "UI"),
]


def master_tags(ticker: str) -> str:
    """Generate hedge-fund master tags from DB + market_screen Candidate-style data."""
    try:
        # Use market_screen for current price + indicators
        # Build minimal Candidate-like dict from DB
        rows = db.ticker_history(ticker, days=1)
        if not rows:
            return ""
        latest = rows[-1]
        close = float(latest.get("Close") or 0)
        sma13 = float(latest.get("sma_13") or 0)
        sma27 = float(latest.get("sma_27") or 0)
        rsi14 = float(latest.get("rsi_14") or 0)
        foreign_net = int(latest.get("ForeignNet") or 0)

        # Get 240d return
        rets = db.long_term_returns_batch([ticker], str(latest.get("Date")))
        ret_240 = rets.get(ticker, {}).get("ret_240d", 0) or 0
        market_cap = close * int(latest.get("SharesOutstanding_shares") or 0) if latest.get("SharesOutstanding_shares") else 0

        tags = []
        if ret_240 > 0.3 and market_cap > 1e12:
            tags.append(f'<span class="tag tag-green">巴菲特</span> 240d +{ret_240:.0%}')
        if market_cap > 1e12:
            tags.append(f'<span class="tag tag-green">芒格</span> {market_cap/1e9:,.0f}億大型股')
        if ret_240 > 0.3:
            tags.append(f'<span class="tag tag-cyan">葛拉漢</span> 240d +{ret_240:.0%}')
        if ret_240 > 0.1 and rsi14 < 70:
            tags.append(f'<span class="tag tag-green">費雪</span> 動能延續')
        if ret_240 > 0.3:
            tags.append(f'<span class="tag tag-blue">達摩達蘭</span> 故事強，可建DCF')
        if ret_240 > 0.2 and market_cap > 3e11:
            tags.append(f'<span class="tag tag-green">帕布萊</span> 上行+{ret_240:.0%}/風險有限')
        # 短線
        if 50 <= rsi14 <= 65:
            tags.append(f'<span class="tag tag-green">RSI {rsi14:.0f} 甜蜜區</span>')
        elif rsi14 > 70:
            tags.append(f'<span class="tag tag-red">RSI {rsi14:.0f} 超買</span>')
        elif rsi14 < 30:
            tags.append(f'<span class="tag tag-green">RSI {rsi14:.0f} 超賣</span>')
        if sma13 and sma27 and close > sma13 > sma27:
            tags.append('<span class="tag tag-green">多頭排列</span>')
        elif sma13 and sma27 and close < sma13 < sma27:
            tags.append('<span class="tag tag-red">空頭排列</span>')
        else:
            tags.append('<span class="tag tag-yellow">盤整</span>')
        if foreign_net > 0:
            tags.append(f'<span class="tag tag-green">外資 +{foreign_net/1000:,.0f} 張</span>')
        elif foreign_net < 0:
            tags.append(f'<span class="tag tag-red">外資 {foreign_net/1000:,.0f} 張</span>')
        return '<div class="tags">' + "".join(tags) + '</div>'
    except Exception as e:
        return f'<div class="tags"><span class="tag tag-yellow">tags 生成失敗: {e}</span></div>'


def render_ticker_html(ticker: str) -> str:
    ticker = ticker.strip()
    print(f"  Fetching data for {ticker}...")
    data = a.fetch_all(ticker)

    info_rows = data.get("info") or []
    company_name = info_rows[0].get("stock_name", ticker) if info_rows else ticker
    industry = info_rows[0].get("industry_category", "—") if info_rows else "—"
    market = info_rows[0].get("type", "—") if info_rows else "—"

    # Latest price from DB
    rows = db.ticker_history(ticker, days=2)
    if rows:
        latest_row = rows[-1]
        close = float(latest_row.get("Close") or 0)
        prev_row = rows[-2] if len(rows) > 1 else {}
        prev_close = float(prev_row.get("Close") or 0)
        change_pct = (close - prev_close) / prev_close * 100 if prev_close else 0
    else:
        close = 0; prev_close = 0; change_pct = 0

    pcls = "up" if change_pct > 0 else "down" if change_pct < 0 else ""

    # Build sections
    sections = {
        "info": ("🏢 公司基本資料", a.section_info(data)),
        "price": ("💰 股價概況", a.section_price(data)),
        "technical": ("📈 技術面", a.section_technical(data)),
        "valuation": ("📊 估值", a.section_valuation(data)),
        "dividend": ("💵 配息歷史", a.section_dividend(data)),
        "institutional": ("🏛 三大法人 (近 30 日)", a.section_institutional(data)),
        "margin": ("💰 融資融券", a.section_margin(data)),
        "margin_maintenance": ("🛡 融資維持率", a.section_margin_maintenance(data)),
        "government_bank": ("🏦 八大行庫", a.section_government_bank(data)),
        "securities_lending": ("📜 借券成交", a.section_securities_lending(data)),
        "shareholding": ("👥 股權結構", a.section_shareholding(data)),
        "financial": ("📋 季度財報 (近 6 季)", a.section_financial(data)),
        "finlab_roe": ("🧬 ROE 趨勢", a.section_finlab_roe(data)),
        "finlab_revenue": ("📈 月營收 (近 12 月)", a.section_finlab_revenue(data)),
        "news": ("📰 近期新聞", a.section_news(data)),
        "observations": ("🎯 觀察重點", a.section_observations(data)),
    }

    # Build deep-dive prompt
    try:
        rets = db.long_term_returns_batch([ticker], str(latest_row.get("Date")) if rows else None)
        ret_240 = rets.get(ticker, {}).get("ret_240d", 0) or 0
    except:
        ret_240 = 0
    cand = ms.Candidate(
        ticker=ticker, name=company_name, industry=industry,
        close=close, change_pct=change_pct, volume=0,
        three_net=0, foreign_net=0, margin_balance=0, short_balance=0,
        foreign_ratio=0, sma13=0, sma27=0, sma54=0, rsi14=0, atr14=0, is_gap=0,
        excess_return_240d=ret_240,
    )
    try:
        dd_prompt = ddp.render_prompt(cand)
    except Exception as e:
        dd_prompt = f"(deep-dive prompt 生成失敗: {e})"
    dd_html = f'<div class="dd-prompt"><button class="copy-btn" onclick="copyText(this)">📋 複製</button><pre>{_esc(dd_prompt)}</pre></div>'

    # Hero
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    market_label = "上市" if market == "twse" else "上櫃" if market == "tpex" else market
    hero = f"""
    <div class="hero">
      <div>
        <div><span class="ticker">{_esc(ticker)}</span><span class="name">{_esc(company_name)}</span></div>
        <div class="industry">{_esc(industry)} · {market_label} · {now_str}</div>
      </div>
      <div class="price {pcls}">{close:,.2f} <small style="font-size:0.5em;color:var(--muted)">元</small> <span style="font-size:0.5em">{change_pct:+.2f}%</span></div>
    </div>
    """

    tags_html = master_tags(ticker)

    # Summary stats
    summary = []
    if close:
        summary.append(f'<div class="card"><div class="k">收盤</div><div class="v">{close:,.2f}</div></div>')
    if ret_240:
        cls = "pos" if ret_240 > 0 else "neg" if ret_240 < 0 else "muted"
        summary.append(f'<div class="card"><div class="k">240d 漲跌</div><div class="v {cls}">{ret_240:+.2%}</div></div>')
    if rows and latest_row.get("rsi_14"):
        summary.append(f'<div class="card"><div class="k">RSI(14)</div><div class="v">{latest_row["rsi_14"]:.1f}</div></div>')
    if rows and latest_row.get("ForeignNet") is not None:
        fn = int(latest_row["ForeignNet"] or 0)
        cls = "pos" if fn > 0 else "neg" if fn < 0 else "muted"
        summary.append(f'<div class="card"><div class="k">當日外資</div><div class="v {cls}">{fn:+,.0f}</div></div>')

    # Render sections
    sec_html_parts = []
    for key, (title, content) in sections.items():
        sec_html_parts.append(f'<div class="section"><h2>{title}</h2>{beautify(content)}</div>')
    sec_html_parts.append(f'<div class="section"><h2>🔬 Deep-dive (Perplexity Prompt)</h2>{dd_html}</div>')

    skillbar = "".join(f'<span class="sk" title="{_esc(d)}">{_esc(n)}</span>' for n, d in SKILL_LINKS)

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(ticker)} {_esc(company_name)} · 個股分析 · {datetime.now().strftime('%Y-%m-%d')}</title>
<style>{CSS}</style>
</head>
<body>
<div class="topbar">
  <div class="brand">📊 個股深度分析 <small>tw-invest-suite · single-stock deep-dive</small></div>
  <form class="search-form" action="https://groovelab.dev/analyze.html" method="get">
    <input name="ticker" placeholder="代號 e.g. 2324" maxlength="6" required>
    <button type="submit">分析 →</button>
  </form>
</div>
<div class="skillbar">{skillbar}</div>
<main>
  {hero}
  <div class="summary-bar">{"".join(summary)}</div>
  {tags_html}
  {"".join(sec_html_parts)}
  <div class="disclaimer">
    ⚠️ <strong>免責聲明</strong>：本報告由 AI 自動產生，僅供研究與教育用途。資料來源：MySQL <code>tw_elec.daily_data2_full</code> ＋ FinMind ＋ FinLab。
    篩選邏輯為啟發式，<strong>非投資建議</strong>。請於做決策前自行查證或諮詢持牌顧問。
  </div>
</main>
<footer>tw-invest-suite · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · Generated by Mavis</footer>
<script>
function copyText(btn) {{
  const pre = btn.nextElementSibling;
  const text = pre.textContent;
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(text).then(() => {{
      const orig = btn.textContent;
      btn.textContent = '✓ 已複製';
      setTimeout(() => btn.textContent = orig, 1500);
    }}).catch(err => {{
      fallbackCopy(text, btn);
    }});
  }} else {{
    fallbackCopy(text, btn);
  }}
}}
function fallbackCopy(text, btn) {{
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed';
  ta.style.opacity = '0';
  document.body.appendChild(ta);
  ta.select();
  try {{
    document.execCommand('copy');
    const orig = btn.textContent;
    btn.textContent = '✓ 已複製';
    setTimeout(() => btn.textContent = orig, 1500);
  }} catch(e) {{
    alert('複製失敗，請手動選取');
  }}
  document.body.removeChild(ta);
}}
</script>
</body>
</html>"""
    return html


def main():
    parser = argparse.ArgumentParser(description="Render single-ticker deep-dive HTML")
    parser.add_argument("ticker", help="Stock ticker (e.g. 2324)")
    parser.add_argument("--out", help="Output path (default: C:\\Groove-Lab\\analyze\\<ticker>.html)")
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    html = render_ticker_html(args.ticker)

    if args.no_save:
        print(html[:500])
        return

    # Two destinations: groovelab live + local reports
    groove_dir = Path(r"C:\Groove-Lab\analyze")
    groove_dir.mkdir(parents=True, exist_ok=True)
    groove_path = groove_dir / f"{args.ticker}.html"

    reports_dir = Path.home() / ".claude" / "skills" / "tw-invest-suite" / "reports"
    today = datetime.now().strftime("%Y-%m-%d")
    reports_path = reports_dir / f"analyze-{args.ticker}-{today}.html"

    if args.out:
        Path(args.out).write_text(html, encoding="utf-8")
        print(f"  → {args.out}")
    else:
        groove_path.write_text(html, encoding="utf-8")
        print(f"  → {groove_path}")
        reports_path.write_text(html, encoding="utf-8")
        print(f"  → {reports_path}")
    print(f"  size: {len(html):,} bytes")


if __name__ == "__main__":
    main()
