"""
HTML report renderer for market screen output.

Adds a self-contained .html file next to the .md report.
Uses inline CSS (no external deps) and Chart.js for inline bar charts.
"""
import html
import os
import sys
from datetime import datetime
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import market_screen as ms  # noqa: E402


CSS = """
:root {
  --bg: #0f1419;
  --card: #1a2028;
  --border: #2a3340;
  --text: #e1e4e8;
  --muted: #8b949e;
  --accent: #58a6ff;
  --green: #3fb950;
  --red: #f85149;
  --yellow: #d29922;
  --purple: #bc8cff;
  --cyan: #39c5cf;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, "Segoe UI", "Microsoft JhengHei", "PingFang TC", sans-serif;
  background: var(--bg); color: var(--text); line-height: 1.6; padding: 2rem 1rem;
}
.container { max-width: 1100px; margin: 0 auto; }
h1 { font-size: 2rem; margin-bottom: 0.5rem; color: var(--accent); }
h2 { font-size: 1.6rem; margin: 2.5rem 0 1rem; padding-bottom: 0.5rem;
     border-bottom: 1px solid var(--border); }
h3 { font-size: 1.25rem; margin: 1.5rem 0 0.75rem; color: var(--accent); }
h4 { font-size: 1rem; margin: 1rem 0 0.5rem; color: var(--purple); }
.meta { color: var(--muted); font-size: 0.9rem; margin-bottom: 2rem; }
.summary { background: var(--card); border: 1px solid var(--border);
          border-radius: 8px; padding: 1.5rem; margin-bottom: 2rem; }
.summary ul { padding-left: 1.5rem; }
.summary li { margin: 0.25rem 0; }
.bucket { background: var(--card); border: 1px solid var(--border);
          border-radius: 8px; padding: 1.5rem; margin: 1.5rem 0; }
.bucket h2 { border: none; margin-top: 0; }
.bucket-tag { display: inline-block; padding: 0.2rem 0.6rem;
              background: var(--accent); color: #000; border-radius: 4px;
              font-size: 0.85rem; margin-right: 0.5rem; vertical-align: middle; }
.picks { display: grid; grid-template-columns: 1fr; gap: 1rem; margin-top: 1rem; }
.pick { background: var(--bg); border: 1px solid var(--border);
       border-radius: 6px; padding: 1rem 1.25rem; }
.pick-long { border-left: 4px solid var(--green); }
.pick-short { border-left: 4px solid var(--yellow); }
.pick-head { display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 0.5rem; }
.pick-title { font-size: 1.1rem; font-weight: 600; }
.pick-ticker { color: var(--accent); margin-right: 0.5rem; }
.pick-price { font-size: 1.3rem; font-weight: 700; color: var(--green); }
.pick-price.down { color: var(--red); }
.pick-meta { color: var(--muted); font-size: 0.85rem; margin-top: 0.3rem; }
.pick-meta span { margin-right: 1rem; }
.pick-bullets { list-style: none; padding-left: 0; margin-top: 0.75rem; }
.pick-bullets li { padding: 0.3rem 0; border-bottom: 1px dashed var(--border);
                  font-size: 0.95rem; }
.pick-bullets li:last-child { border-bottom: none; }
.tag { display: inline-block; padding: 0.1rem 0.5rem; border-radius: 3px;
       font-size: 0.8rem; margin-right: 0.3rem; background: var(--border); color: var(--text); }
.tag-green { background: rgba(63,185,80,0.2); color: var(--green); }
.tag-yellow { background: rgba(210,153,34,0.2); color: var(--yellow); }
.tag-red { background: rgba(248,81,73,0.2); color: var(--red); }
.tag-blue { background: rgba(88,166,255,0.2); color: var(--accent); }
.tag-purple { background: rgba(188,140,255,0.2); color: var(--purple); }
.tag-cyan { background: rgba(57,197,207,0.2); color: var(--cyan); }
.zen-box { background: rgba(188,140,255,0.08); border: 1px solid var(--purple);
           border-radius: 6px; padding: 0.75rem 1rem; margin-top: 0.75rem; }
.zen-box h4 { color: var(--purple); margin-top: 0; margin-bottom: 0.4rem; font-size: 0.95rem; }
.zen-box p { font-size: 0.9rem; color: var(--text); }
.zen-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 0.5rem; margin-top: 0.5rem; }
.zen-cell { background: var(--bg); padding: 0.4rem 0.6rem; border-radius: 4px;
            border: 1px solid var(--border); }
.zen-cell-label { font-size: 0.75rem; color: var(--muted); }
.zen-cell-value { font-size: 0.95rem; font-weight: 600; }
.dd-details { margin-top: 0.75rem; background: rgba(57,197,207,0.06);
              border: 1px solid var(--cyan); border-radius: 6px; padding: 0.5rem 0.75rem; }
.dd-details summary { cursor: pointer; color: var(--cyan); font-size: 0.9rem;
                     user-select: none; list-style: none; }
.dd-details summary::-webkit-details-marker { display: none; }
.dd-details summary::before { content: "▶ "; font-size: 0.7rem; }
.dd-details[open] summary::before { content: "▼ "; }
.dd-prompt { position: relative; margin-top: 0.5rem; }
.dd-prompt pre { background: var(--bg); border: 1px solid var(--border);
                border-radius: 4px; padding: 0.75rem; font-size: 0.78rem;
                white-space: pre-wrap; word-wrap: break-word;
                max-height: 300px; overflow-y: auto; line-height: 1.4; }
.copy-btn { position: absolute; top: 0.4rem; right: 0.4rem;
            background: var(--cyan); color: #000; border: none;
            padding: 0.3rem 0.7rem; border-radius: 4px; cursor: pointer;
            font-size: 0.8rem; font-weight: 600; }
.copy-btn:hover { background: #fff; }
.news-box { background: rgba(88,166,255,0.06); border-left: 3px solid var(--accent);
            padding: 0.5rem 0.75rem; margin-top: 0.5rem; font-size: 0.9rem; }
.news-title { color: var(--accent); }
.disclaimer { background: var(--card); border: 1px solid var(--yellow);
              border-radius: 6px; padding: 1rem; margin-top: 2rem; color: var(--yellow); font-size: 0.9rem; }
table { border-collapse: collapse; width: 100%; margin-top: 0.5rem; }
th, td { padding: 0.4rem 0.6rem; text-align: left; border-bottom: 1px solid var(--border); font-size: 0.9rem; }
th { color: var(--muted); font-weight: 500; }
.footer { color: var(--muted); font-size: 0.8rem; text-align: center; margin-top: 2rem; }
@media (min-width: 700px) {
  .picks { grid-template-columns: repeat(3, 1fr); }
}
"""

BUCKET_INTRO = {
    "<100":       ("💰", "銅板股", "高波動、題材驅動，短中期操作為主"),
    "100-300":    ("💵", "中價股", "主流操作區間，流動性佳"),
    "300-1000":   ("💎", "中高價", "基本面與成長性兼具，適合中期持有"),
    ">1000":      ("🏆", "高價股", "龍頭企業、法人重倉、波動相對小"),
}


def _esc(s) -> str:
    return html.escape(str(s)) if s else ""


def render_pick(c: ms.Candidate, kind: str) -> str:
    """Render one pick as HTML. kind = 'long' or 'short'."""
    horizon_label = "長期" if kind == "long" else "短中期"
    css_class = "pick-long" if kind == "long" else "pick-short"
    badge_class = "tag-green" if kind == "long" else "tag-yellow"
    from deep_dive_prompts import render_prompt as build_dd_prompt  # local import
    dd_prompt = build_dd_prompt(c)
    dd_id = f"dd-{c.ticker}-{kind}"

    # Meta line
    meta_items = []
    if c.industry:
        meta_items.append(f"<span>🏷️ {_esc(c.industry)}</span>")
    if c.market_cap:
        meta_items.append(f"<span>💰 市值 {c.market_cap/1e9:,.0f} 億</span>")
    if c.excess_return_240d is not None:
        er = c.excess_return_240d
        cls = "tag-green" if er > 0 else "tag-red"
        meta_items.append(f'<span class="tag {cls}">240d {er:+.1%}</span>')
    meta_items.append(f"<span>📊 成交量 {c.volume/1e3:,.0f}K</span>")
    meta_items.append(f"<span>📅 {_esc(str(c.ticker))}</span>")
    meta_html = "".join(meta_items)

    # Bullets — apply hedge-fund-expert-team master tags
    bullets = []
    if kind == "long":
        # === Long-term: 6 masters ===
        er240 = c.excess_return_240d or 0
        er120 = c.excess_return_120d or 0
        cap = c.market_cap or 0
        cap_yi = cap / 1e9  # in 億

        # 1. 巴菲特 (Buffett): moat + ROE proxy via 240d strong return + large cap
        if er240 > 0.3 and cap > 1000e9:
            bullets.append(f'<span class="tag tag-green">巴菲特</span> 240d +{er240:.0%} + {cap_yi:,.0f} 億市值（護城河+長期複利）')
        elif er240 > 0.3:
            bullets.append(f'<span class="tag tag-green">巴菲特</span> 240d +{er240:.0%} 強勁長期動能')
        elif er240 > 0.1:
            bullets.append(f'<span class="tag tag-blue">巴菲特</span> 240d +{er240:.0%} 穩健')

        # 2. 芒格 (Munger): large, simple, predictable
        if cap > 1000e9:
            bullets.append(f'<span class="tag tag-green">芒格</span> {cap_yi:,.0f} 億大型股，符合「大型、可預測」')
        elif cap > 300e9:
            bullets.append(f'<span class="tag tag-blue">芒格</span> {cap_yi:,.0f} 億中型股，可研究')
        else:
            bullets.append(f'<span class="tag tag-yellow">芒格</span> {cap_yi:,.0f} 億小型股（注意波動）')

        # 3. 葛拉漢 (Graham): margin of safety
        if er240 < 0:
            bullets.append(f'<span class="tag tag-red">葛拉漢</span> 240d {er240:+.0%}，安全邊際不足')
        elif er240 < 0.1:
            bullets.append(f'<span class="tag tag-yellow">葛拉漢</span> 240d +{er240:.0%} 偏低，須算 DCF 找安全邊際')
        else:
            bullets.append(f'<span class="tag tag-cyan">葛拉漢</span> 240d +{er240:.0%} 合理，需 NCAV/Graham 數驗證')

        # 4. 費雪 (Fisher): scuttlebutt, growth quality
        if er120 > 0.2 and er240 > 0.3:
            bullets.append(f'<span class="tag tag-green">費雪</span> 短中期 (120d +{er120:.0%}) 與長期皆強，15 問正面')
        elif er120 > 0:
            bullets.append(f'<span class="tag tag-blue">費雪</span> 120d +{er120:.0%} 成長延續中')
        else:
            bullets.append(f'<span class="tag tag-yellow">費雪</span> 120d {er120:+.0%} 成長動能轉弱')

        # 5. 達摩達蘭 (Damodaran): DCF / story
        if er240 > 0.5:
            bullets.append(f'<span class="tag tag-green">達摩達蘭</span> 故事強：240d +{er240:.0%}，可建 DCF 估內在價值')
        elif er240 > 0:
            bullets.append(f'<span class="tag tag-blue">達摩達蘭</span> 故事中性偏多，須驗證 driver')
        else:
            bullets.append(f'<span class="tag tag-yellow">達摩達蘭</span> 故事需重寫，內在價值可能下修')

        # 6. 帕布萊 (Pabrai): Dhandho (heads I win, tails I don't lose much)
        if er240 > 0.2 and cap > 300e9:
            bullets.append(f'<span class="tag tag-green">帕布萊</span> 上行+{er240:.0%} / 風險有限（大型股）')
        elif er240 < -0.1:
            bullets.append(f'<span class="tag tag-red">帕布萊</span> {er240:+.0%} 不對稱下行，避免')
        else:
            bullets.append(f'<span class="tag tag-cyan">帕布萊</span> 風險／報酬比普通')

        # Supporting data
        if c.volume > 5_000_000:
            bullets.append(f'<span class="tag tag-cyan">💧 高流動性</span> {c.volume/1e6:.1f}M 股')
        elif c.volume > 1_000_000:
            bullets.append(f'<span class="tag tag-cyan">💧 中流動性</span> {c.volume/1e3:.0f}K 股')
        else:
            bullets.append(f'<span class="tag tag-yellow">⚠️ 低流動性</span> {c.volume/1e3:.0f}K 股')
        if c.foreign_ratio and c.foreign_ratio > 50:
            bullets.append(f'<span class="tag tag-cyan">🌍 外資</span> 持股 {c.foreign_ratio:.0f}%')
        bullets.append(f'<span class="tag">{_esc(c.industry or "—")}</span>')

    else:
        # === Short-term: 6 masters / analysts ===
        # 1. 凱西·伍德 (Cathie Wood): disruptive innovation, S-curve
        if c.excess_return_240d and c.excess_return_240d > 0.3:
            bullets.append(f'<span class="tag tag-green">凱西·伍德</span> 240d +{c.excess_return_240d:.0%} 創新動能')

        # 2. 伯里 (Michael Burry): contrarian, deep value
        if c.rsi14 < 30:
            bullets.append(f'<span class="tag tag-green">伯里</span> RSI {c.rsi14:.0f} 超賣，逆向進場訊號')
        elif c.rsi14 > 70:
            bullets.append(f'<span class="tag tag-yellow">伯里</span> RSI {c.rsi14:.0f} 超熱，避開')
        else:
            bullets.append(f'<span class="tag tag-cyan">伯里</span> RSI {c.rsi14:.0f} 中性，無逆向訊號')

        # 3. 德魯肯米勒 (Druckenmiller): macro, momentum
        if c.sma13 and c.sma27 and c.close > c.sma13 > c.sma27:
            bullets.append(f'<span class="tag tag-green">德魯肯米勒</span> 順勢：收盤&gt;SMA13({c.sma13:.0f})&gt;SMA27({c.sma27:.0f})')
        elif c.sma13 and c.close < c.sma13 < c.sma27:
            bullets.append(f'<span class="tag tag-red">德魯肯米勒</span> 逆勢：收盤&lt;SMA13&lt;SMA27')
        else:
            bullets.append(f'<span class="tag tag-yellow">德魯肯米勒</span> 趨勢糾結，方向未定')

        # 4. 林奇 (Lynch): growth, ten-bagger
        if c.excess_return_240d and c.excess_return_240d > 0.5:
            bullets.append(f'<span class="tag tag-green">林奇</span> 240d +{c.excess_return_240d:.0%} 十倍股潛力')
        elif c.excess_return_240d and c.excess_return_240d > 0:
            bullets.append(f'<span class="tag tag-blue">林奇</span> 240d +{c.excess_return_240d:.0%} 穩健成長')
        else:
            bullets.append(f'<span class="tag tag-red">林奇</span> 240d {c.excess_return_240d:+.0%}，迴避')

        # 5. 估值分析師 (Valuation analyst) — short tags
        if 50 <= c.rsi14 <= 65:
            bullets.append(f'<span class="tag tag-green">RSI {c.rsi14:.0f} 甜蜜區</span>')
        elif c.rsi14 > 70:
            bullets.append(f'<span class="tag tag-red">RSI {c.rsi14:.0f} 超買</span>')
        else:
            bullets.append(f'<span class="tag tag-yellow">RSI {c.rsi14:.0f} 動能偏弱</span>')

        # 6. 技術分析師: trend + volume
        if c.sma13 and c.sma27 and c.close > c.sma13 > c.sma27:
            bullets.append(f'<span class="tag tag-green">技術分析師</span> 多頭排列 收盤&gt;SMA13&gt;SMA27')
        if c.volume_burst == 1:
            bullets.append('<span class="tag tag-yellow">💥 量能爆發</span>')
        if c.kd_golden_cross == 1:
            bullets.append('<span class="tag tag-green">✝️ KD 黃金交叉</span>')
        if c.inv_first_in == 1:
            bullets.append('<span class="tag tag-yellow">🏦 法人首次進場</span>')
        if c.chip_score and c.chip_score > 50:
            bullets.append(f'<span class="tag tag-cyan">ChipScore {c.chip_score:.0f}</span>')

        # 7. 籌碼面：法人買賣
        if c.foreign_net and c.foreign_net > 0:
            bullets.append(f'<span class="tag tag-green">🌍 外資 +{c.foreign_net/1000:,.0f}K 張</span>')
        elif c.foreign_net and c.foreign_net < 0:
            bullets.append(f'<span class="tag tag-red">🌍 外資 {c.foreign_net/1000:,.0f}K 張</span>')

        # 8. 基本面：新聞情緒
        if c.news_sentiment_avg is not None and c.news_sentiment_avg > 0.3:
            bullets.append(f'<span class="tag tag-green">📰 情緒 {c.news_sentiment_avg:+.2f}</span> ({c.news_count_5d}則/5日)')
        elif c.news_sentiment_avg is not None and c.news_sentiment_avg < -0.3:
            bullets.append(f'<span class="tag tag-red">📰 情緒 {c.news_sentiment_avg:+.2f}</span> ({c.news_count_5d}則/5日)')

        # 9. 跳空
        if c.is_gap == 1 and c.change_pct > 0:
            bullets.append(f'<span class="tag tag-yellow">⬆️ 跳空 +{c.change_pct:.2f}%</span>')

        # 10. 流動性 (always)
        if c.volume > 5_000_000:
            bullets.append(f'<span class="tag tag-cyan">💧 高流動性</span> {c.volume/1e6:.1f}M 股')
        elif c.volume > 1_000_000:
            bullets.append(f'<span class="tag tag-cyan">💧 中流動性</span> {c.volume/1e3:.0f}K 股')
        else:
            bullets.append(f'<span class="tag tag-yellow">⚠️ 低流動性</span> {c.volume/1e3:.0f}K 股 (注意滑價)')

        # 11. 產業 (always)
        if c.industry:
            bullets.append(f'<span class="tag">{_esc(c.industry)}</span>')

    bullets_html = "".join(f"<li>{b}</li>" for b in bullets)

    # News headlines box
    news_html = ""
    if c.news_headlines:
        items = "".join(f'<div class="news-title">• {_esc(h)}</div>' for h in c.news_headlines[:3] if h)
        if items:
            news_html = f'<div class="news-box">{items}</div>'

    # Zen box (for short-term picks only)
    zen_html = ""
    if kind == "short":
        zen_html = render_zen_box(c)

    # Deep-dive prompt (collapsible)
    dd_html = f"""
    <details class="dd-details">
      <summary>🔬 <strong>Deep-dive Prompt</strong>（{_esc('Tiger Global' if (kind == 'short' or (c.excess_return_240d or 0) > 0.3) else 'Baupost')}）— 點擊展開，可複製到 Perplexity</summary>
      <div class="dd-prompt">
        <button class="copy-btn" onclick="copyPrompt('{dd_id}', this)">📋 複製</button>
        <pre id="{dd_id}">{_esc(dd_prompt)}</pre>
      </div>
    </details>
    """

    return f"""
    <div class="pick {css_class}">
      <div class="pick-head">
        <div>
          <div class="pick-title"><span class="pick-ticker">{_esc(c.ticker)}</span>{_esc(c.name)}</div>
          <div class="pick-meta">{meta_html}</div>
        </div>
        <div class="pick-price">{c.close:,.2f} <small style="font-size:0.5em;font-weight:400;color:var(--muted)">元</small></div>
      </div>
      <ul class="pick-bullets">{bullets_html}</ul>
      {zen_html}
      {news_html}
      {dd_html}
    </div>
    """


def render_zen_box(c: ms.Candidate) -> str:
    """Render a small Chanlun (纏論) structural read box for the pick.

    Uses real detector output from market_screen.zen_summary if available;
    otherwise shows a heuristic read.
    """
    if c.zen_summary:
        # Use the real detector output
        summary_lines = c.zen_summary.split("\n")
        # Render as a definition list
        cells = []
        for line in summary_lines:
            line = line.strip()
            if not line:
                continue
            # Split "**key**: value" into label + value
            if line.startswith("**") and "**：" in line:
                label, val = line.split("**：", 1)
                label = label.strip("*")
                val = val.strip()
                cells.append((label, val))
        cells_html = "".join(
            f'<div class="zen-cell"><div class="zen-cell-label">{_esc(label)}</div><div class="zen-cell-value">{_esc(val)}</div></div>'
            for label, val in cells
        )
        return f"""
        <div class="zen-box">
          <h4>🧘 纏論 (日 K) 結構速讀 <span class="tag tag-green" style="font-size:0.7rem">DETECTOR</span></h4>
          <p style="font-size:0.85rem;color:var(--muted);margin-bottom:0.5rem;">
            自動偵測分型／筆／中樞（120 日 K 線）
          </p>
          <div class="zen-grid">{cells_html}</div>
        </div>
        """

    # Fallback: heuristic read
    cells = []
    if c.close and c.sma13 and c.sma27 and c.sma54:
        if c.close > c.sma13 > c.sma27 > c.sma54:
            pos = "上升趨勢"
        elif c.close < c.sma13 < c.sma27 < c.sma54:
            pos = "下降趨勢"
        else:
            pos = "盤整/轉折"
        cells.append(("均線", pos))
    if c.rsi14:
        if c.rsi14 > 70:
            cells.append(("RSI", "超買"))
        elif c.rsi14 < 30:
            cells.append(("RSI", "超賣"))
        else:
            cells.append(("RSI", "中性"))
    if c.atr14:
        cells.append(("ATR(14)", f"{c.atr14:.1f}"))
    cells.append(("級別", "日 K"))

    cells_html = "".join(
        f'<div class="zen-cell"><div class="zen-cell-label">{_esc(label)}</div><div class="zen-cell-value">{_esc(val)}</div></div>'
        for label, val in cells
    )
    return f"""
    <div class="zen-box">
      <h4>🧘 纏論 (日 K) 結構速讀 <span class="tag tag-yellow" style="font-size:0.7rem">HEURISTIC</span></h4>
      <p style="font-size:0.85rem;color:var(--muted);">K 線資料不足，使用均線/RSI 推斷</p>
      <div class="zen-grid">{cells_html}</div>
    </div>
    """


def render_bucket(label: str, lo: int, hi: float,
                  longs: List[ms.Candidate], shorts: List[ms.Candidate]) -> str:
    emoji, name, tagline = BUCKET_INTRO.get(label, ("📊", label, ""))
    if hi == float("inf"):
        title = f"{emoji} {label} 元 — {name}"
    else:
        title = f"{emoji} {label} 元 — {name}"
    return f"""
    <div class="bucket">
      <h2>{title}</h2>
      <p style="color:var(--muted);margin-bottom:1rem">{_esc(tagline)}</p>

      <h3><span class="bucket-tag">📈 長期持有</span>基本面取向</h3>
      <div class="picks">
        {"".join(render_pick(c, "long") for c in longs)}
      </div>

      <h3 style="margin-top:1.5rem"><span class="bucket-tag" style="background:var(--yellow);color:#000">⚡ 短中期交易</span>技術 + 題材</h3>
      <div class="picks">
        {"".join(render_pick(c, "short") for c in shorts)}
      </div>
    </div>
    """


def render_html(result: Dict[str, Dict[str, List[ms.Candidate]]]) -> str:
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    db_date = ms.db.latest_date("daily_data2_full")
    total_picks = sum(len(v["long"]) + len(v["short"]) for v in result.values())
    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>台股全市場分價位掃描 — {today[:10]}</title>
<style>{CSS}</style>
</head>
<body>
<div class="container">
  <h1>📊 台股全市場分價位掃描報告</h1>
  <div class="meta">
    報告時間：{today} ｜ 資料庫日期：{db_date}<br>
    工具：<code>tw-invest-suite v0.3</code>（market screen mode）
  </div>

  <div class="summary">
    <h3>📋 掃描摘要</h3>
    <ul>
      <li>全市場股票：1,943 檔（TWSE + TPEx）</li>
      <li>本次推薦：<strong>{total_picks} 檔</strong></li>
      <li>分組：4 個價位（&lt;100、100-300、300-1000、&gt;1000）</li>
      <li>每組：3 檔長期（基本面）＋ 3 檔短中期（技術＋題材）</li>
    </ul>
  </div>

  {"".join(render_bucket(label, lo, hi, result[label]['long'], result[label]['short']) for label, lo, hi in ms.PRICE_BUCKETS if label in result)}

  <div class="disclaimer">
    ⚠️ <strong>免責聲明</strong>：本報告由 AI 自動產生，僅供研究與教育用途。
    資料來源：MySQL <code>tw_elec.daily_data2_full</code> ＋ <code>chipscore_daily</code> ＋ <code>stock_news</code>。
    篩選邏輯為啟發式，<strong>非投資建議</strong>。請於做決策前自行查證或諮詢持牌顧問。
  </div>

  <div class="footer">
    tw-invest-suite v0.3 · market screen mode · {today}
  </div>
</div>
<script>
function copyPrompt(id, btn) {{
  const text = document.getElementById(id).textContent;
  navigator.clipboard.writeText(text).then(() => {{
    if (btn) {{
      const orig = btn.textContent;
      btn.textContent = '✓ 已複製';
      setTimeout(() => btn.textContent = orig, 1500);
    }}
  }}).catch(err => {{
    alert('複製失敗：' + err);
  }});
}}
</script>
</body>
</html>"""


def save_html(result: Dict[str, Dict[str, List[ms.Candidate]]]) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    out_dir = os.path.expanduser("~/.claude/skills/tw-invest-suite/reports")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"market-screen-{today}.html")
    content = render_html(result)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


if __name__ == "__main__":
    result = ms.screen_market()
    path = save_html(result)
    print(f"[HTML] saved → {path}")
