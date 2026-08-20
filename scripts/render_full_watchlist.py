"""
Render the full deep-dive watchlist for groovelab.dev/picks.html.

For each of the 24 picks (4 price buckets × 6 picks):
  - Company info (FinMind stock_info)
  - Price snapshot (TWSE / TPEx)
  - Technicals (MA5/20/60, RSI, trend)
  - Valuation (P/E, P/B, dividend yield)
  - Three-major institutional (近 10 日)
  - Margin / short balance
  - Monthly revenue (FinLab — free tier may be limited)
  - ROE (FinLab)
  - News (5 latest)
  - Dividend history
  - Hedge-fund master tags (from market_screen)
  - Zen (Chanlun) structural read
  - Perplexity deep-dive prompt (Tiger Global / Baupost)

Layout:
  - Top: 14-skill navigation bar
  - Tabs: 4 price buckets (default open: <100)
  - Inside each tab: pick cards in 3-col grid, expandable to deep-dive
  - Each card links out to:
      * ticker-dashboard (single-stock dashboard)
      * wall-street-tw-stock-analysis (華爾街風格分析)
      * ai-telegram-research-check (研究流程)

Output:
  - C:\\Users\\icemo\\.claude\\skills\\tw-invest-suite\\reports\\watchlist-full-YYYY-MM-DD.html
  - C:\\Groove-Lab\\watchlist.html  (live, served by groovelab tunnel)
"""
import html
import re as _re
import os
import sys
import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date
from pathlib import Path
import pymysql

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_stock as a   # noqa: E402
import market_screen as ms  # noqa: E402
import deep_dive_prompts as ddp  # noqa: E402
import watchlist as wl  # noqa: E402
import db_client as db  # noqa: E402
import zen_analyzer as zen  # noqa: E402


SKILL_LINKS = [
    ("tw-invest-suite", "主控：個股深挖 + 市場掃描"),
    ("finlab", "台股量化交易（ROE／月營收）"),
    ("finmind", "台股／全球金融資料 API"),
    ("tw-stock-info", "即時報價／財報／技術（Fugle/FinMind）"),
    ("twse-api", "TWSE 官方 OpenAPI"),
    ("yahoo-finance", "Yahoo Finance 全球股票"),
    ("wall-street-tw-stock-analysis", "華爾街風格台股個股分析"),
    ("hedge-fund-expert-team", "18 位投資大師 + 6 位分析師"),
    ("stock-selection-decision", "選股決策工作流"),
    ("minerva", "Minerva 量化研究 workflow"),
    ("zen", "纏論技術分析"),
    ("ticker-dashboard", "AI-Telegram 個股儀表板"),
    ("ai-telegram-research-check", "台股 daily 研究流程"),
    ("ui-development", "AI-Telegram 總控 UI"),
]


CSS = """
:root { --bg:#0a0e1a; --panel:#131b2e; --ink:#e6ecf5; --muted:#8aa0c0; --acc:#5fb1ff; --green:#58d68d; --red:#ec7063; --amber:#f5b041; --purple:#bc8cff; --cyan:#39c5cf; --border:#1f2942; }
* { box-sizing: border-box; }
body { margin: 0; padding: 0; background: var(--bg); color: var(--ink); font-family: -apple-system, "Microsoft JhengHei", "Noto Sans TC", system-ui, sans-serif; }
.topbar { position: sticky; top: 0; z-index: 100; background: rgba(10, 14, 26, 0.95); backdrop-filter: blur(8px); border-bottom: 1px solid var(--border); padding: 12px 20px; }
.brand { font-size: 1.2rem; font-weight: 600; color: var(--acc); }
.brand small { color: var(--muted); font-weight: 400; font-size: 0.7rem; margin-left: 8px; }
.skillbar { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; font-size: 0.72rem; }
.skillbar .sk { background: var(--panel); color: var(--muted); padding: 3px 8px; border-radius: 8px; border: 1px solid var(--border); }
.tabs { display: flex; gap: 4px; background: var(--panel); border-radius: 8px; padding: 4px; margin: 16px 20px 0; overflow-x: auto; }
.tab { background: transparent; color: var(--muted); border: none; padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 0.9rem; font-weight: 500; white-space: nowrap; transition: all 0.15s; }
.tab:hover { color: var(--ink); }
.tab.active { background: var(--acc); color: #000; }
.tab .count { background: rgba(0,0,0,0.2); padding: 1px 6px; border-radius: 8px; font-size: 0.7rem; margin-left: 4px; }
main { padding: 20px; max-width: 1400px; margin: 0 auto; }
.tab-content { display: none; }
.tab-content.active { display: block; }
.bucket-title { font-size: 1.1rem; color: var(--acc); margin: 0 0 16px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.bucket-title small { color: var(--muted); font-weight: 400; font-size: 0.85rem; }
.pick-chips { display: flex; flex-wrap: wrap; gap: 4px; margin: 8px 0 6px; }
.chip { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.72rem; font-weight: 600; font-family: 'Consolas', monospace; border: 1px solid; }
.chip-pos { background: rgba(236,112,99,0.15); color: #ec7063; border-color: rgba(236,112,99,0.3); }
.chip-neu { background: rgba(245,176,65,0.15); color: #f5b041; border-color: rgba(245,176,65,0.3); }
.chip-neg { background: rgba(88,214,141,0.12); color: #58d68d; border-color: rgba(88,214,141,0.3); }
.pick-score { margin-left: auto; }
.summary-bar { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; margin-bottom: 20px; }
.card { background: var(--panel); border-radius: 8px; padding: 12px 14px; border: 1px solid var(--border); }
.card .k { color: var(--muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px; }
.card .v { font-size: 1.3rem; font-weight: 600; margin-top: 4px; }
.picks { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 16px; }
.pick { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
.pick-head { padding: 14px 16px; background: linear-gradient(135deg, rgba(95,177,255,0.1), rgba(57,197,207,0.05)); border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: baseline; flex-wrap: wrap; gap: 8px; }
.pick-head.long { border-left: 3px solid var(--green); }
.pick-head.short { border-left: 3px solid var(--amber); }
.pick-ticker { font-size: 1.1rem; font-weight: 700; color: var(--acc); }
.pick-name { color: var(--ink); font-weight: 500; }
.pick-price { font-size: 1.3rem; font-weight: 700; }
.pick-price.up { color: var(--green); }
.pick-price.down { color: var(--red); }
.pick-horizon { display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: 0.7rem; font-weight: 500; }
.pick-horizon.long { background: rgba(88,214,141,0.18); color: var(--green); }
.pick-horizon.short { background: rgba(245,176,65,0.18); color: var(--amber); }
.pick-body { padding: 12px 16px; }
.tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 10px; }
.tag { display: inline-block; padding: 2px 7px; border-radius: 4px; font-size: 0.72rem; background: var(--border); color: var(--ink); }
.tag-green { background: rgba(63,185,80,0.18); color: var(--green); }
.tag-red { background: rgba(236,112,99,0.18); color: var(--red); }
.tag-yellow { background: rgba(245,176,65,0.18); color: var(--amber); }
.tag-blue { background: rgba(95,177,255,0.18); color: var(--acc); }
.tag-cyan { background: rgba(57,197,207,0.18); color: var(--cyan); }
.tag-purple { background: rgba(188,140,255,0.18); color: var(--purple); }
.tabs2 { display: flex; gap: 2px; background: rgba(0,0,0,0.2); border-radius: 6px; padding: 2px; margin: 8px 0; }
.tabs2 button { background: transparent; color: var(--muted); border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer; font-size: 0.78rem; }
.tabs2 button.active { background: var(--acc); color: #000; }
.section { display: none; padding: 8px 0; font-size: 0.9rem; line-height: 1.6; }
.section.active { display: block; }
.section h5 { color: var(--muted); font-size: 0.72rem; text-transform: uppercase; margin: 10px 0 6px; letter-spacing: 0.6px; font-weight: 600; }
.section table { width: 100%; border-collapse: separate; border-spacing: 0; font-size: 0.85rem; margin: 4px 0 10px; background: rgba(0,0,0,0.15); border-radius: 6px; overflow: hidden; }
.section th, .section td { padding: 8px 10px; text-align: right; border-bottom: 1px solid rgba(255,255,255,0.05); }
.section th { color: var(--muted); font-weight: 600; background: rgba(255,255,255,0.03); text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.4px; }
.section td:first-child, .section th:first-child { text-align: left; }
.section tr:last-child td { border-bottom: none; }
.section tr:hover td { background: rgba(95,177,255,0.06); }
.section td.num { font-variant-numeric: tabular-nums; font-weight: 500; }
.section td.pos { color: var(--green); font-weight: 600; }
.section td.neg { color: var(--red); font-weight: 600; }
.section td.muted { color: var(--muted); }
.section .callout { background: linear-gradient(135deg, rgba(95,177,255,0.1), rgba(57,197,207,0.05)); border: 1px solid rgba(95,177,255,0.3); border-radius: 8px; padding: 10px 12px; margin: 8px 0; font-size: 0.85rem; line-height: 1.7; }
.section .callout .k { color: var(--muted); font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.4px; margin-right: 4px; }
.section .callout .v { font-weight: 600; color: var(--ink); }
.section .callout .v.pos { color: var(--green); }
.section .callout .v.neg { color: var(--red); }
.section .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 6px; margin: 6px 0 10px; }
.section .stat { background: rgba(255,255,255,0.04); border-radius: 6px; padding: 8px 10px; }
.section .stat .k { color: var(--muted); font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.4px; }
.section .stat .v { font-size: 0.95rem; font-weight: 700; margin-top: 2px; }
.section .stat .v.pos { color: var(--green); }
.section .stat .v.neg { color: var(--red); }
.section .summary-line { padding: 6px 0; border-top: 1px solid rgba(255,255,255,0.06); margin-top: 8px; font-size: 0.85rem; }
.zen-box { background: rgba(188,140,255,0.06); border: 1px solid var(--purple); border-radius: 6px; padding: 8px 10px; margin: 6px 0; font-size: 0.82rem; }
.zen-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 4px; margin-top: 4px; }
.zen-cell { background: rgba(0,0,0,0.2); padding: 4px 6px; border-radius: 4px; }
.zen-cell-label { font-size: 0.7rem; color: var(--muted); }
.zen-cell-value { font-size: 0.85rem; font-weight: 600; }
.zen-bullish { color: var(--green); }
.zen-bearish { color: var(--red); }
.zen-neutral { color: var(--muted); }
.news-item { padding: 4px 0; border-bottom: 1px dashed rgba(255,255,255,0.06); font-size: 0.8rem; }
.news-item:last-child { border-bottom: none; }
.news-item a { color: var(--acc); text-decoration: none; }
.dd-prompt { background: rgba(57,197,207,0.06); border: 1px solid var(--cyan); border-radius: 6px; padding: 8px; margin-top: 6px; }
.dd-prompt pre { font-size: 0.72rem; line-height: 1.4; white-space: pre-wrap; word-wrap: break-word; max-height: 280px; overflow-y: auto; margin: 0; }
.copy-btn { background: var(--cyan); color: #000; border: none; padding: 3px 8px; border-radius: 4px; cursor: pointer; font-size: 0.72rem; font-weight: 600; margin-bottom: 4px; }
.actions { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border); }
.actions a { color: var(--acc); font-size: 0.72rem; padding: 2px 8px; border: 1px solid var(--border); border-radius: 4px; text-decoration: none; }
.obs { color: var(--ink); font-size: 0.82rem; }
.obs li { padding: 2px 0; }
footer { padding: 24px; color: var(--muted); font-size: 0.8rem; text-align: center; }
.ret-up { color: var(--green); }
.ret-down { color: var(--red); }
.muted { color: var(--muted); }
@media (max-width: 700px) {
  .picks { grid-template-columns: 1fr; }
  .zen-grid { grid-template-columns: 1fr; }
  .summary-bar { grid-template-columns: repeat(2, 1fr); }
}
"""


# ---- helpers ----

def _esc(s) -> str:
    return html.escape(str(s)) if s else ""


def render_md_table(md: str) -> str:
    """Convert a markdown pipe table to a styled HTML table.
    Handles: | col1 | col2 |\n|---|---|...\n| v1 | v2 |...
    Cells with **text** become bold; +N/-N get pos/neg classes;
    first column is left-aligned, rest are right-aligned (numeric).
    """
    if not md or "|" not in md:
        return md
    lines = [l for l in md.split("\n") if l.strip().startswith("|")]
    if len(lines) < 2:
        return md
    # Detect separator row (|---|)
    sep_idx = None
    for i, l in enumerate(lines):
        if _re.match(r"^\|[\s\-:|]+\|?\s*$", l):
            sep_idx = i
            break
    if sep_idx is None:
        return md
    header_cells = [c.strip() for c in lines[sep_idx - 1].strip("|").split("|")]
    body_rows = []
    for l in lines[sep_idx + 1:]:
        cells = [c.strip() for c in l.strip("|").split("|")]
        if len(cells) != len(header_cells):
            cells = (cells + [""] * len(header_cells))[:len(header_cells)]
        body_rows.append(cells)

    def cell_html(raw: str, is_first: bool) -> str:
        # parse number
        s = raw
        # strip bold markers
        is_bold = s.startswith("**") and s.endswith("**") and len(s) > 4
        if is_bold: s = s[2:-2]
        # detect numeric for sign + class
        sign_cls = ""
        s_clean = s.strip()
        m = _re.match(r"^([+\-]?)([\d.,]+)(%?)$", s_clean)
        if m and not is_first:
            try:
                sign = m.group(1) or ""
                val = float((sign + m.group(2)).replace(",", ""))
                if val > 0: sign_cls = "pos"
                elif val < 0: sign_cls = "neg"
            except: pass
        # escape
        s_esc = _esc(s)
        # restore bold
        if is_bold: s_esc = f"<strong>{s_esc}</strong>"
        # decimal alignment: tabular-nums via .num class
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


def beautify_section_html(html_str: str) -> str:
    """Post-process a section's HTML: convert markdown tables to HTML tables,
    and wrap 'summary' lines that start with '- ' after a table into a callout.
    """
    if not html_str: return html_str
    # Find markdown table block: contiguous lines starting with |
    out = []
    lines = html_str.split("\n")
    i = 0
    while i < len(lines):
        l = lines[i]
        # detect start of a markdown table (line starts with | and next line is |---|)
        if l.lstrip().startswith("|") and i + 1 < len(lines) and _re.match(r"^\s*\|[\s\-:|]+\|?\s*$", lines[i + 1]):
            # collect table block
            block = []
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                block.append(lines[i])
                i += 1
            out.append(render_md_table("\n".join(block)))
        else:
            out.append(l)
            i += 1
    return "\n".join(out)


def _fmt_pct(v):
    if v is None: return "—"
    try:
        return f"{float(v)*100:+.2f}%"
    except (TypeError, ValueError):
        return "—"


def _fmt_price(v):
    if v is None: return "—"
    try:
        return f"{float(v):,.2f}"
    except (TypeError, ValueError):
        return "—"


def _fmt_int(v):
    if v is None: return "—"
    try:
        return f"{int(v):,.0f}"
    except (TypeError, ValueError):
        return "—"


def _signed(v, dec=0):
    if v is None: return "—"
    try:
        f = float(v)
        s = f"{abs(f):,.{dec}f}"
        return f"+{s}" if f > 0 else (f"-{s}" if f < 0 else s)
    except (TypeError, ValueError):
        return "—"


def _zen_class(bias: str) -> str:
    if not bias: return "zen-neutral"
    if "bull" in bias.lower() or "多" in bias: return "zen-bullish"
    if "bear" in bias.lower() or "空" in bias: return "zen-bearish"
    return "zen-neutral"


# ---- SVG chart helpers ----

def _svg_bar_chart(rows: list, value_keys: list, width: int = 480, height: int = 200,
                    labels: list = None, colors: list = None, title: str = "") -> str:
    """Clustered bar chart for time series. rows = [{date, k1, k2, ...}].
    Each bar group per row, multiple series side by side.
    """
    if not rows: return '<div class="muted">_無資料_</div>'
    if not colors: colors = ["#5fb1ff", "#58d68d", "#f5b041", "#bc8cff"]
    if not labels: labels = value_keys

    n = len(rows)
    n_series = len(value_keys)
    pad_l, pad_r, pad_t, pad_b = 40, 12, 18, 28
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    group_w = plot_w / n
    bar_w = group_w / (n_series + 1)  # +1 for spacing

    # find max abs value for y scale
    max_abs = 1.0
    for r in rows:
        for k in value_keys:
            v = r.get(k) or 0
            max_abs = max(max_abs, abs(v))
    # round up to nice number
    import math
    ymax = math.ceil(max_abs / 1000) * 1000
    ymin = -ymax

    parts = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
             f'style="width:100%;height:auto;display:block;background:rgba(0,0,0,0.15);border-radius:4px;margin:6px 0;">']
    if title:
        parts.append(f'<text x="{width/2}" y="12" text-anchor="middle" fill="#8aa0c0" font-size="10">{_esc(title)}</text>')

    # zero line
    y0 = pad_t + plot_h * (ymax / (ymax - ymin))
    parts.append(f'<line x1="{pad_l}" y1="{y0:.1f}" x2="{width-pad_r}" y2="{y0:.1f}" stroke="#3a4a6a" stroke-width="0.5" stroke-dasharray="2,2"/>')

    # y-axis labels (3 levels: +max, 0, -max)
    for v, lab in [(ymax, f"+{ymax:,.0f}"), (0, "0"), (-ymax, f"-{ymax:,.0f}")]:
        y = pad_t + plot_h * ((ymax - v) / (ymax - ymin))
        parts.append(f'<text x="{pad_l-4}" y="{y+3:.1f}" text-anchor="end" fill="#8aa0c0" font-size="9">{lab}</text>')
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" stroke="#1f2942" stroke-width="0.3"/>')

    # bars
    for i, r in enumerate(rows):
        gx = pad_l + i * group_w + bar_w / 2
        for s_i, k in enumerate(value_keys):
            v = r.get(k) or 0
            if v == 0: continue
            color = colors[s_i % len(colors)]
            bar_x = gx + s_i * bar_w
            # map value to height
            h = abs(v) / ymax * (plot_h / 2)
            if v >= 0:
                y = y0 - h
                rect_h = h
            else:
                y = y0
                rect_h = h
            parts.append(f'<rect x="{bar_x:.1f}" y="{y:.1f}" width="{bar_w*0.92:.1f}" height="{max(rect_h, 1):.1f}" '
                         f'fill="{color}" opacity="0.85" rx="1">'
                         f'<title>{_esc(labels[s_i])} {_esc(str(r.get("date", "")))}: {v:+,.0f}</title></rect>')
        # x-axis date label
        d = r.get("date", "")
        if hasattr(d, "strftime"):
            d_short = d.strftime("%m-%d")
        else:
            d = str(d)
            if " " in d: d = d.split(" ")[0]
            d_short = d[5:] if len(d) >= 10 else d
        parts.append(f'<text x="{gx + (n_series*bar_w)/2:.1f}" y="{height-12}" text-anchor="middle" fill="#8aa0c0" font-size="8">{d_short}</text>')

    # legend
    legend_y = height - 4
    leg_x = pad_l
    for s_i, lab in enumerate(labels):
        color = colors[s_i % len(colors)]
        parts.append(f'<rect x="{leg_x}" y="{legend_y-7}" width="8" height="8" fill="{color}" opacity="0.85" rx="1"/>')
        parts.append(f'<text x="{leg_x+11}" y="{legend_y}" fill="#8aa0c0" font-size="8">{_esc(lab)}</text>')
        leg_x += 12 + len(lab) * 5 + 8

    parts.append('</svg>')
    return "".join(parts)


def _svg_line_chart(series: dict, width: int = 480, height: int = 200,
                     dates: list = None, title: str = "", y_label: str = "價格", n_total: int = None) -> str:
    """Multi-series line chart. series = {name: [(x_idx, value), ...]}.
    n_total: total x-axis points (defaults to max len of series).
    """
    if not series: return '<div class="muted">_無資料_</div>'

    n = n_total or max(len(v) for v in series.values())
    if n == 0: return '<div class="muted">_無資料_</div>'
    pad_l, pad_r, pad_t, pad_b = 42, 12, 18, 28
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    # collect all values for y scale
    all_vals = []
    for vals in series.values():
        for _, v in vals:
            if v is not None: all_vals.append(v)
    if not all_vals: return '<div class="muted">_無資料_</div>'

    ymin = min(all_vals)
    ymax = max(all_vals)
    yrange = ymax - ymin if ymax > ymin else 1
    # add 5% padding
    ymin -= yrange * 0.05
    ymax += yrange * 0.05
    yrange = ymax - ymin

    colors = {"收盤": "#5fb1ff", "MA5": "#f5b041", "MA13": "#58d68d", "MA27": "#bc8cff", "MA54": "#ec7063", "RSI(14)": "#39c5cf"}
    palette = ["#5fb1ff", "#f5b041", "#58d68d", "#bc8cff", "#ec7063", "#39c5cf", "#8b949e"]

    parts = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
             f'style="width:100%;height:auto;display:block;background:rgba(0,0,0,0.15);border-radius:4px;margin:6px 0;">']
    if title:
        parts.append(f'<text x="{width/2}" y="12" text-anchor="middle" fill="#8aa0c0" font-size="10">{_esc(title)}</text>')

    def x_pos(i):
        return pad_l + (i / max(1, n - 1)) * plot_w

    def y_pos(v):
        return pad_t + (1 - (v - ymin) / yrange) * plot_h

    # y grid + labels (5 ticks)
    for t in range(6):
        v = ymin + yrange * t / 5
        y = y_pos(v)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" stroke="#1f2942" stroke-width="0.3"/>')
        parts.append(f'<text x="{pad_l-4}" y="{y+3:.1f}" text-anchor="end" fill="#8aa0c0" font-size="8">{v:.0f}</text>')

    # x labels (dates)
    if dates and len(dates) == n:
        idxs = [0, n // 4, n // 2, 3 * n // 4, n - 1]
        for i in idxs:
            d = dates[i]
            if hasattr(d, "strftime"):
                d_short = d.strftime("%m-%d")
            elif isinstance(d, str) and len(d) >= 10:
                d_short = d[5:]  # MM-DD
            else:
                d_short = str(d)
            parts.append(f'<text x="{x_pos(i):.1f}" y="{height-12}" text-anchor="middle" fill="#8aa0c0" font-size="8">{d_short}</text>')

    # plot each series
    for s_i, (name, vals) in enumerate(series.items()):
        color = colors.get(name, palette[s_i % len(palette)])
        pts = []
        for i, (x_i, v) in enumerate(vals):
            if v is None: continue
            pts.append(f"{x_pos(i):.1f},{y_pos(v):.1f}")
        if not pts: continue
        # path
        path_d = "M " + " L ".join(pts)
        parts.append(f'<path d="{path_d}" fill="none" stroke="{color}" stroke-width="1.4" stroke-linejoin="round"/>')
        # dots (last point only)
        if vals:
            last = [v for v in vals if v[1] is not None]
            if last:
                i, v = last[-1]
                parts.append(f'<circle cx="{x_pos(i):.1f}" cy="{y_pos(v):.1f}" r="2.5" fill="{color}">'
                             f'<title>{name} 最新: {v:.2f}</title></circle>')

    # legend
    legend_y = height - 4
    leg_x = pad_l
    for s_i, name in enumerate(series.keys()):
        color = colors.get(name, palette[s_i % len(palette)])
        parts.append(f'<rect x="{leg_x}" y="{legend_y-7}" width="8" height="8" fill="{color}" rx="1"/>')
        parts.append(f'<text x="{leg_x+11}" y="{legend_y}" fill="#8aa0c0" font-size="8">{_esc(name)}</text>')
        leg_x += 12 + len(name) * 5 + 8

    parts.append('</svg>')
    return "".join(parts)


def _compute_rsi(closes: list, period: int = 14) -> list:
    """Return RSI values list (same length as closes, first period-1 are None)."""
    rsi = [None] * len(closes)
    if len(closes) < period + 1: return rsi
    gains, losses = [], []
    for i in range(1, period + 1):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_g = sum(gains) / period
    avg_l = sum(losses) / period
    rs = avg_g / avg_l if avg_l else 100
    rsi[period] = 100 - (100 / (1 + rs))
    for i in range(period + 1, len(closes)):
        diff = closes[i] - closes[i - 1]
        g = max(diff, 0)
        l = max(-diff, 0)
        avg_g = (avg_g * (period - 1) + g) / period
        avg_l = (avg_l * (period - 1) + l) / period
        rs = avg_g / avg_l if avg_l else 100
        rsi[i] = 100 - (100 / (1 + rs))
    return rsi


def _svg_candlestick(ohlc: list, width: int = 520, height: int = 220,
                     dates: list = None, title: str = "",
                     zen_overlay: dict = None) -> str:
    """Candlestick chart. ohlc = [{date, open, high, low, close}, ...].
    zen_overlay = {center_low, center_high, center_start_date, center_end_date} optional.
    """
    if not ohlc or len(ohlc) < 5: return '<div class="muted">_K 線資料不足_</div>'
    pad_l, pad_r, pad_t, pad_b = 42, 12, 18, 30
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    n = len(ohlc)

    highs = [float(r.get("high") or 0) for r in ohlc]
    lows = [float(r.get("low") or 0) for r in ohlc]
    ymax = max(highs)
    ymin = min(lows)
    yrange = ymax - ymin if ymax > ymin else 1
    ymin -= yrange * 0.03
    ymax += yrange * 0.03
    yrange = ymax - ymin

    def x_pos(i): return pad_l + (i / max(1, n - 1)) * plot_w
    def y_pos(v): return pad_t + (1 - (v - ymin) / yrange) * plot_h

    candle_w = max(2, plot_w / n * 0.65)

    parts = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
             f'style="width:100%;height:auto;display:block;background:rgba(0,0,0,0.15);border-radius:4px;margin:6px 0;">']
    if title:
        parts.append(f'<text x="{width/2}" y="12" text-anchor="middle" fill="#8aa0c0" font-size="10">{_esc(title)}</text>')

    # y grid
    for t in range(6):
        v = ymin + yrange * t / 5
        y = y_pos(v)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" stroke="#1f2942" stroke-width="0.3"/>')
        parts.append(f'<text x="{pad_l-4}" y="{y+3:.1f}" text-anchor="end" fill="#8aa0c0" font-size="8">{v:.1f}</text>')

    # x labels (5 ticks)
    for i in [0, n // 4, n // 2, 3 * n // 4, n - 1]:
        d = ohlc[i].get("date", "")
        if hasattr(d, "strftime"): d_short = d.strftime("%m-%d")
        elif isinstance(d, str) and len(d) >= 10: d_short = d[5:]
        else: d_short = str(d)
        parts.append(f'<text x="{x_pos(i):.1f}" y="{height-12}" text-anchor="middle" fill="#8aa0c0" font-size="8">{d_short}</text>')

    # zen center overlay (rectangle)
    if zen_overlay:
        cl = zen_overlay.get("center_low")
        ch = zen_overlay.get("center_high")
        cs = zen_overlay.get("center_start_idx")
        ce = zen_overlay.get("center_end_idx")
        if cl is not None and ch is not None and cs is not None and ce is not None:
            x1 = x_pos(cs)
            x2 = x_pos(ce)
            y1 = y_pos(ch)
            y2 = y_pos(cl)
            parts.append(f'<rect x="{x1:.1f}" y="{y1:.1f}" width="{x2-x1:.1f}" height="{y2-y1:.1f}" '
                         f'fill="#bc8cff" fill-opacity="0.18" stroke="#bc8cff" stroke-width="0.6" stroke-dasharray="2,2"/>')
            parts.append(f'<text x="{(x1+x2)/2:.1f}" y="{y1-2:.1f}" text-anchor="middle" fill="#bc8cff" font-size="8">中樞 {cl:.1f} - {ch:.1f}</text>')

    # candles
    for i, r in enumerate(ohlc):
        o = float(r.get("open") or 0)
        h = float(r.get("high") or 0)
        l = float(r.get("low") or 0)
        c = float(r.get("close") or 0)
        if not all([o, h, l, c]): continue
        x = x_pos(i)
        up = c >= o
        color = "#58d68d" if up else "#ec7063"
        # wick
        parts.append(f'<line x1="{x:.1f}" y1="{y_pos(h):.1f}" x2="{x:.1f}" y2="{y_pos(l):.1f}" stroke="{color}" stroke-width="0.8"/>')
        # body
        body_top = y_pos(max(o, c))
        body_bot = y_pos(min(o, c))
        body_h = max(1, body_bot - body_top)
        parts.append(f'<rect x="{x-candle_w/2:.1f}" y="{body_top:.1f}" width="{candle_w:.1f}" height="{body_h:.1f}" fill="{color}" opacity="0.9" rx="0.5">'
                     f'<title>{_esc(str(r.get("date", "")))[:10]} O:{o:.2f} H:{h:.2f} L:{l:.2f} C:{c:.2f}</title></rect>')

    # buy/sell markers (from zen_overlay)
    if zen_overlay:
        for marker in zen_overlay.get("markers", []):
            idx = marker.get("idx")
            kind = marker.get("kind")  # "buy" or "sell"
            price = marker.get("price")
            if idx is None or price is None: continue
            x = x_pos(idx)
            y = y_pos(price)
            if kind == "buy":
                sym = "▲"
                color = "#58d68d"
                y_offset = -8
            else:
                sym = "▼"
                color = "#ec7063"
                y_offset = 12
            parts.append(f'<text x="{x:.1f}" y="{y+y_offset:.1f}" text-anchor="middle" fill="{color}" font-size="11" font-weight="700">{sym}</text>')

    parts.append('</svg>')
    return "".join(parts)


def _svg_horizontal_bars(items: list, width: int = 480, height: int = 180,
                          title: str = "", value_fmt: str = "+.1%") -> str:
    """Horizontal bar chart. items = [{label, value, color?, suffix?}]"""
    if not items: return '<div class="muted">_無資料_</div>'
    pad_l, pad_r, pad_t, pad_b = 70, 60, 18, 16
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    n = len(items)
    bar_h = plot_h / n * 0.7
    gap = plot_h / n * 0.3

    abs_vals = [abs(it.get("value") or 0) for it in items]
    max_abs = max(abs_vals) if abs_vals else 1
    if max_abs == 0: max_abs = 1

    parts = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
             f'style="width:100%;height:auto;display:block;background:rgba(0,0,0,0.15);border-radius:4px;margin:6px 0;">']
    if title:
        parts.append(f'<text x="{width/2}" y="12" text-anchor="middle" fill="#8aa0c0" font-size="10">{_esc(title)}</text>')

    # zero line
    zero_x = pad_l + plot_w / 2
    parts.append(f'<line x1="{zero_x:.1f}" y1="{pad_t}" x2="{zero_x:.1f}" y2="{height-pad_b}" stroke="#3a4a6a" stroke-width="0.5" stroke-dasharray="2,2"/>')

    for i, it in enumerate(items):
        v = it.get("value") or 0
        label = it.get("label", "")
        color = it.get("color") or ("#58d68d" if v > 0 else "#ec7063" if v < 0 else "#8aa0c0")
        y = pad_t + i * (bar_h + gap) + gap / 2
        bar_w = abs(v) / max_abs * (plot_w / 2)
        if v >= 0:
            x = zero_x
        else:
            x = zero_x - bar_w
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(bar_w, 1):.1f}" height="{bar_h:.1f}" fill="{color}" opacity="0.85" rx="1">'
                     f'<title>{_esc(label)}: {v}</title></rect>')
        # label
        parts.append(f'<text x="{pad_l-6}" y="{y + bar_h/2 + 3:.1f}" text-anchor="end" fill="#8aa0c0" font-size="9">{_esc(label)}</text>')
        # value (after bar)
        val_str = f"{v*100:+.1f}%" if value_fmt == "+.1%" else f"{v:.1f}"
        text_x = zero_x + bar_w + 4 if v >= 0 else zero_x - bar_w - 4
        anchor = "start" if v >= 0 else "end"
        parts.append(f'<text x="{text_x:.1f}" y="{y + bar_h/2 + 3:.1f}" text-anchor="{anchor}" fill="{color}" font-size="9" font-weight="600">{val_str}</text>')

    parts.append('</svg>')
    return "".join(parts)


def _svg_grouped_bars(categories: list, series: dict, width: int = 480, height: int = 200,
                       title: str = "", value_fmt: str = "{:.1f}") -> str:
    """Grouped vertical bar chart. categories = [labels on x-axis].
    series = {name: [values, ...]} with same length as categories.
    """
    if not categories or not series: return '<div class="muted">_無資料_</div>'
    pad_l, pad_r, pad_t, pad_b = 42, 12, 18, 30
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    n = len(categories)
    n_series = len(series)
    group_w = plot_w / n
    bar_w = group_w / (n_series + 0.5)

    all_vals = []
    for vals in series.values():
        for v in vals:
            if v is not None: all_vals.append(v)
    if not all_vals: return '<div class="muted">_無資料_</div>'
    vmax = max(all_vals)
    vmin = min(all_vals)
    if vmax == vmin: vmax = vmin + 1
    vmax *= 1.1
    if vmin < 0: vmin *= 1.1
    yrange = vmax - vmin

    def y_pos(v): return pad_t + (1 - (v - vmin) / yrange) * plot_h

    palette = ["#5fb1ff", "#58d68d", "#f5b041", "#bc8cff", "#ec7063", "#39c5cf"]
    colors = {n: palette[i % len(palette)] for i, n in enumerate(series.keys())}

    parts = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
             f'style="width:100%;height:auto;display:block;background:rgba(0,0,0,0.15);border-radius:4px;margin:6px 0;">']
    if title:
        parts.append(f'<text x="{width/2}" y="12" text-anchor="middle" fill="#8aa0c0" font-size="10">{_esc(title)}</text>')

    # zero line if vmin < 0
    if vmin < 0:
        zy = y_pos(0)
        parts.append(f'<line x1="{pad_l}" y1="{zy:.1f}" x2="{width-pad_r}" y2="{zy:.1f}" stroke="#3a4a6a" stroke-width="0.5" stroke-dasharray="2,2"/>')

    # y grid
    for t in range(5):
        v = vmin + yrange * t / 4
        y = y_pos(v)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" stroke="#1f2942" stroke-width="0.3"/>')
        parts.append(f'<text x="{pad_l-4}" y="{y+3:.1f}" text-anchor="end" fill="#8aa0c0" font-size="8">{v:.0f}</text>')

    # bars
    for i, cat in enumerate(categories):
        gx = pad_l + i * group_w
        for s_i, (name, vals) in enumerate(series.items()):
            if i >= len(vals) or vals[i] is None: continue
            v = vals[i]
            x = gx + s_i * bar_w + bar_w * 0.1
            color = colors[name]
            if v >= 0:
                y = y_pos(v)
                h = y_pos(0) - y if vmin < 0 else pad_t + plot_h - y
                if vmin >= 0: h = (pad_t + plot_h) - y
                else: h = y_pos(0) - y
                h = max(1, h)
                y_top = y
            else:
                y = y_pos(0)
                h = y_pos(v) - y_pos(0)
                h = max(1, h)
                y_top = y_pos(v)
            parts.append(f'<rect x="{x:.1f}" y="{y_top:.1f}" width="{bar_w*0.9:.1f}" height="{h:.1f}" fill="{color}" opacity="0.85" rx="1">'
                         f'<title>{_esc(name)} {_esc(str(cat))}: {v:.1f}</title></rect>')
        # x label
        parts.append(f'<text x="{gx + group_w/2:.1f}" y="{height-12}" text-anchor="middle" fill="#8aa0c0" font-size="8">{_esc(str(cat))[:10]}</text>')

    # legend
    legend_y = height - 4
    leg_x = pad_l
    for name, c in colors.items():
        parts.append(f'<rect x="{leg_x}" y="{legend_y-7}" width="8" height="8" fill="{c}" opacity="0.85" rx="1"/>')
        parts.append(f'<text x="{leg_x+11}" y="{legend_y}" fill="#8aa0c0" font-size="8">{_esc(name)}</text>')
        leg_x += 12 + len(name) * 5 + 8

    parts.append('</svg>')
    return "".join(parts)


def _svg_combo_bar_line(categories: list, bars: list, line: list, width: int = 480, height: int = 200,
                          title: str = "", bar_label: str = "", line_label: str = "") -> str:
    """Combo chart: bar values + line overlay (e.g. revenue bars + YoY line).
    bars = [values], line = [values].
    """
    if not categories: return '<div class="muted">_無資料_</div>'
    pad_l, pad_r, pad_t, pad_b = 42, 50, 18, 30
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    n = len(categories)

    # y scale: bars (left), line (right) — use 0-100 for YoY % on right
    bar_max = max([b for b in bars if b is not None] + [1])
    line_vals = [l for l in line if l is not None]
    line_min = min(line_vals) if line_vals else 0
    line_max = max(line_vals) if line_vals else 1
    line_pad = max(5, (line_max - line_min) * 0.1)
    line_min -= line_pad; line_max += line_pad
    if line_min > 0: line_min = 0  # anchor at 0 for %

    bar_w = plot_w / n * 0.65

    def y_bar(v): return pad_t + (1 - v / bar_max) * plot_h
    def y_line(v):
        if line_max == line_min: return pad_t + plot_h / 2
        return pad_t + (1 - (v - line_min) / (line_max - line_min)) * plot_h

    parts = [f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
             f'style="width:100%;height:auto;display:block;background:rgba(0,0,0,0.15);border-radius:4px;margin:6px 0;">']
    if title:
        parts.append(f'<text x="{width/2}" y="12" text-anchor="middle" fill="#8aa0c0" font-size="10">{_esc(title)}</text>')

    # y left axis (bars)
    for t in range(5):
        v = bar_max * t / 4
        y = y_bar(v)
        parts.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-pad_r}" y2="{y:.1f}" stroke="#1f2942" stroke-width="0.3"/>')
        parts.append(f'<text x="{pad_l-4}" y="{y+3:.1f}" text-anchor="end" fill="#8aa0c0" font-size="8">{v:.0f}</text>')
    # y right axis (line)
    for t in range(5):
        v = line_min + (line_max - line_min) * t / 4
        y = y_line(v)
        parts.append(f'<text x="{width-pad_r+4}" y="{y+3:.1f}" text-anchor="start" fill="#bc8cff" font-size="8">{v:+.0f}%</text>')

    # bars
    for i, cat in enumerate(categories):
        x = pad_l + i * (plot_w / n) + (plot_w / n - bar_w) / 2
        b = bars[i] if i < len(bars) else None
        if b is not None:
            y = y_bar(b)
            h = (pad_t + plot_h) - y
            parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{max(h, 1):.1f}" fill="#5fb1ff" opacity="0.75" rx="1">'
                         f'<title>{_esc(str(cat))} {bar_label}: {b:,.0f}</title></rect>')
        # x label
        parts.append(f'<text x="{pad_l + i * (plot_w/n) + plot_w/n/2:.1f}" y="{height-12}" text-anchor="middle" fill="#8aa0c0" font-size="8">{_esc(str(cat))[:10]}</text>')

    # line (YoY)
    pts = []
    for i, lv in enumerate(line):
        if lv is None: continue
        x = pad_l + i * (plot_w / n) + plot_w / n / 2
        y = y_line(lv)
        pts.append(f"{x:.1f},{y:.1f}")
    if pts:
        parts.append(f'<path d="M {" L ".join(pts)}" fill="none" stroke="#bc8cff" stroke-width="1.5"/>')
        # dots
        for i, lv in enumerate(line):
            if lv is None: continue
            x = pad_l + i * (plot_w / n) + plot_w / n / 2
            y = y_line(lv)
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.5" fill="#bc8cff">'
                         f'<title>{_esc(str(categories[i]))} {line_label}: {lv:+.1f}%</title></circle>')

    # legend
    parts.append(f'<rect x="{pad_l}" y="{height-7}" width="8" height="6" fill="#5fb1ff" opacity="0.75" rx="1"/>')
    parts.append(f'<text x="{pad_l+11}" y="{height-2}" fill="#8aa0c0" font-size="8">{_esc(bar_label)}</text>')
    parts.append(f'<rect x="{pad_l + len(bar_label)*6 + 24}" y="{height-7}" width="8" height="6" fill="#bc8cff" rx="1"/>')
    parts.append(f'<text x="{pad_l + len(bar_label)*6 + 35}" y="{height-2}" fill="#8aa0c0" font-size="8">{_esc(line_label)}</text>')

    parts.append('</svg>')
    return "".join(parts)


# ---- institutional + technical chart sections ----

def render_institutional_section(ticker: str) -> str:
    """Three-major institutional investors, last 8 trading days, with bar chart + table."""
    rows = db.ticker_history(ticker, days=10)  # grab 10 to filter weekends
    if not rows: return '<div class="muted">_查無三大法人_</div>'
    # Take last 8 (most recent first in list, but list is asc so last 8)
    rows = rows[-8:]
    chart_rows = [
        {
            "date": r.get("Date"),
            "ForeignNet": float(r.get("ForeignNet") or 0) / 1000.0,  # 張
            "InvestmentNet": float(r.get("InvestmentNet") or 0) / 1000.0,
            "DealerNet": float(r.get("DealerNet") or 0) / 1000.0,
            "ThreeNet": float(r.get("ThreeNet") or 0) / 1000.0,
        }
        for r in rows
    ]
    # Build chart rows in display order (most recent on top? No, left-to-right asc)
    # we want most recent on the RIGHT
    chart_rows_asc = list(reversed(chart_rows))
    chart = _svg_bar_chart(
        chart_rows_asc,
        value_keys=["ForeignNet", "InvestmentNet", "DealerNet", "ThreeNet"],
        labels=["外資", "投信", "自營", "合計"],
        colors=["#5fb1ff", "#58d68d", "#f5b041", "#bc8cff"],
        width=520, height=180, title="三大法人買賣超 (近 8 日, 單位: 張)",
    )

    # Table - most recent first
    items = ["| 日期 | 外資 | 投信 | 自營 | 合計 |", "|---|---|---|---|---|"]
    cum_f = cum_t = cum_d = 0
    for r in reversed(chart_rows):
        f_v = r["ForeignNet"]; t_v = r["InvestmentNet"]; d_v = r["DealerNet"]; total = r["ThreeNet"]
        cum_f += f_v; cum_t += t_v; cum_d += d_v
        items.append(
            f"| {_esc(r['date'])[:10]} | {_signed(f_v)} | {_signed(t_v)} | {_signed(d_v)} | **{_signed(total)}** |"
        )
    items.append(f"\n**近 8 日累積**：外資 {_signed(cum_f)} 張｜投信 {_signed(cum_t)} 張｜自營 {_signed(cum_d)} 張｜合計 {_signed(cum_f+cum_t+cum_d)} 張")
    return chart + "\n" + "\n".join(items)


def render_technical_section(ticker: str) -> str:
    """Price + MA + RSI chart, last 60 days."""
    rows = db.ticker_history(ticker, days=70)
    if not rows or len(rows) < 30:
        return '<div class="muted">_K 線資料不足_</div>'
    rows = rows[-60:]
    dates = [r.get("Date") for r in rows]
    closes = [float(r.get("Close") or 0) for r in rows]

    # MA5/13/27/54
    def ma(closes, n):
        out = [None] * len(closes)
        for i in range(n - 1, len(closes)):
            out[i] = sum(closes[i - n + 1:i + 1]) / n
        return out

    ma5 = ma(closes, 5)
    ma13 = ma(closes, 13)
    ma27 = ma(closes, 27)
    ma54 = ma(closes, 54)
    rsi = _compute_rsi(closes, 14)

    def to_xy(arr):
        return [(i, v) for i, v in enumerate(arr) if v is not None]

    main_chart = _svg_line_chart(
        {
            "收盤": list(enumerate(closes)),
            "MA5": to_xy(ma5),
            "MA13": to_xy(ma13),
            "MA27": to_xy(ma27),
            "MA54": to_xy(ma54),
        },
        dates=dates, width=520, height=220,
        title="收盤價 + 均線 (近 60 日)",
    )
    rsi_chart = _svg_line_chart(
        {"RSI(14)": [(i, v) for i, v in enumerate(rsi) if v is not None]},
        dates=dates, width=520, height=120,
        title="RSI(14) 動能指標 (超買 >70 / 超賣 <30)",
        n_total=len(closes),
    )

    # Last values summary
    cur = closes[-1]
    last_ma5 = ma5[-1] or 0
    last_ma13 = ma13[-1] or 0
    last_ma27 = ma27[-1] or 0
    last_ma54 = ma54[-1] or 0
    last_rsi = rsi[-1] or 0
    trend = "多頭排列" if (cur > last_ma5 > last_ma13 > last_ma27) else \
            "空頭排列" if (cur < last_ma5 < last_ma13 < last_ma27) else "盤整/糾結"
    if cur > last_ma13 > last_ma27 and last_ma13 > last_ma5:
        trend = "短空長多，留意落底"
    if last_rsi > 70: rsi_label = "超買"
    elif last_rsi < 30: rsi_label = "超賣"
    else: rsi_label = "中性"

    summary = f"""
- 收盤: **{cur:.2f}** | MA5: {last_ma5:.2f} | MA13: {last_ma13:.2f} | MA27: {last_ma27:.2f} | MA54: {last_ma54:.2f}
- RSI(14): **{last_rsi:.1f}** ({rsi_label}) | 趨勢: **{trend}**
- 區間高: {max(closes):.2f} | 區間低: {min(closes):.2f} | 波動: {(max(closes)-min(closes))/cur*100:.1f}%
"""
    return main_chart + rsi_chart + summary



# ---- per-pick section renderers ----

def render_pick_header(c: ms.Candidate) -> str:
    change_pct = c.change_pct or 0
    pcls = "up" if change_pct > 0 else "down" if change_pct < 0 else ""
    horizon = c.horizon or "long"
    horizon_label = "長期" if horizon == "long" else "短中期"
    industry = c.industry or "—"
    cap_yi = c.market_cap / 1e9 if c.market_cap else 0
    return f"""
    <div class="pick-head {horizon}">
      <div>
        <div><span class="pick-ticker">{_esc(c.ticker)}</span> <span class="pick-name">{_esc(c.name)}</span> <span class="pick-horizon {horizon}">{horizon_label}</span></div>
        <div class="muted" style="font-size:0.78rem;margin-top:3px">{_esc(industry)} · 市值 {cap_yi:,.0f} 億 · 成交量 {_fmt_int(c.volume/1000)}K 張</div>
      </div>
      <div class="pick-price {pcls}">{_fmt_price(c.close)} <span class="muted" style="font-size:0.7rem">{_fmt_pct(change_pct/100)}</span></div>
    </div>
    """


def render_tags_bar(c: ms.Candidate) -> str:
    """Reuse tags from market_screen Candidate by reconstructing from a quick call."""
    # We rely on tags already attached to candidate. But Candidate has no tags attr
    # — tags are generated in market_report_html.render_pick. Instead, use chip + horizon summary.
    tags = []
    if c.excess_return_240d is not None:
        cls = "tag-green" if c.excess_return_240d > 0 else "tag-red"
        tags.append(f'<span class="tag {cls}">240d {c.excess_return_240d:+.1%}</span>')
    if c.foreign_net and c.foreign_net > 0:
        tags.append(f'<span class="tag tag-green">外資 +{c.foreign_net/1000:,.0f} 張</span>')
    elif c.foreign_net and c.foreign_net < 0:
        tags.append(f'<span class="tag tag-red">外資 {c.foreign_net/1000:,.0f} 張</span>')
    if c.rsi14:
        if 50 <= c.rsi14 <= 65:
            tags.append(f'<span class="tag tag-green">RSI {c.rsi14:.0f} 甜蜜區</span>')
        elif c.rsi14 > 70:
            tags.append(f'<span class="tag tag-red">RSI {c.rsi14:.0f} 超買</span>')
        elif c.rsi14 < 30:
            tags.append(f'<span class="tag tag-green">RSI {c.rsi14:.0f} 超賣</span>')
    if c.sma13 and c.sma27 and c.close > c.sma13 > c.sma27:
        tags.append('<span class="tag tag-green">多頭排列</span>')
    if c.chip_score and c.chip_score > 50:
        tags.append(f'<span class="tag tag-cyan">ChipScore {c.chip_score:.0f}</span>')
    if c.volume_burst == 1:
        tags.append('<span class="tag tag-yellow">量能爆發</span>')
    if c.kd_golden_cross == 1:
        tags.append('<span class="tag tag-green">KD 黃金交叉</span>')
    if c.inv_first_in == 1:
        tags.append('<span class="tag tag-yellow">法人首次進場</span>')
    return f'<div class="tags">{"".join(tags)}</div>'


def render_zen_section(c: ms.Candidate) -> str:
    """Zen summary from Candidate.zen_summary (already populated by market_screen)."""
    if not c.zen_summary:
        return '<div class="muted">無 Zen 結構資料</div>'
    cells = []
    for line in c.zen_summary.split("\n"):
        line = line.strip()
        if not line: continue
        if line.startswith("**") and "**：" in line:
            label, val = line.split("**：", 1)
            label = label.strip("*").strip()
            val = val.strip()
            vcls = ""
            if "方向" in label and "偏多" in val and "偏空" not in val:
                vcls = "zen-bullish"
            elif "方向" in label and "偏空" in val and "偏多" not in val:
                vcls = "zen-bearish"
            cells.append(f'<div class="zen-cell"><div class="zen-cell-label">{_esc(label)}</div><div class="zen-cell-value {vcls}">{_esc(val)}</div></div>')
    return f'<div class="zen-grid">{"".join(cells)}</div>'


def render_news_section(d: Dict, limit=5) -> str:
    rows = d.get("news") or []
    if not rows:
        return '<div class="muted">_查無近期新聞_</div>'
    rows_sorted = sorted(rows, key=lambda x: x.get("date", ""), reverse=True)[:limit]
    items = []
    for r in rows_sorted:
        title = r.get("title", "—")
        source = r.get("source", "—")
        date_s = r.get("date", "—")
        link = r.get("link", "")
        if link:
            items.append(f'<div class="news-item">· <a href="{_esc(link)}" target="_blank">{_esc(title)}</a><div class="muted" style="font-size:0.7rem">{_esc(date_s)} · {_esc(source)}</div></div>')
        else:
            items.append(f'<div class="news-item">· {_esc(title)}<div class="muted" style="font-size:0.7rem">{_esc(date_s)} · {_esc(source)}</div></div>')
    return "\n".join(items)


def render_dividend_section(d: Dict) -> str:
    rows = d.get("dividend") or []
    if not rows:
        return '<div class="muted">_查無配息資料_</div>'
    rows_sorted = sorted(rows, key=lambda x: (x.get("year", 0), x.get("CashExDividendTradingDate", "")), reverse=True)[:5]
    items = ["| 年度 | 現金 | 股票 | 合計 |", "|---|---|---|---|"]
    for r in rows_sorted:
        try: cash = float(r.get("CashEarningsDistribution") or 0)
        except: cash = 0
        try: stock = float(r.get("StockEarningsDistribution") or 0)
        except: stock = 0
        items.append(f"| {r.get('year', '—')} | {cash:.2f} | {stock:.2f} | {cash+stock:.2f} |")
    return "\n".join(items)


def render_financial_section(d: Dict) -> str:
    """Quarterly financial statements — render from raw rows."""
    rows = d.get("financial") or []
    if not rows:
        return '<div class="muted">_查無季度財報_</div>'
    type_map = {
        "Revenue": "revenue", "GrossProfit": "grossProfit", "OperatingIncome": "operatingIncome",
        "PreTaxIncome": "pretaxIncome", "IncomeAfterTaxes": "netIncome", "EPS": "EPS",
        "營業收入": "revenue", "營業毛利": "grossProfit", "營業利益": "operatingIncome",
        "稅前淨利": "pretaxIncome", "本期淨利": "netIncome", "歸屬於母公司業主之淨利": "netIncome",
        "基本每股盈餘": "EPS",
    }
    pivot: Dict[str, Dict[str, float]] = {}
    for r in rows:
        d_str = r.get("date", "")
        t = r.get("type", "")
        col = type_map.get(t)
        if not col: continue
        try:
            v = float(r.get("value")) if r.get("value") is not None else None
        except: continue
        pivot.setdefault(d_str, {})[col] = v
    if not pivot:
        return '<div class="muted">_財報格式無法解析_</div>'
    dates = sorted(pivot.keys(), reverse=True)[:6]
    dates.reverse()
    keep = ["revenue", "grossProfit", "operatingIncome", "netIncome", "EPS"]
    headers = ["季度", "營收(億)", "毛利(億)", "營業利益(億)", "淨利(億)", "EPS"]
    items = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * 6) + "|"]
    for d_str in dates:
        row = pivot[d_str]
        cells = [d_str]
        for k in keep:
            v = row.get(k)
            if v is None: cells.append("—")
            elif k == "EPS": cells.append(f"{v:.2f}")
            else: cells.append(f"{v/1e8:.1f}")
        items.append("| " + " | ".join(cells) + " |")
    return "\n".join(items)


def render_margin_section(d: Dict) -> str:
    rows = d.get("margin") or []
    if not rows:
        return '<div class="muted">_查無融資融券_</div>'
    rows_sorted = sorted(rows, key=lambda x: x.get("date", ""), reverse=True)
    r = rows_sorted[0]
    date = r.get("date", "—")
    mb = int(r.get("MarginPurchaseTodayBalance") or 0)
    ms = int(r.get("ShortSaleTodayBalance") or 0)
    mb_prev = int(r.get("MarginPurchaseYesterdayBalance") or 0)
    change = mb - mb_prev
    ratio = (mb / ms) if ms else None
    ratio_str = f"{ratio:.1f}" if ratio else "—"
    return (
        f"_資料日：{date}_\n\n"
        f"| 項目 | 融資 | 融券 |\n|---|---|---|\n"
        f"| 今日餘額 | **{mb:,}** 張 | **{ms:,}** 張 |\n"
        f"| 較昨日 | {_signed(change)} 張 | — |\n"
        f"| 融資融券比 | {ratio_str} | — |\n"
    )


def render_finlab_roe(d: Dict) -> str:
    rows = d.get("finlab_roe") or []
    if not rows:
        return '<div class="muted">_FinLab free tier 不提供 / 額度已滿_</div>'
    rows_sorted = sorted(rows, key=lambda x: x.get("date", ""), reverse=True)[:6]
    rows_sorted.reverse()
    items = ["| 季度 | ROE |", "|---|---|"]
    for r in rows_sorted:
        v = r.get("value")
        items.append(f"| {r.get('date', '—')} | {f'{v:.2f}%' if v is not None else '—'} |")
    items.append("\n_資料來源：FinLab（free tier 限 ~2018）_")
    return "\n".join(items)


def render_finlab_revenue(d: Dict) -> str:
    rows = d.get("finlab_revenue") or []
    if not rows:
        return '<div class="muted">_FinLab free tier 不提供 / 額度已滿_</div>'
    rows_sorted = sorted(rows, key=lambda x: x.get("date", ""), reverse=True)[:8]
    rows_sorted.reverse()
    items = ["| 月份 | 營收 | YoY |", "|---|---|---|"]
    for r in rows_sorted:
        v = r.get("value")
        yoy = r.get("yoy")
        date_s = r.get("date", "—")[:7]
        v_str = f"{v:,.0f}" if v is not None else "—"
        yoy_str = f"{yoy:+.1f}%" if yoy is not None else "—"
        items.append(f"| {date_s} | {v_str} | {yoy_str} |")
    items.append("\n_資料來源：FinLab（free tier 限 ~2018）_")
    return "\n".join(items)


def render_observations(d: Dict) -> str:
    obs = a.section_observations(d)
    return obs.replace("\n", "<br>")


# ---- chart-enhanced sections ----

def render_zen_chart_section(ticker: str, c: ms.Candidate) -> str:
    """K-line candlestick + zen center overlay + buy/sell markers (120 days)."""
    rows = db.ticker_history(ticker, days=130)
    if not rows or len(rows) < 30:
        return '<div class="muted">_K 線資料不足_</div>'
    rows = rows[-120:]
    ohlc = [{"date": r.get("Date"), "open": r.get("Open"), "high": r.get("High"),
             "low": r.get("Low"), "close": r.get("Close")} for r in rows]

    # Try to get zen center from cand.zen_summary or compute
    overlay = {}
    if c.zen_summary:
        for line in c.zen_summary.split("\n"):
            line = line.strip()
            if "中樞" in line and "**" not in line and "失效" not in line and "買點" not in line and "賣點" not in line:
                # parse "中樞: 1725.00 - 1985.00（2026-07-08 ~ 2026-07-29）"
                import re
                m = re.match(r"中樞：?\s*([\d.]+)\s*-\s*([\d.]+)", line)
                if m:
                    overlay["center_low"] = float(m.group(1))
                    overlay["center_high"] = float(m.group(2))
                    # find date range
                    m2 = re.search(r"(\d{4}-\d{2}-\d{2})\s*~\s*(\d{4}-\d{2}-\d{2})", line)
                    if m2:
                        try:
                            s_date = m2.group(1)
                            e_date = m2.group(2)
                            # find indices
                            for idx, r in enumerate(ohlc):
                                d = r.get("date")
                                d_s = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
                                if d_s >= s_date and overlay.get("center_start_idx") is None:
                                    overlay["center_start_idx"] = idx
                                if d_s <= e_date:
                                    overlay["center_end_idx"] = idx
                        except: pass
                    break

    # 買點/賣點 markers
    markers = []
    if c.zen_summary:
        for line in c.zen_summary.split("\n"):
            line = line.strip()
            if "買點" in line and "：**" in line:
                # 二買: 拉回至中樞高 X 且不破 (現價 Y)
                import re
                m = re.search(r"現價\s*([\d.]+)", line)
                if m:
                    cur_price = float(m.group(1))
                    # find the last bar index
                    markers.append({"idx": len(ohlc)-1, "kind": "buy", "price": cur_price})
            elif "賣點" in line and "：**" in line:
                import re
                m = re.search(r"現價\s*([\d.]+)", line)
                if m:
                    cur_price = float(m.group(1))
                    markers.append({"idx": len(ohlc)-1, "kind": "sell", "price": cur_price})
    if markers:
        overlay["markers"] = markers

    chart = _svg_candlestick(ohlc, width=520, height=240, title="K 線 (近 120 日) + 中樞/買賣點",
                            zen_overlay=overlay if overlay else None)

    # 補充資訊表
    cur = float(ohlc[-1].get("close") or 0)
    high_60 = max([float(r.get("high") or 0) for r in ohlc[-60:]])
    low_60 = min([float(r.get("low") or 0) for r in ohlc[-60:]])
    summary = f"""
- 收盤: **{cur:.2f}** | 60日高: {high_60:.2f} | 60日低: {low_60:.2f} | 振幅: {(high_60 - low_60)/cur*100:.1f}%
"""
    return chart + summary


def render_valuation_section(c: ms.Candidate) -> str:
    """240d/120d/60d/20d excess return horizontal bar chart."""
    items = [
        {"label": "20d", "value": c.excess_return_20d or 0},
        {"label": "60d", "value": c.excess_return_60d or 0},
        {"label": "120d", "value": c.excess_return_120d or 0},
        {"label": "240d", "value": c.excess_return_240d or 0},
    ]
    chart = _svg_horizontal_bars(items, width=520, height=130,
                                  title="超額報酬率 (扣大盤)", value_fmt="+.1%")
    cap_yi = c.market_cap / 1e9 if c.market_cap else 0
    summary = f"""
- 市值: **{cap_yi:,.0f} 億** | 收盤: {c.close:.2f} | 成交量: {c.volume/1000:,.0f}K 張
- **240d** 是長期動能指標，**60d** 是中期趨勢，**20d** 是短期動能
"""
    return chart + summary


def render_margin_chart_section(ticker: str, d: Dict) -> str:
    """Margin balance trend (line) + daily change (bars) over last 30 days."""
    rows = db.ticker_history(ticker, days=35)
    if not rows:
        return render_margin_section(d)
    rows = rows[-30:]
    dates = [r.get("Date") for r in rows]
    balances = [float(r.get("MarginBalance") or 0) / 1000.0 for r in rows]  # 張
    shorts = [float(r.get("ShortBalance") or 0) / 1000.0 for r in rows]

    # Daily change
    changes = [None]
    for i in range(1, len(balances)):
        changes.append(balances[i] - balances[i-1])

    # Line chart: 融資 + 融券
    main_chart = _svg_line_chart(
        {
            "融資 (張)": [(i, v) for i, v in enumerate(balances) if v is not None],
            "融券 (張)": [(i, v) for i, v in enumerate(shorts) if v is not None],
        },
        dates=dates, width=520, height=160, title="融資融券餘額走勢 (近 30 日)",
    )

    # Bar chart: daily change
    bar_data = [{"date": d, "ForeignNet": 0, "InvestmentNet": 0, "DealerNet": 0, "ThreeNet": chg or 0}
                for d, chg in zip(dates, changes)]
    bar_data = [b for b in bar_data if b["ThreeNet"] != 0]
    if bar_data:
        change_chart = _svg_bar_chart(
            bar_data[-20:],
            value_keys=["ThreeNet"],
            labels=["日增減"],
            colors=["#f5b041"],
            width=520, height=100, title="融資日增減 (近 20 日, 張)",
        )
    else:
        change_chart = ""

    if rows:
        r = rows[-1]
        mb = int(r.get("MarginBalance") or 0)
        ms = int(r.get("ShortBalance") or 0)
        ratio = (mb / ms) if ms else None
        ratio_str = f"{ratio:.1f}" if ratio else "—"
        return main_chart + change_chart + f"""
- 今日融資: **{mb:,} 張** | 融券: **{ms:,} 張** | 融資融券比: {ratio_str}
"""
    return main_chart + change_chart


def render_financial_chart_section(d: Dict) -> str:
    """Quarterly financial statements: 6-quarter grouped bar chart + table."""
    rows = d.get("financial") or []
    if not rows: return '<div class="muted">_查無季度財報_</div>'
    type_map = {
        "Revenue": "revenue", "GrossProfit": "grossProfit", "OperatingIncome": "operatingIncome",
        "PreTaxIncome": "pretaxIncome", "IncomeAfterTaxes": "netIncome", "EPS": "EPS",
        "營業收入": "revenue", "營業毛利": "grossProfit", "營業利益": "operatingIncome",
        "稅前淨利": "pretaxIncome", "本期淨利": "netIncome", "歸屬於母公司業主之淨利": "netIncome",
        "基本每股盈餘": "EPS",
    }
    pivot = {}
    for r in rows:
        d_str = r.get("date", "")
        t = r.get("type", "")
        col = type_map.get(t)
        if not col: continue
        try:
            v = float(r.get("value")) if r.get("value") is not None else None
        except: continue
        pivot.setdefault(d_str, {})[col] = v
    if not pivot: return '<div class="muted">_財報格式無法解析_</div>'

    dates = sorted(pivot.keys(), reverse=True)[:6]
    dates.reverse()
    categories = [d[2:].replace("-", "Q") if len(d) >= 7 else d for d in dates]  # e.g. "25Q3"

    # Convert to 億
    rev = [pivot[d].get("revenue", 0) / 1e8 if pivot[d].get("revenue") else None for d in dates]
    oi = [pivot[d].get("operatingIncome", 0) / 1e8 if pivot[d].get("operatingIncome") else None for d in dates]
    ni = [pivot[d].get("netIncome", 0) / 1e8 if pivot[d].get("netIncome") else None for d in dates]
    eps = [pivot[d].get("EPS") for d in dates]

    chart = _svg_grouped_bars(categories, {"營收(億)": rev, "營業利益(億)": oi, "淨利(億)": ni},
                              width=520, height=180, title="近 6 季季報 (億)")

    # EPS line below
    eps_chart = _svg_line_chart(
        {"EPS (元)": [(i, v) for i, v in enumerate(eps) if v is not None]},
        dates=dates, width=520, height=80, title="EPS 趨勢 (元)",
    )

    # Compact table
    table = "| 季度 | 營收(億) | 毛利(億) | 營業利益(億) | 淨利(億) | EPS |\n|---|---|---|---|---|---|\n"
    for d in dates:
        row = pivot[d]
        def fmt(k, scale=1e8):
            v = row.get(k)
            if v is None: return "—"
            if k == "EPS": return f"{v:.2f}"
            return f"{v/scale:.1f}"
        table += f"| {d[2:7].replace('-', 'Q')} | {fmt('revenue')} | {fmt('grossProfit')} | {fmt('operatingIncome')} | {fmt('netIncome')} | {fmt('EPS')} |\n"
    return chart + eps_chart + "\n" + table


def render_finlab_roe_chart(d: Dict) -> str:
    """ROE history line chart + table."""
    rows = d.get("finlab_roe") or []
    if not rows:
        return '<div class="muted">_查無 ROE 資料_</div>'
    rows_sorted = sorted(rows, key=lambda x: x.get("date", ""))[-12:]  # 最多 12 季
    if not rows_sorted: return '<div class="muted">_查無 ROE 資料_</div>'
    dates = [r.get("date", "") for r in rows_sorted]
    vals = [float(r.get("value")) if r.get("value") is not None else None for r in rows_sorted]

    chart = _svg_line_chart(
        {"ROE (%)": [(i, v) for i, v in enumerate(vals) if v is not None]},
        dates=dates, width=520, height=140, title="ROE 季度趨勢 (%)",
    )
    latest = vals[-1] if vals[-1] else None
    note = f"\n_最新 ROE: **{latest:.2f}%** | 資料來源：FinMind TaiwanStockFinancialStatements_\n" if latest is not None else "\n_資料來源：FinMind_\n"
    return chart + note


def render_finlab_revenue_chart(d: Dict) -> str:
    """Monthly revenue combo chart: bar + YoY line."""
    rows = d.get("finlab_revenue") or []
    if not rows:
        return '<div class="muted">_查無月營收_</div>'
    rows_sorted = sorted(rows, key=lambda x: x.get("date", ""))[-12:]
    if not rows_sorted: return '<div class="muted">_查無月營收_</div>'
    # Strip timestamp and take year-month; date format is "2025-08-01" or "2018-12-10 00:00:00"
    cats = []
    for r in rows_sorted:
        ds = str(r.get("date", ""))[:7]  # "2025-08"
        cats.append(ds[2:])  # "25-08"
    bars = [float(r.get("value")) if r.get("value") is not None else None for r in rows_sorted]
    line = [float(r.get("yoy")) if r.get("yoy") is not None else None for r in rows_sorted]
    chart = _svg_combo_bar_line(cats, bars, line, width=520, height=180,
                                 title="月營收 + YoY (近 12 月)", bar_label="營收", line_label="YoY%")
    latest_yoy = [y for y in line if y is not None][-1] if any(line) else None
    note = f"\n_最新 YoY: **{latest_yoy:+.1f}%** | 資料來源：FinMind TaiwanStockMonthRevenue_\n" if latest_yoy is not None else "\n_資料來源：FinMind TaiwanStockMonthRevenue_\n"
    return chart + note


def render_dividend_chart_section(d: Dict) -> str:
    """Dividend history stacked bar (cash + stock) + total line."""
    rows = d.get("dividend") or []
    if not rows: return '<div class="muted">_查無配息資料_</div>'
    # Group by year
    by_year: Dict[str, Dict[str, float]] = {}
    for r in rows:
        y = r.get("year", "")
        if not y or y in ("不適用", "0"): continue
        try:
            cash = float(r.get("CashEarningsDistribution") or 0)
        except: cash = 0
        try:
            stock = float(r.get("StockEarningsDistribution") or 0)
        except: stock = 0
        if y not in by_year:
            by_year[y] = {"cash": 0, "stock": 0}
        by_year[y]["cash"] += cash
        by_year[y]["stock"] += stock
    if not by_year: return '<div class="muted">_查無配息資料_</div>'
    years = sorted(by_year.keys())[-5:]  # 最近 5 年
    cash = [by_year[y]["cash"] for y in years]
    stock = [by_year[y]["stock"] for y in years]
    total = [c + s for c, s in zip(cash, stock)]

    # Stacked bar via grouped_bars (will show side by side, but we want stacked — fake with 2 series)
    # Use line for total
    chart = _svg_grouped_bars(years, {"現金股利": cash, "股票股利": stock},
                              width=520, height=140, title="近 5 年股利 (元/股)")
    line_chart = _svg_line_chart(
        {"合計": [(i, v) for i, v in enumerate(total) if v is not None]},
        dates=years, width=520, height=80, title="合計股利 (元/股)",
    )
    # Compact table
    table = "| 年度 | 現金 | 股票 | 合計 |\n|---|---|---|---|\n"
    for y in years:
        c = by_year[y]["cash"]; s = by_year[y]["stock"]
        table += f"| {y} | {c:.2f} | {s:.2f} | {c+s:.2f} |\n"
    return chart + line_chart + "\n" + table


def render_deep_dive_prompt(c: ms.Candidate) -> str:
    """Tiger Global or Baupost prompt based on horizon/return."""
    try:
        prompt = ddp.render_prompt(c)
        # Escape for HTML
        return f'<div class="dd-prompt"><button class="copy-btn" onclick="copyText(this)">📋 複製</button><pre>{_esc(prompt)}</pre></div>'
    except Exception as e:
        return f'<div class="muted">_deep-dive prompt 生成失敗：{e}_</div>'


def render_pick_card(c: ms.Candidate, d: Dict, idx: int) -> str:
    ticker = c.ticker
    ticker_url = f"https://walterLiu168.github.io/stock-report/market-screen-2026-08-12.html#{ticker}"
    headline = render_pick_header(c)
    tags = render_tags_bar(c)
    # Section tabs (chart-enhanced)
    sections = {
        "zen": ("🧘 纏論", render_zen_chart_section(c.ticker, c)),
        "tech": ("📈 技術", render_technical_section(c.ticker)),
        "val": ("💰 估值", render_valuation_section(c)),
        "inst": ("🏛 法人", render_institutional_section(c.ticker)),
        "marg": ("💴 融資", render_margin_chart_section(c.ticker, d)),
        "fin": ("📊 季報", render_financial_chart_section(d)),
        "fl_roe": ("🧬 ROE", render_finlab_roe_chart(d)),
        "fl_rev": ("📈 月營收", render_finlab_revenue_chart(d)),
        "div": ("💵 配息", render_dividend_chart_section(d)),
        "news": ("📰 新聞", render_news_section(d, limit=5)),
        "obs": ("💡 觀察", render_observations(d)),
        "dd": ("🔬 Deep-dive", render_deep_dive_prompt(c)),
    }
    tab_btns = []
    sec_htmls = []
    for i, (k, (label, raw_content)) in enumerate(sections.items()):
        active = "active" if i == 0 else ""
        tab_btns.append(f'<button class="{active}" data-sec="{k}">{label}</button>')
        # Post-process: convert markdown tables to styled HTML
        content = beautify_section_html(raw_content)
        sec_htmls.append(f'<div class="section {active}" data-sec="{k}"><h5>{label}</h5>{content}</div>')

    actions = f"""
    <div class="actions">
      <a href="https://walterLiu168.github.io/stock-report/market-screen-2026-08-12.html#{ticker}" target="_blank">📊 Market Report</a>
      <a href="https://github.com/your-org/ticker-dashboard/blob/main/{ticker}.md" onclick="return false">🎛 Ticker Dashboard</a>
      <a href="https://walterLiu168.github.io/stock-report/wall-street-{ticker}.html" onclick="return false">🏛 Wall Street</a>
      <a href="https://walterLiu168.github.io/stock-report/research-{ticker}.md" onclick="return false">📋 Research</a>
    </div>
    """

    return f"""
    <div class="pick" id="pick-{ticker}">
      {headline}
      <div class="pick-body">
        {tags}
        <div class="tabs2">
          {''.join(tab_btns)}
        </div>
        {''.join(sec_htmls)}
        {actions}
      </div>
    </div>
    """


# ---- per-bucket group ----

def _fetch_margin_distress_candidates(top_n: int = 10) -> List[Dict]:
    """從 outputs/margin_rebound/<date>.json 讀取 scan 結果。

    若 JSON 不存在（scan 還沒跑過），fallback 到 DB query 算簡化版。
    全 7 維度的 scan 結果由 src/margin_rebound/scan.py 產出。
    """
    import json
    # Try reading today's JSON (skill root / outputs / margin_rebound / <date>.json)
    today = date.today().isoformat()
    skill_root = Path(__file__).parent.parent
    json_path = skill_root / "outputs" / "margin_rebound" / f"{today}.json"
    if json_path.exists():
        try:
            d = json.loads(json_path.read_text(encoding="utf-8"))
            candidates = d.get("candidates", [])
            return candidates[:top_n]
        except (json.JSONDecodeError, OSError):
            pass
    # Fallback: simple DB query (old behavior)
    return _fetch_margin_distress_fallback(top_n)


def _fetch_margin_distress_fallback(top_n: int = 10) -> List[Dict]:
    """Fallback: 從 DB 查詢融資反彈候選人（簡化版，不含多維度評分）。"""
    out = []
    with db.get_conn() as conn:
        cur = conn.cursor(pymysql.cursors.DictCursor)
        cur.execute("""
            SELECT
                d.Ticker, d.Date, d.Close, d.MarginBalance,
                d.ShortBalance, d.Volume,
                c.industry, c.company AS name
            FROM daily_data2_full d
            LEFT JOIN industry_type c ON d.Ticker = c.ticker
            WHERE d.Date = (SELECT MAX(Date) FROM daily_data2_full)
              AND d.MarginBalance >= 5000
              AND d.Close >= 5
              AND d.Volume >= 100
        """)
        latest = cur.fetchall()
        if not latest:
            return []
        tickers = [r["Ticker"] for r in latest]
        placeholders = ",".join(["%s"] * len(tickers))
        cur.execute(f"""
            SELECT Ticker, AVG(Close) AS avg_c
            FROM daily_data2_full
            WHERE Ticker IN ({placeholders})
              AND Date >= (SELECT MAX(Date) FROM daily_data2_full) - INTERVAL 120 DAY
            GROUP BY Ticker
        """, tuple(tickers))
        avg_costs = {r["Ticker"]: float(r["avg_c"]) for r in cur.fetchall() if r.get("avg_c")}

    for r in latest:
        t = r["Ticker"]
        avg_c = avg_costs.get(t, 0)
        if avg_c <= 0:
            continue
        close = float(r["Close"])
        margin = int(r["MarginBalance"])
        maint_pct = close / avg_c * 100
        if maint_pct >= 133:
            continue
        out.append({
            "ticker": t,
            "name": r.get("name") or t,
            "industry": r.get("industry") or "—",
            "close": close,
            "margin_張": margin,
            "margin_市值_億": round(margin * close * 1000 / 1e8, 2),
            "avg_cost_120d": round(avg_c, 2),
            "maint_rate": round(maint_pct, 1),
            "composite": round(maint_pct / 1.33, 1),  # simple proxy
            "scores": {"maint_rate": round(max(0, 100 - (maint_pct - 100) * 2), 1)},
        })
    out.sort(key=lambda x: x.get("margin_市值_億", 0), reverse=True)
    return out[:top_n]


def _render_margin_tab(candidates: List[Dict]) -> str:
    """Render the 🎯 潛在反彈 tab content (uses multi-dim scan results).

    D025: 顯示 tier 標籤 + 進場天數 badge（🆕 新進 / 🔥 持續 / ⚠️ 持續 8+ 天）。
    Group by tier (Tier 1 strict < 130% first, then Tier 2 warning 130-150% 連 3 日下降).
    """
    if not candidates:
        return '<div class="tab-content" data-bucket="margin">無候選人</div>'

    # Group by tier
    tier1 = [c for c in candidates if c.get("tier") == 1 or c.get("maint_rate") is not None and c.get("maint_rate") < 130]
    tier2 = [c for c in candidates if c not in tier1]
    sections = []
    for label, group, badge_color, desc in [
        ("🎯 Tier 1: 維持率 < 130%（斷頭區）", tier1, "red", "已觸及追繳線，強制賣壓大"),
        ("⚠️ Tier 2: 130-150% 連 3 日融資下降（警示區）", tier2, "yellow", "接近追繳且融資持續減，可能是早進場訊號"),
    ]:
        if not group:
            continue
        cards = []
        for c in group:
            # Color: 維持率 紅色 (台灣慣例 — 維持率低 = 紅 = 反彈機會)
            maint = c.get("maint_rate")
            maint_s = f"{maint:.1f}%" if maint is not None else "—"
            score = c.get("composite", 0)
            # D025: 進場天數 badge (Taiwan color convention: 紅=新/正, 綠=舊/負)
            days = c.get("days_on_list", 0) or 0
            if days <= 2:
                # 新進 — 紅色 (台灣慣例 = 正/新)
                days_badge = '<span class="chip chip-pos">🆕 新進 ' + ('今' if days == 0 else f'{days} 天') + '</span>'
            elif days <= 7:
                # 持續中 — 黃色 (注意)
                days_badge = f'<span class="chip chip-neu">🔥 持續 {days} 天</span>'
            else:
                # 持續 8+ 天 — 綠色 (台灣慣例 = 負/舊/失去新鮮感)
                days_badge = f'<span class="chip chip-neg">⚠️ 持續 {days} 天</span>'
            # 顯示每個維度的分數
            scores = c.get("scores", {})
            score_chips = ""
            if scores:
                chips = []
                label_map = {
                    "maint_rate": "📏維持率",
                    "margin_change_1d": "📉1d融資",
                    "margin_change_3d": "📉3d融資",
                    "bias": "📐Bias",
                    "rsi": "RSI",
                    "boll": "布林",
                    "volume_shadow": "💥爆量",
                }
                for k, lbl in label_map.items():
                    if k in scores:
                        s = scores[k]
                        cls = "pos" if s >= 70 else ("neu" if s >= 40 else "neg")
                        chips.append(f'<span class="chip chip-{cls}">{lbl} {s:.0f}</span>')
                score_chips = '<div class="pick-chips">' + " ".join(chips) + '</div>'

            # Tier label
            tier_label = '<span class="chip" style="background:rgba(236,112,99,0.18);color:#ec7063">Tier 1</span>' if c.get("tier") == 1 else '<span class="chip" style="background:rgba(245,176,65,0.18);color:#f5b041">Tier 2</span>'

            cards.append(f"""
        <div class="pick">
          <div class="pick-head">
            <span class="pick-ticker">{_esc(c['ticker'])}</span>
            <span class="pick-name">{_esc(c.get('company') or c.get('name', c['ticker']))}</span>
            <span class="pick-industry muted">{_esc(c.get('industry') or '—')}</span>
            {tier_label}
            {days_badge}
            <span class="pick-score" style="background:var(--acc);color:#000;padding:2px 8px;border-radius:10px;font-weight:700;font-size:0.78rem">Score {score:.0f}</span>
            <a class="analyze-link" href="analyze/{_esc(c['ticker'])}.html" target="_blank">🔍 分析 →</a>
          </div>
          <div class="pick-grid">
            <div class="pick-cell">
              <div class="k">收盤</div>
              <div class="v">{c['close']:,.2f}</div>
            </div>
            <div class="pick-cell">
              <div class="k">120d 平均成本</div>
              <div class="v muted">{c.get('avg_cost_120d', 0):,.2f}</div>
            </div>
            <div class="pick-cell">
              <div class="k">📏 估維持率</div>
              <div class="v pos" style="font-weight:700">{maint_s}</div>
            </div>
            <div class="pick-cell">
              <div class="k">📉 1d 融資變化</div>
              <div class="v neg">{c.get('margin_chg_1d_pct', 0):+.1f}%</div>
            </div>
            <div class="pick-cell">
              <div class="k">📐 Bias</div>
              <div class="v neg">{c.get('bias_pct', 0):+.1f}%</div>
            </div>
            <div class="pick-cell">
              <div class="k">RSI</div>
              <div class="v">{c.get('rsi', 0):.0f}</div>
            </div>
          </div>
          {score_chips}
          <div class="pick-meta muted">
            <span>🚨 120d 估維持率 <b style="color:#ec7063">{maint_s}</b>（&lt; 133% 追繳線）</span> ·
            <span>融資 {c.get('margin_張', 0):,} 張 · 市值 {c.get('margin_市值_億', 0):,.1f} 億</span> ·
            <span>進場 {c.get('first_seen', '—')}</span>
          </div>
        </div>""")
        sections.append(f"""
        <h3 style="margin:18px 0 8px;color:var(--{'green' if badge_color=='red' else 'amber'});font-size:0.95rem">{label} <small class="muted" style="font-weight:400">{desc} · {len(group)} 檔</small></h3>
        <div class="picks">{''.join(cards)}</div>""")
    return f"""
    <div class="tab-content" data-bucket="margin">
      <h2 class="bucket-title">🎯 潛在反彈候選 <small>7 維度評分 (維持率 / 融資變化 / Bias / RSI / 布林 / 量價 / 集保*)</small></h2>
      <p class="muted" style="font-size:0.82rem;margin:4px 0 12px">*集保戶數 / 千張大戶需 TDCC 申報資料，目前沒接入。每日 22:25 自動更新。<br>
      <b>Tier 1</b> 維持率 &lt; 130%（斷頭區）；<b>Tier 2</b> 130-150% 連 3 日融資下降（警示區）。進場天數：<span class="chip chip-pos">🆕 新進</span> ≤ 2 天 / <span class="chip chip-neu">🔥 持續</span> 3-7 天 / <span class="chip" style="background:rgba(110,118,130,0.15);color:#8b949e">⚠️ 持續 8+ 天</span>。</p>
      {''.join(sections)}
    </div>"""


def render_bucket(bucket_label: str, picks: List[ms.Candidate], data_map: Dict[str, Dict], idx_offset: int) -> str:
    BUCKET_META = {
        "<100": ("💰 銅板股", "高波動、題材驅動，短中期操作為主"),
        "100-300": ("💵 中價股", "主流操作區間，流動性佳"),
        "300-1000": ("💎 中高價", "基本面與成長性兼具，適合中期持有"),
        ">1000": ("🏆 高價股", "龍頭企業、法人重倉、波動相對小"),
    }
    title, desc = BUCKET_META.get(bucket_label, (bucket_label, ""))
    cards = []
    for i, c in enumerate(picks):
        d = data_map.get(c.ticker, {})
        cards.append(render_pick_card(c, d, idx_offset + i))
    return f"""
    <div class="tab-content" data-bucket="{bucket_label}">
      <h2 class="bucket-title">{title} <small>{desc}</small></h2>
      <div class="picks">{''.join(cards)}</div>
    </div>
    """


# ---- main ----

def main():
    # Use the actual data date (last trading day in DB) instead of today's date.
    # DB may not have today's data if rendered before market close or on holidays.
    try:
        data_date = db.latest_date("daily_data2_full")
    except Exception:
        data_date = date.today().strftime("%Y-%m-%d")
    if not data_date:
        data_date = date.today().strftime("%Y-%m-%d")
    today = data_date
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    print(f"[1/4] Loading active picks from DB + screen…")
    perf = wl.get_performance_report()
    rows = perf["picks"]
    if not rows:
        print("No active picks. Run market_screen.py first.")
        return
    print(f"  {len(rows)} active picks")

    # Re-run the market screen to get fresh Candidate objects (zen_summary, etc.)
    print(f"[2/4] Re-running market screen for fresh Candidates with zen + tags…")
    result = ms.screen_market()
    # Build ticker -> Candidate map (horizon-aware)
    cand_map: Dict[Tuple[str, str], ms.Candidate] = {}
    for bucket_label, by_horizon in result.items():
        for horizon in ("long", "short"):
            for c in by_horizon.get(horizon, []):
                cand_map[(c.ticker, horizon)] = c
                c.horizon = horizon  # ensure set
                c.bucket = bucket_label
    # Bucket candidates by their (already-set) bucket attr
    bucket_picks: Dict[str, List[ms.Candidate]] = {"<100": [], "100-300": [], "300-1000": [], ">1000": []}
    for r in rows:
        ticker = r["ticker"]
        horizon = r["horizon"]
        bucket = r["bucket"]
        c = cand_map.get((ticker, horizon))
        if c and bucket in bucket_picks:
            bucket_picks[bucket].append(c)
    # Sort each bucket: long first, then short
    for k in bucket_picks:
        bucket_picks[k].sort(key=lambda x: (0 if x.horizon == "long" else 1, x.ticker))

    # Group DB picks by ticker for performance summary
    perf_map = {r["ticker"]: r for r in rows}

    # ---- Step 3: parallel deep-dive fetch ----
    print(f"[3/4] Fetching deep-dive data for {sum(len(v) for v in bucket_picks.values())} picks (parallel)…")
    all_picks = [c for v in bucket_picks.values() for c in v]
    data_map: Dict[str, Dict] = {}

    def fetch_one(c: ms.Candidate):
        try:
            d = a.fetch_all(c.ticker)
            return c.ticker, d, None
        except Exception as e:
            return c.ticker, {"fetch_errors": [str(e)]}, str(e)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=4) as exe:
        futs = {exe.submit(fetch_one, c): c for c in all_picks}
        done = 0
        for fut in as_completed(futs):
            ticker, d, err = fut.result()
            data_map[ticker] = d
            done += 1
            elapsed = time.time() - t0
            eta = (elapsed / done) * (len(all_picks) - done)
            status = "✓" if not err else f"⚠ {err[:40]}"
            print(f"  [{done}/{len(all_picks)}] {ticker} {status}  ({elapsed:.0f}s elapsed, ~{eta:.0f}s left)")

    # ---- Step 4: render + write ----
    print(f"[4/4] Rendering HTML…")
    tabs_html = []
    contents_html = []
    # First tab: 潛在反彈 (margin distress candidates) — highest priority
    # D025: margin tab 顯示更多 (Tier 1 strict + Tier 2 warning, 總共 ~30 張)
    margin_candidates = _fetch_margin_distress_candidates(top_n=30)
    if margin_candidates:
        active = "active"  # first tab = default open
        tabs_html.append(f'<button class="tab {active}" data-bucket="margin">🎯 潛在反彈 <span class="count">{len(margin_candidates)}</span></button>')
        contents_html.append(_render_margin_tab(margin_candidates))
    for i, bucket_label in enumerate(["<100", "100-300", "300-1000", ">1000"]):
        items = bucket_picks.get(bucket_label, [])
        if not items: continue
        active = "active" if i == 0 and not margin_candidates else ""
        tabs_html.append(f'<button class="tab {active}" data-bucket="{bucket_label}">{bucket_label} 元 <span class="count">{len(items)}</span></button>')
        contents_html.append(render_bucket(bucket_label, items, data_map, i * 10))

    # Summary stats
    rets = [perf_map.get(c.ticker, {}).get("ret_since_pick") for c in all_picks if perf_map.get(c.ticker, {}).get("ret_since_pick") is not None]
    avg = sum(rets) / len(rets) if rets else 0
    wins = sum(1 for r in rets if r > 0)
    winrate = wins / len(rets) * 100 if rets else 0

    summary_cards = f"""
    <div class="summary-bar">
      <div class="card"><div class="k">活躍 picks</div><div class="v">{len(all_picks)}</div></div>
      <div class="card"><div class="k">長期 / 短中期</div><div class="v">{sum(1 for c in all_picks if c.horizon=='long')} / {sum(1 for c in all_picks if c.horizon=='short')}</div></div>
      <div class="card"><div class="k">平均報酬</div><div class="v" style="color:{'var(--green)' if avg>0 else 'var(--red)'}">{avg*100:+.2f}%</div></div>
      <div class="card"><div class="k">勝率</div><div class="v">{winrate:.0f}%</div></div>
      <div class="card"><div class="k">資料日</div><div class="v">{today}</div></div>
      <div class="card"><div class="k">最後更新</div><div class="v" style="font-size:0.95rem">{now[11:]}</div></div>
    </div>
    """

    skillbar = "".join(f'<span class="sk" title="{_esc(desc)}">{_esc(name)}</span>' for name, desc in SKILL_LINKS)

    html_doc = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>台股深度選股 · {today} · 24 檔</title>
<style>{CSS}</style>
</head>
<body>
<div class="topbar">
  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
    <div class="brand">📊 台股深度選股 <small>tw-invest-suite · market screen + single-stock deep-dive · {today}</small></div>
    <div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap">
      <a href="readme.html" style="background:rgba(95,177,255,0.15);color:var(--acc);border:1px solid var(--border);border-radius:6px;padding:6px 12px;font-size:0.85rem;font-weight:600;text-decoration:none;white-space:nowrap">📖 關於本站</a>
      <a href="https://groovelab.dev/analyze/patterns.html" target="_blank" style="background:rgba(57,197,207,0.18);color:var(--cyan);border:1px solid var(--cyan);border-radius:6px;padding:6px 12px;font-size:0.85rem;font-weight:600;text-decoration:none;white-space:nowrap">📊 型態搜尋 →</a>
      <form class="search-form" action="https://groovelab.dev/analyze.html" method="get" target="_blank" style="display:flex;gap:6px">
        <input name="ticker" placeholder="個股代號 e.g. 2324" maxlength="6" required style="background:var(--panel);color:var(--ink);border:1px solid var(--border);border-radius:6px;padding:6px 10px;font-size:0.85rem;width:160px;font-family:inherit">
        <button type="submit" style="background:var(--acc);color:#000;border:none;border-radius:6px;padding:6px 12px;font-size:0.85rem;font-weight:600;cursor:pointer">🔍 分析個股 →</button>
      </form>
    </div>
  </div>
  <div class="skillbar">{skillbar}</div>
</div>
<div class="tabs">{''.join(tabs_html)}</div>
<main>
  {summary_cards}
  {''.join(contents_html)}
  <footer>tw-invest-suite · {now} · Generated by Mavis · 24 檔深度報告 + 14 skill 視角</footer>
</main>
<script>
document.querySelectorAll('.tab').forEach(btn => {{
  btn.addEventListener('click', () => {{
    const b = btn.dataset.bucket;
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    document.querySelector('.tab-content[data-bucket="' + b + '"]').classList.add('active');
  }});
}});
document.querySelectorAll('.tabs2').forEach(group => {{
  group.querySelectorAll('button').forEach(btn => {{
    btn.addEventListener('click', () => {{
      const sec = btn.dataset.sec;
      const card = btn.closest('.pick');
      group.querySelectorAll('button').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      card.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
      card.querySelector('.section[data-sec="' + sec + '"]').classList.add('active');
    }});
  }});
}});
function copyText(btn) {{
  const pre = btn.nextElementSibling;
  const text = pre.textContent;
  navigator.clipboard.writeText(text).then(() => {{
    const orig = btn.textContent;
    btn.textContent = '✓ 已複製';
    setTimeout(() => btn.textContent = orig, 1500);
  }}).catch(err => alert('複製失敗：' + err));
}}
</script>
</body>
</html>"""

    # Write outputs
    reports_dir = Path.home() / ".claude" / "skills" / "tw-invest-suite" / "reports"
    out1 = reports_dir / f"watchlist-full-{today}.html"
    out1.write_text(html_doc, encoding="utf-8")
    print(f"  → {out1} ({len(html_doc):,} bytes)")

    groove = Path(r"C:\Groove-Lab\watchlist.html")
    groove.write_text(html_doc, encoding="utf-8")
    print(f"  → {groove} ({len(html_doc):,} bytes)")

    # Stats
    total_errs = sum(len(d.get("fetch_errors", [])) for d in data_map.values())
    print(f"\n✅ Done. {len(all_picks)} picks, fetch_errors={total_errs}, total time {time.time()-t0:.0f}s")
    print(f"📱 Phone: https://groovelab.dev/watchlist.html")


if __name__ == "__main__":
    main()
