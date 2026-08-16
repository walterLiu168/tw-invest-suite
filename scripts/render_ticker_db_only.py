"""
Render a single-ticker deep-dive HTML using ONLY local MySQL data.
No FinMind / FinLab API calls (free tier friendly).

This is the fast version used by daily_all_tickers.py to render 1,943 stocks
in ~10-15 minutes (4 workers parallel).
"""
import os
import sys
import html as _html_lib
import re as _re
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db_client as db
import market_screen as ms
import deep_dive_prompts as ddp
from render_ticker_html import (
    CSS, _esc, render_md_table, beautify, SKILL_LINKS, master_tags
)


# ---- DB-only section renderers (no API calls) ----

def _row_to_dict(r):
    """Convert DB row (dict-like) to plain dict."""
    return dict(r) if r else {}


def section_info_db(ticker: str) -> str:
    """公司基本資料 from industries map."""
    industry = db.industry_for(ticker)
    md = "| 項目 | 內容 |\n|---|---|\n"
    md += f"| 股票代號 | {ticker} |\n"
    md += f"| 產業別 | {industry or '—'} |\n"
    return md


def section_price_db(rows_2day: list) -> str:
    """股價概況 from daily_data2_full."""
    if not rows_2day:
        return "_查無股價資料_"
    latest = rows_2day[-1]
    prev = rows_2day[-2] if len(rows_2day) >= 2 else {}
    cur = float(latest.get("Close") or 0)
    prev_close = float(prev.get("Close") or 0)
    change = cur - prev_close
    pct = (change / prev_close * 100) if prev_close else 0
    high_52w = max(float(r.get("High") or 0) for r in rows_2day)
    low_52w = min(float(r.get("Low") or 0) for r in rows_2day) if rows_2day else 0
    # Actually only 2 days; use snapshot for 52w. Skip 52w if not avail.

    return (
        "| 項目 | 數值 |\n|---|---|\n"
        f"| 收盤價 | {cur:.2f} 元 |\n"
        f"| 漲跌 | {change:+.2f} ({pct:+.2f}%) |\n"
        f"| 開盤 | {latest.get('Open') or '—'} |\n"
        f"| 最高 | {latest.get('High') or '—'} |\n"
        f"| 最低 | {latest.get('Low') or '—'} |\n"
        f"| 成交量 | {int((latest.get('Volume') or 0)/1000):,} 張 |\n"
        f"| 資料日期 | {latest.get('Date')} |\n"
    )


def section_technical_db(latest_row: dict) -> str:
    """技術面 from daily_data2_full computed columns."""
    cur = float(latest_row.get("Close") or 0)
    sma13 = float(latest_row.get("sma_13") or 0)
    sma27 = float(latest_row.get("sma_27") or 0)
    sma54 = float(latest_row.get("sma_54") or 0)
    rsi14 = float(latest_row.get("rsi_14") or 0)
    atr14 = float(latest_row.get("atr_14") or 0)
    if not cur:
        return "_查無技術面資料_"
    if sma13 and sma27 and cur > sma13 > sma27:
        trend = "多頭排列，趨勢偏多"
    elif sma13 and sma27 and cur < sma13 < sma27:
        trend = "空頭排列，趨勢偏空"
    else:
        trend = "均線糾結，盤整觀望"
    rsi_label = "超買" if rsi14 > 70 else "超賣" if rsi14 < 30 else "中性"
    return (
        "| 指標 | 數值 |\n|---|---|\n"
        f"| 收盤價 | {cur:.2f} |\n"
        f"| MA13 | {sma13:.2f} |\n"
        f"| MA27 | {sma27:.2f} |\n"
        f"| MA54 | {sma54:.2f} |\n"
        f"| RSI(14) | {rsi14:.2f} ({rsi_label}) |\n"
        f"| ATR(14) | {atr14:.2f} |\n"
        f"\n趨勢判讀：**{trend}**\n"
    )


def section_valuation_db(latest_row: dict, ret_240: float) -> str:
    """估值 (limited — no P/E from DB)."""
    cur = float(latest_row.get("Close") or 0)
    md = "| 指標 | 數值 |\n|---|---|\n"
    md += f"| 收盤 | {cur:.2f} |\n"
    md += f"| 240d 漲跌 | {ret_240:+.2%} |\n"
    md += "| 本益比 (P/E) | _需 FinMind 訂閱 (本頁為 DB-only 版本) |\n"
    md += "| 殖利率 | _需 FinMind 訂閱 (本頁為 DB-only 版本) |\n"
    return md


def section_institutional_db(rows_30day: list) -> str:
    """三大法人 from daily_data2_full (近 10 日)."""
    if not rows_30day:
        return "_查無三大法人_"
    rows = rows_30day[-10:]
    md = "| 日期 | 外資 | 投信 | 自營 | 合計 |\n|---|---|---|---|---|\n"
    cum_f = cum_t = cum_d = 0
    for r in reversed(rows):
        f = float(r.get("ForeignNet") or 0) / 1000.0
        t = float(r.get("InvestmentNet") or 0) / 1000.0
        d = float(r.get("DealerNet") or 0) / 1000.0
        total = float(r.get("ThreeNet") or 0) / 1000.0
        cum_f += f; cum_t += t; cum_d += d
        d_str = str(r.get("Date"))[:10]
        sign = lambda v: f"{v:+,.0f}" if v else "0"
        md += f"| {d_str} | {sign(f)} | {sign(t)} | {sign(d)} | **{sign(total)}** |\n"
    md += f"\n**近 {len(rows)} 日累積**：外資 {cum_f:+,.0f} 張｜投信 {cum_t:+,.0f} 張｜自營 {cum_d:+,.0f} 張"
    return md


def section_margin_db(latest_row: dict) -> str:
    """融資融券 from daily_data2_full."""
    if not latest_row:
        return "_查無融資融券_"
    mb = int(latest_row.get("MarginBalance") or 0)
    ms = int(latest_row.get("ShortBalance") or 0)
    ratio = (mb / ms) if ms else None
    ratio_s = f"{ratio:.1f}" if ratio else "—"
    return (
        "_資料來源：MySQL `daily_data2_full` (DB-only 版，無 FinMind sponsor 個股融資維持率)_\n\n"
        "| 項目 | 融資 | 融券 |\n|---|---|---|\n"
        f"| 今日餘額 | **{mb:,}** 張 | **{ms:,}** 張 |\n"
        f"| 融資融券比 | {ratio_s} | — |\n"
    )


def section_news_db(ticker: str) -> str:
    """新聞 from stock_news table."""
    rows = db.recent_news(ticker, limit=5)
    if not rows:
        return "_查無近期新聞_"
    md = ""
    for r in rows:
        title = r.get("title", "—")
        source = r.get("source", "—")
        date = r.get("published_at") or r.get("date", "")
        if hasattr(date, "strftime"):
            date = date.strftime("%Y-%m-%d")
        else:
            date = str(date)[:10]
        link = r.get("link", "")
        if link:
            md += f"- **{date}** [{title}]({link}) — {source}\n"
        else:
            md += f"- **{date}** {title} — {source}\n"
    return md


def section_observations_db(latest_row: dict, ret_240: float) -> str:
    """觀察重點 (auto-generated from DB)."""
    cur = float(latest_row.get("Close") or 0)
    rsi14 = float(latest_row.get("rsi_14") or 0)
    foreign_net = float(latest_row.get("ForeignNet") or 0)
    bullets = []
    if cur:
        if rsi14 > 70:
            bullets.append(f"RSI {rsi14:.1f} 偏高，留意超買風險。")
        elif rsi14 < 30:
            bullets.append(f"RSI {rsi14:.1f} 偏低，留意是否落底。")
        else:
            bullets.append(f"RSI {rsi14:.1f} 中性。")
    if foreign_net > 0:
        bullets.append(f"當日三大法人合計買超 {foreign_net/1000:+,.0f} 張，籌碼面偏多。")
    elif foreign_net < 0:
        bullets.append(f"當日三大法人合計賣超 {-foreign_net/1000:,.0f} 張，籌碼面偏空。")
    if ret_240 > 0.3:
        bullets.append(f"240d 漲幅 {ret_240:+.1%}，長期動能強。")
    elif ret_240 < -0.1:
        bullets.append(f"240d 跌幅 {ret_240:+.1%}，長期動能弱。")
    if not bullets:
        bullets.append("_資料不足以產生觀察重點_")
    return "\n".join(f"- {b}" for b in bullets)


def render_ticker_html_db_only(ticker: str, snap: dict, ret_data: dict,
                                chip: dict, history: dict) -> str:
    """Render full HTML using pre-fetched DB data (no API calls).

    Args:
        ticker: e.g. "2324"
        snap: latest snapshot row from market_snapshot
        ret_data: {ret_240, ret_120, ret_60, ret_20} from long_term_returns_batch
        chip: {chip_score, volume_burst, kd_golden_cross, ...} from all_latest_chipscore
        history: {"30": [...], "120": [...], "all": [...]} from ticker_history
    """
    ticker = ticker.strip()
    if not snap:
        return None

    industry = db.industry_for(ticker)
    # Try to get company name from industries map (has 'company' field)
    all_ind = db.all_industries()
    ind_info = all_ind.get(ticker, {})
    company_name = ind_info.get("company") or ticker
    market = "twse" if len(ticker) == 4 else "tpex"  # rough guess

    close = float(snap.get("Close") or 0)
    prev_row = history.get("prev", {})
    prev_close = float(prev_row.get("Close") or 0) if prev_row else 0
    change_pct = (close - prev_close) / prev_close * 100 if prev_close else 0
    pcls = "up" if change_pct > 0 else "down" if change_pct < 0 else ""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    market_label = "上市" if market == "twse" else "上櫃" if market == "tpex" else market

    # Build sections
    sections = {
        "info": ("🏢 公司基本資料", section_info_db(ticker)),
        "price": ("💰 股價概況", section_price_db(history.get("recent", []))),
        "technical": ("📈 技術面", section_technical_db(snap)),
        "valuation": ("📊 估值 (DB 簡版)", section_valuation_db(snap, ret_data.get("ret_240d", 0) or 0)),
        "institutional": ("🏛 三大法人 (近 10 日)", section_institutional_db(history.get("30", []))),
        "margin": ("💰 融資融券", section_margin_db(snap)),
        "news": ("📰 近期新聞", section_news_db(ticker)),
        "observations": ("🎯 觀察重點", section_observations_db(snap, ret_data.get("ret_240d", 0) or 0)),
    }

    # Hero
    hero = f"""
    <div class="hero">
      <div>
        <div><span class="ticker">{_esc(ticker)}</span><span class="name">{_esc(company_name)}</span></div>
        <div class="industry">{_esc(industry)} · {market_label} · {now_str} · <span class="muted">DB-only 簡版</span></div>
      </div>
      <div class="price {pcls}">{close:,.2f} <small style="font-size:0.5em;color:var(--muted)">元</small> <span style="font-size:0.5em">{change_pct:+.2f}%</span></div>
    </div>
    """

    # Build tags from DB
    tags = []
    ret_240 = ret_data.get("ret_240d") or 0
    if ret_240 > 0.3 and snap.get("MarketCap"):
        tags.append(f'<span class="tag tag-green">巴菲特</span> 240d +{ret_240:.0%}')
    if ret_240 > 0.3:
        tags.append(f'<span class="tag tag-cyan">葛拉漢</span> 240d +{ret_240:.0%}')
    rsi14 = float(snap.get("rsi_14") or 0)
    if 50 <= rsi14 <= 65:
        tags.append(f'<span class="tag tag-green">RSI {rsi14:.0f} 甜蜜區</span>')
    elif rsi14 > 70:
        tags.append(f'<span class="tag tag-red">RSI {rsi14:.0f} 超買</span>')
    elif rsi14 < 30:
        tags.append(f'<span class="tag tag-green">RSI {rsi14:.0f} 超賣</span>')
    sma13 = float(snap.get("sma_13") or 0)
    sma27 = float(snap.get("sma_27") or 0)
    if sma13 and sma27 and close > sma13 > sma27:
        tags.append('<span class="tag tag-green">多頭排列</span>')
    elif sma13 and sma27 and close < sma13 < sma27:
        tags.append('<span class="tag tag-red">空頭排列</span>')
    else:
        tags.append('<span class="tag tag-yellow">盤整</span>')
    fn = float(snap.get("ForeignNet") or 0)
    if fn > 0:
        tags.append(f'<span class="tag tag-green">外資 +{fn/1000:,.0f} 張</span>')
    elif fn < 0:
        tags.append(f'<span class="tag tag-red">外資 {fn/1000:,.0f} 張</span>')
    if chip.get("chip_score") and chip["chip_score"] > 50:
        tags.append(f'<span class="tag tag-cyan">ChipScore {chip["chip_score"]:.0f}</span>')
    tags_html = '<div class="tags">' + "".join(tags) + '</div>' if tags else ""

    # Summary cards
    summary = []
    if close:
        summary.append(f'<div class="card"><div class="k">收盤</div><div class="v">{close:,.2f}</div></div>')
    if ret_240:
        cls = "pos" if ret_240 > 0 else "neg" if ret_240 < 0 else "muted"
        summary.append(f'<div class="card"><div class="k">240d</div><div class="v {cls}">{ret_240:+.2%}</div></div>')
    if rsi14:
        summary.append(f'<div class="card"><div class="k">RSI(14)</div><div class="v">{rsi14:.1f}</div></div>')
    if fn:
        cls = "pos" if fn > 0 else "neg" if fn < 0 else "muted"
        summary.append(f'<div class="card"><div class="k">當日外資</div><div class="v {cls}">{fn/1000:+,.0f}</div></div>')
    if chip.get("chip_score"):
        summary.append(f'<div class="card"><div class="k">ChipScore</div><div class="v">{chip["chip_score"]:.0f}</div></div>')

    # Deep-dive prompt (Tiger Global, basic version)
    cand = ms.Candidate(
        ticker=ticker, name=company_name, industry=industry or "",
        close=close, change_pct=change_pct, volume=int(snap.get("Volume") or 0),
        three_net=int(snap.get("ThreeNet") or 0), foreign_net=int(snap.get("ForeignNet") or 0),
        margin_balance=int(snap.get("MarginBalance") or 0),
        short_balance=int(snap.get("ShortBalance") or 0),
        foreign_ratio=0, sma13=sma13, sma27=sma27, sma54=float(snap.get("sma_54") or 0),
        rsi14=rsi14, atr14=float(snap.get("atr_14") or 0), is_gap=0,
        excess_return_240d=ret_240,
    )
    try:
        dd_prompt = ddp.render_prompt(cand)
    except Exception as e:
        dd_prompt = f"(deep-dive prompt 生成失敗: {e})"
    dd_html = f'<div class="dd-prompt"><button class="copy-btn" onclick="copyText(this)">📋 複製</button><pre>{_esc(dd_prompt)}</pre></div>'

    # Render all sections
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
<title>{_esc(ticker)} {now_str[:10]} · DB 簡版</title>
<style>{CSS}</style>
</head>
<body>
<div class="topbar">
  <div class="brand">📊 個股分析 <small>DB-only 簡版 · {now_str[:10]}</small></div>
  <form class="search-form" action="https://groovelab.dev/analyze.html" method="get">
    <input name="ticker" placeholder="代號" maxlength="6" required>
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
    ⚠️ <strong>DB-only 簡版</strong>：本頁面僅用 MySQL <code>tw_elec.daily_data2_full</code> 渲染（無 FinMind / FinLab API 呼叫）。<br>
    完整版（含 P/E、配息、季報、ROE、新聞、Perplexity deep-dive 等）請 <a href="https://groovelab.dev/analyze.html" style="color:inherit;text-decoration:underline">用 search bar 跑完整版</a>。<br>
    <strong>免責聲明</strong>：僅供研究與教育用途，<strong>非投資建議</strong>。
  </div>
</main>
<footer>tw-invest-suite · {now_str} · DB-only</footer>
<script>
function copyText(btn) {{
  const pre = btn.nextElementSibling;
  const text = pre.textContent;
  if (navigator.clipboard && navigator.clipboard.writeText) {{
    navigator.clipboard.writeText(text).then(() => {{
      const orig = btn.textContent;
      btn.textContent = '✓ 已複製';
      setTimeout(() => btn.textContent = orig, 1500);
    }}).catch(err => fallbackCopy(text, btn));
  }} else {{ fallbackCopy(text, btn); }}
}}
function fallbackCopy(text, btn) {{
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.position = 'fixed'; ta.style.opacity = '0';
  document.body.appendChild(ta); ta.select();
  try {{
    document.execCommand('copy');
    const orig = btn.textContent;
    btn.textContent = '✓ 已複製';
    setTimeout(() => btn.textContent = orig, 1500);
  }} catch(e) {{ alert('複製失敗'); }}
  document.body.removeChild(ta);
}}
</script>
</body>
</html>"""
    return html


# ---- Pre-fetch helpers for batch ----

def fetch_all_data_for_batch(tickers: list, workers: int = 4) -> dict:
    """Pre-fetch ALL data needed for batch rendering (3 queries)."""
    print(f"  Pre-fetching data for {len(tickers)} tickers (3 batch queries)...")
    target_date = db.latest_date("daily_data2_full")
    print(f"    target_date = {target_date}")

    # 1. Market snapshot (latest day for all tickers)
    snap_rows = db.market_snapshot(target_date)
    snap_map = {r["Ticker"]: r for r in snap_rows if r.get("Ticker")}

    # 2. Long-term returns
    rets_map = db.long_term_returns_batch(tickers, target_date)

    # 3. Chip scores
    chip_map = db.all_latest_chipscore(target_date)
    # also features (we use sma/rsi/atr from market_snapshot already)

    return {
        "target_date": target_date,
        "snap_map": snap_map,
        "rets_map": rets_map,
        "chip_map": chip_map,
    }


def fetch_history_for_ticker(ticker: str) -> dict:
    """Fetch history for a single ticker (recent + 30d)."""
    try:
        recent = db.ticker_history(ticker, days=2)
        h30 = db.ticker_history(ticker, days=35)
    except Exception as e:
        return {"recent": [], "30": [], "prev": {}, "err": str(e)}
    prev = recent[-2] if len(recent) >= 2 else {}
    return {"recent": recent, "30": h30[-30:], "prev": prev}
