"""
Full single-ticker renderer — uses pre-assembled cross-source data.

Output: C:\\Groove-Lab\\analyze\\<ticker>.html  (~25-30KB per file)

Sections:
  1. Hero (ticker, name, industry, price, change)
  2. Summary cards (PE/PB/ROE/MarketCap/Yield/240d/RSI/Foreign/ChipScore/Zen)
  3. Master tags (hedge-fund style, conditional)
  4. Company info (sector, industry, market, shares, beta)
  5. Price snapshot (today + prev day)
  6. Technical (MA13/27/54, RSI, ATR, trend)
  7. Valuation (PE, PB, dividend yield, market cap, 52w)
  8. Financials (latest 6 quarters P&L, ROE, EPS)
  9. Monthly revenue (last 12 months + YoY)
 10. Dividends (last 6 distributions)
 11. News (top 5 with source URL)
 12. Chanlun (zen) — recent pivots
 13. Observations (auto-generated)
 14. Deep-dive prompt (Perplexity)

Args:
  data: output of cross_source_runner.assemble(t)
"""
import sys
import os
import html as _html_lib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db_client as db
import market_screen as ms
import deep_dive_prompts as ddp
import zen_analyzer as zen
from render_ticker_html import (CSS, _esc, render_md_table, beautify,
                                 SKILL_LINKS, master_tags)


# ---- Per-section markdown builders ----

def _fmt_pct(v):
    if v is None: return "—"
    return f"{float(v):+.2f}%"


def _fmt_num(v, decimals=0):
    if v is None: return "—"
    try:
        v = float(v)
        if abs(v) >= 1e12: return f"{v/1e12:.2f}兆"
        if abs(v) >= 1e8:  return f"{v/1e8:.2f}億"
        if decimals == 0:   return f"{v:,.0f}"
        return f"{v:,.{decimals}f}"
    except (TypeError, ValueError):
        return str(v)


def _fetch_db_technicals(ticker: str) -> Dict:
    """Get latest row from DB for technical section."""
    try:
        rows = db.ticker_history(ticker, days=2)
        if not rows: return {}
        latest = rows[-1]
        return dict(latest)
    except Exception as e:
        return {"_err": str(e)}


def _fetch_history(ticker: str, days: int = 240) -> List[Dict]:
    """Get N-day price history for chart/zen."""
    try:
        return db.ticker_history(ticker, days=days)
    except Exception:
        return []


def section_company(data: Dict) -> str:
    """公司基本資料."""
    ticker = data["ticker"]
    yf = data.get("yfinance", {})
    name = data.get("company_name") or yf.get("longName") or ticker
    industry = data.get("industry") or yf.get("industry") or "—"
    sector = yf.get("sector") or "—"
    market = "上市" if len(ticker) == 4 else "上櫃" if len(ticker) == 5 else "—"
    beta = yf.get("beta")
    shares = yf.get("_shares_outstanding") or data.get("yfinance", {}).get("_shares_outstanding")
    market_cap = yf.get("marketCap")
    if not market_cap and shares and data.get("latest_close"):
        market_cap = float(shares) * float(data["latest_close"])
    md = "| 項目 | 數值 |\n|---|---|\n"
    md += f"| 公司全名 | {name} |\n"
    md += f"| 產業分類 | {industry} |\n"
    md += f"| 市場 (yfinance) | {sector} |\n"
    md += f"| 上市/上櫃 | {market} |\n"
    if beta is not None:
        md += f"| Beta | {beta:.2f} |\n"
    if market_cap:
        md += f"| 市值 | {_fmt_num(market_cap)} 元 |\n"
    return md


def section_price(data: Dict, db_latest: Dict) -> str:
    """即時價格."""
    if not db_latest:
        return "_無價格資料_"
    close = float(db_latest.get("Close") or 0)
    rows = db.ticker_history(data["ticker"], days=2)
    prev = rows[-2] if len(rows) >= 2 else {}
    prev_close = float(prev.get("Close") or 0)
    change = close - prev_close
    pct = (change / prev_close * 100) if prev_close else 0
    md = "| 項目 | 數值 |\n|---|---|\n"
    md += f"| 最新收盤 | {close:.2f} 元 |\n"
    md += f"| 漲跌 | {change:+.2f} ({pct:+.2f}%) |\n"
    md += f"| 開盤 | {db_latest.get('Open') or '—'} |\n"
    md += f"| 最高 | {db_latest.get('High') or '—'} |\n"
    md += f"| 最低 | {db_latest.get('Low') or '—'} |\n"
    vol = int(db_latest.get('Volume') or 0)
    md += f"| 成交量 | {vol:,} 張 ({vol/1000:,.0f}K 張) |\n"
    md += f"| 資料日期 | {db_latest.get('Date')} |\n"
    return md


def section_technical(data: Dict, db_latest: Dict) -> str:
    """技術分析."""
    if not db_latest:
        return "_無技術資料_"
    cur = float(db_latest.get("Close") or 0)
    sma13 = float(db_latest.get("sma_13") or 0)
    sma27 = float(db_latest.get("sma_27") or 0)
    sma54 = float(db_latest.get("sma_54") or 0)
    rsi14 = float(db_latest.get("rsi_14") or 0)
    atr14 = float(db_latest.get("atr_14") or 0)
    if not cur:
        return "_無技術資料_"
    if sma13 and sma27 and cur > sma13 > sma27:
        trend = "**多頭排列** (價 > MA13 > MA27)"
    elif sma13 and sma27 and cur < sma13 < sma27:
        trend = "**空頭排列** (價 < MA13 < MA27)"
    else:
        trend = "**盤整/糾結** (均線交錯)"
    rsi_label = "超買" if rsi14 > 70 else "超賣" if rsi14 < 30 else "中性"
    md = "| 指標 | 數值 |\n|---|---|\n"
    md += f"| 收盤 | {cur:.2f} |\n"
    md += f"| MA13 | {sma13:.2f} |\n"
    md += f"| MA27 | {sma27:.2f} |\n"
    md += f"| MA54 | {sma54:.2f} |\n"
    md += f"| RSI(14) | {rsi14:.2f} ({rsi_label}) |\n"
    md += f"| ATR(14) | {atr14:.2f} |\n"
    md += f"\n**趨勢判定：{trend}**\n"
    return md


def section_valuation(data: Dict, history: List[Dict] = None) -> str:
    """估值 (yfinance + FinMind cross-verify) with DB fallback for missing fields."""
    val = data.get("valuation", {}) or {}
    fm_pe = data.get("finmind_pe_latest", {}) or {}
    ticker = data.get("ticker", "")

    # DB fallback for 52w high/low, market cap, beta
    db_52w_h = db_52w_l = None
    db_mcap = None
    if history:
        try:
            closes = [float(r.get("Close") or 0) for r in history if r.get("Close")]
            if closes:
                db_52w_h = max(closes)
                db_52w_l = min(closes)
        except Exception:
            pass
    if ticker:
        try:
            import db_client as dbb
            cap = dbb.market_cap_estimate(ticker)
            if cap:
                db_mcap = cap
        except Exception:
            pass

    md = "| 指標 | yfinance | FinMind | 差異 |\n|---|---|---|---|\n"
    # PE
    pe_yf = val.get("pe"); pe_fm = fm_pe.get("PER")
    pe_yf_s = f"{pe_yf:.2f}" if pe_yf else "—"
    pe_d = ""
    if pe_yf and pe_fm:
        d = (pe_yf - pe_fm) / pe_fm * 100
        pe_d = f"{d:+.1f}%"
    md += f"| P/E | {pe_yf_s} | {pe_fm or '—'} | {pe_d} |\n"
    # Forward PE
    md += f"| Forward P/E | {val.get('forward_pe') or '—'} | — | — |\n"
    # PBR
    pb_yf = val.get("pb"); pb_fm = fm_pe.get("PBR")
    pb_yf_s = f"{pb_yf:.2f}" if pb_yf else "—"
    pb_d = ""
    if pb_yf and pb_fm:
        d = (pb_yf - pb_fm) / pb_fm * 100
        pb_d = f"{d:+.1f}%"
    md += f"| P/B | {pb_yf_s} | {pb_fm or '—'} | {pb_d} |\n"
    # Dividend yield
    dy_yf = val.get("dividend_yield")
    dy_fm_pct = fm_pe.get("dividend_yield")
    if dy_yf is not None and dy_yf > 0.5:
        dy_yf_pct = dy_yf
    elif dy_yf is not None:
        dy_yf_pct = dy_yf * 100
    else:
        dy_yf_pct = None
    dy_d = ""
    if dy_yf_pct is not None and dy_fm_pct:
        d = (dy_yf_pct - float(dy_fm_pct))
        dy_d = f"{d:+.2f}pp"
    dy_yf_pct_s = f"{dy_yf_pct:.2f}" if dy_yf_pct is not None else "—"
    md += f"| 殖利率 | {dy_yf_pct_s}% | {dy_fm_pct or '—'}% | {dy_d} |\n"
    # Market cap (yfinance > DB fallback)
    mcap = val.get("market_cap") or db_mcap
    mcap_s = _fmt_num(mcap) + " 元" if mcap else "—"
    md += f"| 市值 | {mcap_s} | — | {'(DB 估算)' if not val.get('market_cap') and db_mcap else ''} |\n"
    # 52w
    h52 = val.get("fifty_two_week_high") or db_52w_h
    l52 = val.get("fifty_two_week_low") or db_52w_l
    md += f"| 52週高 | {h52 or '—'} | — | {'(DB)' if not val.get('fifty_two_week_high') and db_52w_h else ''} |\n"
    md += f"| 52週低 | {l52 or '—'} | — | {'(DB)' if not val.get('fifty_two_week_low') and db_52w_l else ''} |\n"
    # Beta
    md += f"| Beta | {val.get('beta') or '—'} | — | — |\n"
    if not pe_yf and not pe_fm and not val.get("market_cap"):
        md += "\n_⚠️ 估值資料不完整：yfinance 無資料（可能 404）、FinMind 也無 PE。可手動從財報計算。_\n"
    return md


def section_fundamentals(data: Dict) -> str:
    """季報 P&L (last 6 quarters, pivoted into proper columns)."""
    fins = (data.get("fundamentals") or {}).get("rows", [])
    if not fins:
        return "_無季報資料_"
    # Pivot: group by date, map type (English) / origin_name (Chinese) → canonical key
    # Both English (FinMind `type` field) and Chinese (`origin_name` field) supported
    key_aliases = {
        "revenue": ["Revenue", "營業收入", "銷貨收入", "營業收入淨額"],
        "cogs":    ["CostOfGoodsSold", "營業成本", "銷貨成本"],
        "gross":   ["GrossProfit", "營業毛利（毛損）", "營業毛利", "毛利"],
        "opex":    ["OperatingExpenses", "營業費用"],
        "op":      ["OperatingIncome", "營業利益（損失）", "營業利益", "營業淨利"],
        "nonop":   ["TotalNonoperatingIncomeAndExpense", "營業外收入及支出"],
        "pretax":  ["PreTaxIncome", "稅前淨利（淨損）", "繼續營業單位稅前淨利"],
        "ni":      ["TotalConsolidatedProfitForThePeriod", "本期淨利（淨損）", "淨利（淨損）",
                    "IncomeFromContinuingOperations", "ProfitLoss"],
        "eps":     ["EPS", "基本每股盈餘"],
    }
    pivot: Dict[str, Dict[str, float]] = {}
    for r in fins:
        if not isinstance(r, dict):
            continue
        date = str(r.get("date", "")).strip()
        if not date:
            continue
        # Try type first (English), fall back to origin_name (Chinese)
        type_name = r.get("type", "") or ""
        origin_name = r.get("origin_name", "") or ""
        try:
            val = float(r.get("value") or 0)
        except (TypeError, ValueError):
            continue
        canonical = None
        for k, aliases in key_aliases.items():
            for a in aliases:
                if a and (a == type_name or a == origin_name or a in type_name or a in origin_name):
                    canonical = k
                    break
            if canonical:
                break
        if not canonical:
            continue
        pivot.setdefault(date, {})[canonical] = val
    if not pivot:
        return "_無季報資料（無法 pivot）_"
    # Sort by date desc, take last 6
    sorted_dates = sorted(pivot.keys(), reverse=True)[:6]
    sorted_dates.reverse()
    md = "| 季度 | 營收(億) | 毛利(億) | 營業利益(億) | 稅後淨利(億) | EPS(元) |\n|---|---|---|---|---|---|\n"
    for d in sorted_dates:
        row = pivot[d]
        rev = row.get("revenue", 0)
        gp = row.get("gross", 0)
        op = row.get("op", 0)
        ni = row.get("ni", 0)
        eps = row.get("eps", 0)
        rev_g = rev / 1e8 if rev else 0
        gp_g = gp / 1e8 if gp else 0
        op_g = op / 1e8 if op else 0
        ni_g = ni / 1e8 if ni else 0
        eps_s = f"{eps:.2f}" if eps else "—"
        d_short = d[2:7].replace("-", "Q")  # 25-Q4
        md += f"| {d_short} | {rev_g:.1f} | {gp_g:.1f} | {op_g:.1f} | {ni_g:.1f} | {eps_s} |\n"
    md += "\n_資料來源：FinMind TaiwanStockFinancialStatements（current）_"
    return md


def section_finlab_roe(data: Dict, history: List[Dict]) -> str:
    """ROE 從 yfinance (TTM) + FinMind 季報 (最近 6 季) — 杜邦式分析."""
    yf = data.get("yfinance", {})
    roe_yf = yf.get("returnOnEquity")
    fins = (data.get("fundamentals") or {}).get("rows", [])

    # Aggregate FinMind 季報 (equity, net income) by date
    quarter_data = {}  # date -> {equity, ni, eps}
    for r in fins:
        if not isinstance(r, dict): continue
        date = str(r.get("date", ""))[:10]
        if not date: continue
        t = r.get("type", "")
        if t in ("EquityAttributableToOwnersOfParent", "Equity"):
            quarter_data.setdefault(date, {})["equity"] = float(r.get("value", 0))
        elif t in ("IncomeAfterTaxes", "ProfitLoss", "TotalConsolidatedProfitForThePeriod"):
            quarter_data.setdefault(date, {})["ni"] = float(r.get("value", 0))
        elif t == "EPS":
            quarter_data.setdefault(date, {})["eps"] = float(r.get("value", 0))

    md = "### ROE 比較\n\n"
    md += "| 期間 | 來源 | ROE |\n|---|---|---|\n"
    if roe_yf is not None:
        md += f"| TTM (近 12 月) | yfinance | **{roe_yf*100:.2f}%** |\n"

    # Quarterly ROE: NI / Equity × 4 (annualized)
    sorted_dates = sorted(quarter_data.keys(), reverse=True)[:6]
    for date in sorted_dates:
        qd = quarter_data[date]
        if "equity" in qd and "ni" in qd and qd["equity"] > 0:
            roe_q = (qd["ni"] / qd["equity"]) * 4 * 100  # annualized
            md += f"| {date} (Q) | FinMind 季報 (年化) | {roe_q:.2f}% |\n"
    md += "\n"
    # Add DB-derived ROE fallback: use price/book + EPS to estimate
    if roe_yf is None and not sorted_dates:
        # Try to compute from DB
        ticker = data.get("ticker", "")
        if ticker:
            try:
                import db_client as dbb
                cap = dbb.market_cap_estimate(ticker)
                pb = None
                # Get P/B from FinMind PER
                fm_pe = data.get("finmind_pe_latest", {}) or {}
                pb = fm_pe.get("PBR")
                if cap and pb and pb > 0:
                    equity = cap / pb
                    # Use latest EPS from quarter_data
                    latest_eps = 0
                    if sorted_dates and "eps" in quarter_data[sorted_dates[0]]:
                        latest_eps = quarter_data[sorted_dates[0]]["eps"]
                    elif sorted_dates and "ni" in quarter_data[sorted_dates[0]] and "equity" in quarter_data[sorted_dates[0]]:
                        # Estimate from NI and shares (rough)
                        pass
                    if equity > 0:
                        md += f"| 估算 (DB 市值/P/B) | tw-invest-suite | (需 EPS 計算) |\n"
                        md += f"\n_💡 yfinance 無 ROE、FinMind 季報缺 equity 欄位。改用市值 { _fmt_num(cap) } ÷ P/B {pb:.2f} = { _fmt_num(equity) } 推算權益。EPS 從季報取得可算出真實 ROE。_\n"
            except Exception:
                pass
        if roe_yf is None and not sorted_dates:
            md += "_⚠️ 無 ROE 資料：yfinance 沒抓到（可能 404）+ FinMind 季報缺 equity/ni 欄位。_\n"
            md += "_建議：手動從公司財報計算 ROE = 全年淨利 / 平均權益，或參考公司年報。_\n"
    return md


def section_monthly_revenue(data: Dict) -> str:
    """月營收 + YoY (FinMind TaiwanStockMonthRevenue)."""
    rev = data.get("monthly_revenue", [])
    if not rev:
        return "_無月營收資料_"
    md = "| 月份 | 營收 (元) | YoY |\n|---|---|---|\n"
    for r in rev[-12:]:
        try:
            y = int(r.get("revenue_year", 0))
            m = int(r.get("revenue_month", 0))
            v = float(r.get("revenue", 0))
            yoy = r.get("yoy_pct")
            yoy_s = f"{yoy:+.1f}%" if yoy is not None else "—"
            md += f"| {y}-{m:02d} | {_fmt_num(v)} | {yoy_s} |\n"
        except (KeyError, ValueError, TypeError):
            continue
    return md


def section_dividends(data: Dict) -> str:
    """配息歷史 (FinMind TaiwanStockDividend, last 6)."""
    divs = data.get("dividends", [])
    if not divs:
        return "_無配息資料_"
    md = "| 配息年度 | 現金股利 | 股票股利 | 除息日 |\n|---|---|---|---|\n"
    for r in divs:
        try:
            yr = r.get("year", "")
            cash = float(r.get("CashEarningsDistribution") or 0)
            stock = float(r.get("StockEarningsDistribution") or 0)
            exd = r.get("CashExDividendTradingDate") or "—"
            md += f"| {yr} | {cash:.2f} | {stock:.2f} | {exd} |\n"
        except (KeyError, ValueError, TypeError):
            continue
    return md


def section_news(data: Dict) -> str:
    """新聞 (FinMind + DB fallback)."""
    news = data.get("news", [])
    if not news:
        return "_無新聞資料_"
    md = ""
    for n in news[:5]:
        date = n.get("date", "")
        title = n.get("title", "")
        source = n.get("source", "")
        link = n.get("link", "")
        if hasattr(date, "strftime"):
            date = date.strftime("%Y-%m-%d")
        else:
            date = str(date)[:10]
        if link:
            md += f"- **{date}** [{title}]({link}) — {source}\n"
        else:
            md += f"- **{date}** {title} — {source}\n"
    return md


def section_news_db(ticker: str) -> str:
    """新聞 from DB — 卡片式（一行一則，標題 + 來源 + 日期 + 情緒 icon）。"""
    import db_client as db
    rows = db.recent_news(ticker, limit=10)
    if not rows:
        return "<div class='news-empty'>_無新聞資料_</div>"
    html = "<div class='news-list'>"
    for r in rows:
        title = r.get("title", "")
        source = r.get("source", "—")
        date = r.get("published_at") or r.get("date", "")
        if hasattr(date, "strftime"):
            date = date.strftime("%Y-%m-%d %H:%M")
        else:
            date = str(date)[:16]
        link = r.get("link", "") or r.get("url", "")
        sentiment = r.get("sentiment_label", "")
        # Sentiment icon
        s_icon = "😐"
        s_class = "news-neutral"
        if sentiment:
            sl = str(sentiment).lower()
            if "pos" in sl or "bull" in sl or "good" in sl or "樂" in sl or "多" in sl:
                s_icon = "🔥"
                s_class = "news-pos"
            elif "neg" in sl or "bear" in sl or "bad" in sl or "悲" in sl or "空" in sl:
                s_icon = "⚠️"
                s_class = "news-neg"
        # Truncate long title
        title_display = title[:80] + ("..." if len(title) > 80 else "")
        # Build card
        html += "<div class='news-item'>"
        html += f"<div class='news-meta'><span class='news-icon {s_class}'>{s_icon}</span><span class='news-date'>{_esc(date)}</span><span class='news-source'>{_esc(source)}</span></div>"
        if link:
            html += f"<a class='news-title' href='{_esc(link)}' target='_blank' rel='noopener'>{_esc(title_display)}</a>"
        else:
            html += f"<div class='news-title'>{_esc(title_display)}</div>"
        html += "</div>"
    html += "</div>"
    return html


def section_zen(data: Dict, history: List[Dict]) -> str:
    """Chanlun (纏論) 分析."""
    ticker = data["ticker"]
    try:
        # zen.analyze(ticker) returns a ZenRead dataclass (NOT a dict)
        read = zen.analyze(ticker, days=120)
        if not read:
            return "_無 Chanlun 資料_"
        md = ""
        # 結構
        if hasattr(read, "center") and read.center:
            c = read.center
            md += f"**最近中樞**: {c.low:.2f} - {c.high:.2f}（{c.start_date} ~ {c.end_date}）\n\n"
        else:
            md += "**中樞**: 尚未形成\n\n"
        # Position & bias
        if hasattr(read, "position") and read.position:
            md += f"**位置**: {read.position}\n\n"
        if hasattr(read, "bias") and read.bias:
            md += f"**偏多/偏空**: {read.bias}\n\n"
        # Buy/sell candidates
        if hasattr(read, "buys") and read.buys:
            md += "**買點候選**:\n"
            for b in read.buys[:3]:
                md += f"- {b}\n"
            md += "\n"
        if hasattr(read, "sells") and read.sells:
            md += "**賣點候選**:\n"
            for s in read.sells[:3]:
                md += f"- {s}\n"
            md += "\n"
        # Invalidation
        if hasattr(read, "invalidation") and read.invalidation:
            md += f"**失效條件**: {read.invalidation}\n\n"
        if hasattr(read, "notes"):
            for n in read.notes[:3]:
                md += f"_備註: {n}_\n"
        return md.strip() or "_無 Chanlun 訊號_"
    except Exception as e:
        return f"_Chanlun 分析失敗：{e}_"


def section_institutional(ticker: str, db_latest: Dict) -> str:
    """法人買賣超 (近 20 日) — HTML 卡片式 + 彩色 cell + 內嵌 bar + 多日彙總。"""
    import db_client as db
    rows = db.ticker_history(ticker, days=22)
    if not rows:
        return "<div class='inst-source'>_無法人資料_</div>"
    rows = rows[-20:]
    # 轉成 (date, f, t, d, total)，並算 max_abs for bar scaling
    items = []
    for r in rows:
        try:
            f = float(r.get("ForeignNet") or 0) / 1000.0
            t = float(r.get("InvestmentNet") or 0) / 1000.0
            d = float(r.get("DealerNet") or 0) / 1000.0
            total = float(r.get("ThreeNet") or 0) / 1000.0
        except (TypeError, ValueError):
            f = t = d = total = 0
        d_str = str(r.get("Date"))[:10]
        items.append({"date": d_str, "f": f, "t": t, "d": d, "total": total})
    # max abs for bar scaling (per row's total)
    max_abs = max((abs(x["total"]) for x in items), default=1) or 1
    # 3 windows
    def _sum_window(n: int) -> Dict[str, float]:
        sub = items[-n:] if len(items) >= n else items
        return {
            "f": sum(x["f"] for x in sub),
            "t": sum(x["t"] for x in sub),
            "d": sum(x["d"] for x in sub),
            "total": sum(x["total"] for x in sub),
        }
    w5 = _sum_window(5)
    w10 = _sum_window(10)
    w20 = _sum_window(20)
    def _cls(v: float) -> str:
        if v > 0: return "pos"
        if v < 0: return "neg"
        return ""
    def _sign(v: float) -> str:
        if v == 0: return "0"
        return f"{v:+,.0f}"
    # === Summary cards (5d / 10d / 20d) ===
    def _sum_card(label: str, w: Dict[str, float]) -> str:
        cls_t = _cls(w["total"])
        return (
            f"<div class='inst-sum-card'>"
            f"<div class='inst-sum-label'>{label} 累計</div>"
            f"<div class='inst-sum-grid'>"
            f"<span class='inst-sum-key'>合計</span><span class='inst-sum-val {cls_t}'>{_sign(w['total'])} 張</span>"
            f"<span class='inst-sum-key'>外資</span><span class='inst-sum-val {_cls(w['f'])}'>{_sign(w['f'])}</span>"
            f"<span class='inst-sum-key'>投信</span><span class='inst-sum-val {_cls(w['t'])}'>{_sign(w['t'])}</span>"
            f"<span class='inst-sum-key'>自營</span><span class='inst-sum-val {_cls(w['d'])}'>{_sign(w['d'])}</span>"
            f"</div></div>"
        )
    summary_html = "<div class='inst-summary'>" + _sum_card("近 5 日", w5) + _sum_card("近 10 日", w10) + _sum_card(f"近 {len(items)} 日", w20) + "</div>"
    # === Table ===
    def _cell(v: float, show_zero: bool = True) -> str:
        if v == 0 and not show_zero:
            return "<span class='inst-num zero'>—</span>"
        if v == 0:
            return "<span class='inst-num zero'>0</span>"
        bar_pct = min(abs(v) / max_abs * 100, 100) if max_abs else 0
        cls = _cls(v)
        return (
            f"<span class='inst-cell'>"
            f"<span class='inst-bar-wrap'><span class='inst-bar {cls}' style='width:{bar_pct:.0f}%'></span></span>"
            f"<span class='inst-num {cls}'>{_sign(v)}</span>"
            f"</span>"
        )
    table_rows = []
    # Newest first
    for x in reversed(items):
        total = x["total"]
        row_cls = ""
        if total > max_abs * 0.6: row_cls = "hot-up"
        elif total < -max_abs * 0.6: row_cls = "hot-dn"
        tr = (
            f"<tr class='{row_cls}'>"
            f"<td class='date-col'>{_esc(x['date'])}</td>"
            f"<td>{_cell(x['f'])}</td>"
            f"<td>{_cell(x['t'])}</td>"
            f"<td>{_cell(x['d'])}</td>"
            f"<td class='total-cell'>{_cell(total)}</td>"
            f"</tr>"
        )
        table_rows.append(tr)
    table_html = (
        "<div class='inst-table-wrap'>"
        "<table class='inst-table'>"
        "<thead><tr>"
        "<th class='date-col'>日期</th>"
        "<th>外資 (張)</th><th>投信 (張)</th><th>自營 (張)</th>"
        "<th>合計 (張)</th>"
        "</tr></thead>"
        "<tbody>" + "".join(table_rows) + "</tbody>"
        "</table></div>"
    )
    # === Legend + source ===
    legend = (
        "<div class='inst-source'>"
        "<span style='color:#ec7063'>■ 買超</span> · "
        "<span style='color:#58d68d'>■ 賣超</span> · "
        "色塊 = 該日合計相對最大絕對值的比例 · "
        "<em>資料來源：MySQL `daily_data2_full`</em>"
        "</div>"
    )
    # Chart data marker (for stacked bar chart)
    import json
    chart_marker = "<!--CHART_DATA_INST " + json.dumps({
        "dates": [x["date"] for x in items],
        "foreign": [x["f"] for x in items],
        "trust": [x["t"] for x in items],
        "dealer": [x["d"] for x in items],
        "total": [x["total"] for x in items],
    }, ensure_ascii=False) + " -->"
    return summary_html + table_html + legend + chart_marker


def section_margin(ticker: str, db_latest: Dict) -> str:
    """融資融券 (近 30 日) — from DB."""
    import db_client as db
    if not db_latest:
        return "_無融資資料_"
    mb = int(db_latest.get("MarginBalance") or 0)
    ms = int(db_latest.get("ShortBalance") or 0)
    ratio = (mb / ms) if ms else None
    ratio_s = f"{ratio:.1f}" if ratio else "—"
    # Get trend (last 30 days)
    rows = db.ticker_history(ticker, days=32)
    rows = rows[-30:] if rows else []
    mb_trend = [int(r.get("MarginBalance") or 0) for r in rows]
    ms_trend = [int(r.get("ShortBalance") or 0) for r in rows]
    mb_change = (mb_trend[-1] - mb_trend[0]) / 1000 if len(mb_trend) >= 2 else 0
    ms_change = (ms_trend[-1] - ms_trend[0]) / 1000 if len(ms_trend) >= 2 else 0
    md = "| 項目 | 數值 | 30 日變化 |\n|---|---|---|\n"
    md += f"| 融資餘額 | **{mb:,} 張** | {mb_change:+,.0f} 張 |\n"
    md += f"| 融券餘額 | **{ms:,} 張** | {ms_change:+,.0f} 張 |\n"
    md += f"| 融資融券比 | {ratio_s} | — |\n"
    md += f"| 券資比 | {(ms/mb*100 if mb else 0):.1f}% | — |\n"
    md += "\n_資料來源：MySQL `daily_data2_full` (DB)_"
    return md


def master_tags_full(ticker: str, data: Dict, db_latest: Dict) -> str:
    """Hedge-fund master tags for ALL tickers — 18 experts from hedge-fund-expert-team.

    12 投資大師: 巴菲特/芒格/葛拉漢/林奇/達摩達蘭/伯里/伍德/阿克曼/德魯肯米勒/費雪/帕布萊/鈕亨沃拉
    4 專業分析師: 估值/情緒/基本面/技術
    2 管理專家: 風險管理/組合管理
    """
    tags = []
    try:
        yf = data.get("yfinance", {}) or {}
        val = data.get("valuation", {}) or {}
        pe = val.get("pe"); pb = val.get("pb")
        dy = val.get("dividend_yield")
        mcap = val.get("market_cap")
        roe = yf.get("returnOnEquity")
        beta = yf.get("beta")
        f52w_high = val.get("fifty_two_week_high")
        f52w_low = val.get("fifty_two_week_low")
        rev_yoy = None
        rev_list = data.get("monthly_revenue", [])
        if rev_list and isinstance(rev_list[-1], dict):
            rev_yoy = rev_list[-1].get("yoy_pct")
        cur = float(db_latest.get("Close") or 0) if db_latest else 0
        sma13 = float(db_latest.get("sma_13") or 0) if db_latest else 0
        sma27 = float(db_latest.get("sma_27") or 0) if db_latest else 0
        rsi14 = float(db_latest.get("rsi_14") or 0) if db_latest else 0
        foreign_net = int(db_latest.get("ForeignNet") or 0) if db_latest else 0
        rets = db.long_term_returns_batch([ticker], str(db_latest.get("Date")) if db_latest else None)
        ret_240 = rets.get(ticker, {}).get("ret_240d", 0) or 0
        ret_120 = rets.get(ticker, {}).get("ret_120d", 0) or 0
        ret_60 = rets.get(ticker, {}).get("ret_60d", 0) or 0
        ret_20 = rets.get(ticker, {}).get("ret_20d", 0) or 0

        # ===== Tier 1: 12 投資大師 =====

        # 1. 巴菲特 Buffett — 護城河/價值/大市值
        if roe and roe > 0.15:
            tags.append(f'<span class="tag tag-green">巴菲特</span> 護城河 ROE {roe*100:.0f}%')
        if pe and 0 < pe < 15:
            tags.append(f'<span class="tag tag-green">巴菲特</span> 價值 P/E {pe:.0f}')
        if mcap and mcap > 1e12:
            tags.append(f'<span class="tag tag-green">巴菲特</span> 大市值 {_fmt_num(mcap)}')

        # 2. 芒格 Munger — 多元思維/優質合理
        if roe and roe > 0.20 and pe and 0 < pe < 25:
            tags.append(f'<span class="tag tag-cyan">芒格</span> 優質合理 ROE {roe*100:.0f}% P/E {pe:.0f}')
        if rsi14 and 40 <= rsi14 <= 60 and ret_240 > 0.1:
            tags.append(f'<span class="tag tag-cyan">芒格</span> 合理價位 RSI {rsi14:.0f}')

        # 3. 葛拉漢 Graham — 深度價值/淨值
        if pb and 0 < pb < 1.5:
            tags.append(f'<span class="tag tag-blue">葛拉漢</span> 淨值 P/B {pb:.2f}')
        if pe and 0 < pe < 10:
            tags.append(f'<span class="tag tag-blue">葛拉漢</span> 價值 P/E {pe:.0f}')

        # 4. 林奇 Lynch — 成長股/PEG
        if rev_yoy is not None and pe and rev_yoy > 15:
            peg = pe / rev_yoy
            if peg < 1.0:
                tags.append(f'<span class="tag tag-cyan">林奇</span> PEG {peg:.1f} 十倍股候選')
            elif peg < 1.5:
                tags.append(f'<span class="tag tag-cyan">林奇</span> PEG {peg:.1f} 成長合理')
        if ret_120 and ret_60 and ret_120 > 0.3 and ret_60 > 0.1:
            tags.append(f'<span class="tag tag-cyan">林奇</span> 動能強 120d +{ret_120*100:.0f}%')

        # 5. 達摩達蘭 Damodaran — 估值紀律/DCF
        if pe and pe > 30 and (rev_yoy is None or rev_yoy < 10):
            tags.append(f'<span class="tag tag-yellow">達摩達蘭</span> 估值偏高 P/E {pe:.0f}')
        elif pe and 10 < pe < 20:
            tags.append(f'<span class="tag tag-green">達摩達蘭</span> 合理估值 P/E {pe:.0f}')

        # 6. 伯里 Burry — 逆向/做空/被低估
        if rsi14 and rsi14 < 30 and pb and 0 < pb < 1.0:
            tags.append(f'<span class="tag tag-purple">伯里</span> 深度價值 P/B {pb:.2f} RSI {rsi14:.0f}')
        if foreign_net < -1000 and cur < sma27:
            tags.append(f'<span class="tag tag-purple">伯里</span> 外資棄守 外資 {foreign_net/1000:,.0f} 張')

        # 7. 伍德 Wood — 顛覆創新/TAM/S曲線
        if rev_yoy is not None and rev_yoy > 50:
            tags.append(f'<span class="tag tag-cyan">伍德</span> 顛覆性成長 YoY +{rev_yoy:.0f}%')
        if mcap and 0 < mcap < 1e11 and ret_240 > 1.0:
            tags.append(f'<span class="tag tag-cyan">伍德</span> 小巨人 240d +{ret_240*100:.0f}%')

        # 8. 阿克曼 Ackman — 激進投資/公司治理
        if mcap and mcap > 5e11 and pb and 0 < pb < 2.0:
            tags.append(f'<span class="tag tag-blue">阿克曼</span> 大型價值 P/B {pb:.2f}')
        if roe and roe > 0.10 and ret_120 < -0.2:
            tags.append(f'<span class="tag tag-blue">阿克曼</span> 困境反轉 ROE {roe*100:.0f}% 跌 {ret_120*100:.0f}%')

        # 9. 德魯肯米勒 Druckenmiller — 宏觀/不對稱
        if beta and beta > 1.3 and ret_60 > 0.15:
            tags.append(f'<span class="tag tag-yellow">德魯肯米勒</span> 高 β 順風 β {beta:.1f}')
        if ret_60 > 0.3:
            tags.append(f'<span class="tag tag-yellow">德魯肯米勒</span> 動能爆發 60d +{ret_60*100:.0f}%')

        # 10. 費雪 Fisher — 成長先驅/長期持有
        if rev_yoy is not None and rev_yoy > 20:
            tags.append(f'<span class="tag tag-purple">費雪</span> 高成長 月營收 YoY +{rev_yoy:.0f}%')
        if ret_240 > 0.5:
            tags.append(f'<span class="tag tag-purple">費雪</span> 長股 240d +{ret_240*100:.0f}%')

        # 11. 帕布萊 Pabrai — Dhandho/低風險高回報
        if rsi14 and rsi14 < 35:
            tags.append(f'<span class="tag tag-green">帕布萊</span> 撿便宜 RSI {rsi14:.0f}')
        if beta is not None and beta < 0.8:
            tags.append(f'<span class="tag tag-green">帕布萊</span> 低風險 β {beta:.2f}')

        # 12. 鈕亨沃拉 Jhunjhunwala — 新興市場/行業龍頭
        if mcap and ret_240 > 0.3 and roe and roe > 0.15:
            tags.append(f'<span class="tag tag-cyan">鈕亨沃拉</span> 龍頭新興 ROE {roe*100:.0f}% 240d +{ret_240*100:.0f}%')
        if mcap and 1e10 < mcap < 5e10 and ret_120 > 0.2:
            tags.append(f'<span class="tag tag-cyan">鈕亨沃拉</span> 中小龍頭 120d +{ret_120*100:.0f}%')

        # ===== Tier 2: 4 專業分析師 =====

        # 13. 估值分析師
        if pe and pe < 12 and roe and roe > 0.10:
            tags.append(f'<span class="tag tag-green">估值師</span> 低估 P/E {pe:.0f} + ROE {roe*100:.0f}%')
        elif pe and pe > 40:
            tags.append(f'<span class="tag tag-red">估值師</span> 高估 P/E {pe:.0f}')

        # 14. 情緒分析師 (based on foreign net + chip signals)
        if foreign_net > 1000:
            tags.append(f'<span class="tag tag-cyan">情緒師</span> 法人看多 +{foreign_net/1000:,.0f} 張')
        elif foreign_net < -1000:
            tags.append(f'<span class="tag tag-red">情緒師</span> 法人看空 {foreign_net/1000:,.0f} 張')

        # 15. 基本面分析師
        if roe and roe > 0.20:
            tags.append(f'<span class="tag tag-green">基本面師</span> 優質 ROE {roe*100:.0f}%')
        if rev_yoy is not None and rev_yoy > 30:
            tags.append(f'<span class="tag tag-green">基本面師</span> 營收加速 YoY +{rev_yoy:.0f}%')

        # 16. 技術分析師
        if sma13 and sma27 and cur > sma13 > sma27:
            tags.append('<span class="tag tag-green">技術師</span> 多頭排列')
        elif sma13 and sma27 and cur < sma13 < sma27:
            tags.append('<span class="tag tag-red">技術師</span> 空頭排列')
        if rsi14 and 50 <= rsi14 <= 65:
            tags.append(f'<span class="tag tag-green">技術師</span> RSI 甜蜜區 {rsi14:.0f}')

        # ===== Tier 3: 2 管理專家 =====

        # 17. 風險管理師
        if beta and beta > 1.5:
            tags.append(f'<span class="tag tag-yellow">風險師</span> 高 β {beta:.1f} 注意波動')
        if rsi14 and rsi14 > 75:
            tags.append(f'<span class="tag tag-red">風險師</span> 超買 RSI {rsi14:.0f} 風險升高')
        elif rsi14 and rsi14 < 25:
            tags.append(f'<span class="tag tag-yellow">風險師</span> 超賣 RSI {rsi14:.0f} 注意止損')

        # 18. 投資組合經理 — 綜合判斷
        # 多重訊號一致 → 高信心
        bull_signals = sum([
            1 if (roe and roe > 0.15) else 0,
            1 if (ret_240 and ret_240 > 0.3) else 0,
            1 if (foreign_net > 0) else 0,
            1 if (rev_yoy and rev_yoy > 15) else 0,
            1 if (sma13 and sma27 and cur > sma13 > sma27) else 0,
        ])
        if bull_signals >= 4:
            tags.append(f'<span class="tag tag-green">組合經理</span> 多頭共識 {bull_signals}/5 訊號一致')
        elif bull_signals <= 1:
            tags.append(f'<span class="tag tag-red">組合經理</span> 空頭共識 {5-bull_signals}/5 訊號一致')

        # ===== Technical signals =====
        if 50 <= rsi14 <= 65:
            tags.append(f'<span class="tag tag-green">RSI {rsi14:.0f} 甜蜜區</span>')
        elif rsi14 > 70:
            tags.append(f'<span class="tag tag-red">RSI {rsi14:.0f} 過熱</span>')
        elif rsi14 < 30:
            tags.append(f'<span class="tag tag-green">RSI {rsi14:.0f} 超賣</span>')
        if dy is not None and dy > 0.5:
            dy_pct = dy if dy > 0.5 else dy * 100
            tags.append(f'<span class="tag tag-cyan">高股息 {dy_pct:.1f}%</span>')
    except Exception as e:
        tags.append(f'<span class="tag tag-yellow">tags 取得失敗: {e}</span>')
    return '<div class="tags">' + "".join(tags) + '</div>' if tags else ''


def section_minerva(data: Dict, db_latest: Dict, history: List[Dict]) -> str:
    """Minerva 量化交易策略 — 5 factor scoring (momentum/value/quality/volatility/size).
    Output: 0-100 score for each factor + composite + radar chart.
    """
    try:
        yf = data.get("yfinance", {}) or {}
        val = data.get("valuation", {}) or {}
        pe = val.get("pe") or 50
        pb = val.get("pb") or 3
        roe = (yf.get("returnOnEquity") or 0) * 100
        mcap = val.get("market_cap") or 0
        beta = yf.get("beta") or 1.0
        cur = float(db_latest.get("Close") or 0) if db_latest else 0
        # 1. Momentum (40%): ret_20/60/120/240 z-score
        rets = db.long_term_returns_batch([data["ticker"]], str(db_latest.get("Date")) if db_latest else None)
        r = rets.get(data["ticker"], {})
        ret_20 = (r.get("ret_20d") or 0) * 100
        ret_60 = (r.get("ret_60d") or 0) * 100
        ret_120 = (r.get("ret_120d") or 0) * 100
        ret_240 = (r.get("ret_240d") or 0) * 100
        # momentum score: avg of returns, normalized
        mom = min(100, max(0, 50 + (ret_20 + ret_60 + ret_120 + ret_240) / 8))
        # 2. Value (25%): low P/E + low P/B
        val_score = min(100, max(0, 100 - pe * 2 - pb * 10))
        # 3. Quality (20%): high ROE
        qual = min(100, max(0, roe * 3 + 30))
        # 4. Volatility (10%): low beta preferred
        vol = min(100, max(0, 100 - abs(beta - 1) * 30))
        # 5. Size (5%): larger market cap better (institutional-grade)
        if mcap > 1e12: size = 100
        elif mcap > 1e11: size = 80
        elif mcap > 1e10: size = 60
        elif mcap > 1e9: size = 40
        else: size = 20
        # Composite weighted score
        composite = mom * 0.4 + val_score * 0.25 + qual * 0.20 + vol * 0.10 + size * 0.05
        # Star rating
        stars = "★★★★★" if composite >= 80 else "★★★★" if composite >= 60 else "★★★" if composite >= 40 else "★★" if composite >= 20 else "★"
        md = f"### Minerva 量化評分：{composite:.0f}/100 {stars}\n\n"
        md += "| 因子 | 權重 | 分數 | 信號 |\n|---|---|---|---|\n"
        for name, score, sig in [
            ("動能 (Momentum)", mom, "🚀" if mom > 60 else "📉" if mom < 40 else "➡️"),
            ("價值 (Value)", val_score, "💰" if val_score > 60 else "⚠️" if val_score < 40 else "➡️"),
            ("品質 (Quality)", qual, "✨" if qual > 60 else "⚠️" if qual < 40 else "➡️"),
            ("波動 (Volatility)", vol, "🛡️" if vol > 60 else "⚡" if vol < 40 else "➡️"),
            ("市值 (Size)", size, "🏛️" if size > 60 else "🪙" if size < 40 else "➡️"),
        ]:
            md += f"| {name} | 25-40% | {score:.0f} | {sig} |\n"
        md += f"| **加權綜合** | 100% | **{composite:.0f}** | {stars} |\n\n"
        # 個別指標細節
        md += "**原始數據**：\n"
        md += f"- 動能：20d {ret_20:+.1f}% · 60d {ret_60:+.1f}% · 120d {ret_120:+.1f}% · 240d {ret_240:+.1f}%\n"
        md += f"- 價值：P/E {pe:.1f} · P/B {pb:.2f}\n"
        md += f"- 品質：ROE {roe:.1f}%\n"
        md += f"- 波動：β {beta:.2f}\n"
        md += f"- 市值：{_fmt_num(mcap)}\n"
        return md
    except Exception as e:
        return f"_Minerva 量化評分失敗：{e}_"


def section_build_thesis(data: Dict, db_latest: Dict) -> str:
    """build-thesis — 兩面 thesis：LEFT (數字/共識) vs RIGHT (市場/動能)。
    What must be true + falsification criteria.
    """
    try:
        yf = data.get("yfinance", {}) or {}
        val = data.get("valuation", {}) or {}
        pe = val.get("pe"); pb = val.get("pb")
        roe = (yf.get("returnOnEquity") or 0) * 100
        rev_yoy = None
        rev_list = data.get("monthly_revenue", [])
        if rev_list and isinstance(rev_list[-1], dict):
            rev_yoy = rev_list[-1].get("yoy_pct")
        cur = float(db_latest.get("Close") or 0) if db_latest else 0
        sma13 = float(db_latest.get("sma_13") or 0) if db_latest else 0
        sma27 = float(db_latest.get("sma_27") or 0) if db_latest else 0
        rsi14 = float(db_latest.get("rsi_14") or 0) if db_latest else 0
        foreign_net = int(db_latest.get("ForeignNet") or 0) if db_latest else 0
        rets = db.long_term_returns_batch([data["ticker"]], str(db_latest.get("Date")) if db_latest else None)
        r = rets.get(data["ticker"], {})
        ret_60 = (r.get("ret_60d") or 0) * 100
        ret_240 = (r.get("ret_240d") or 0) * 100

        # LEFT — 數字/共識
        left_claims = []
        if roe > 15:
            left_claims.append(f"ROE {roe:.0f}% > 15% 顯示護城河")
        if pe and 0 < pe < 20:
            left_claims.append(f"P/E {pe:.0f} < 20 估值合理")
        if pb and 0 < pb < 2:
            left_claims.append(f"P/B {pb:.2f} < 2 淨值支撐")
        if rev_yoy is not None and rev_yoy > 10:
            left_claims.append(f"月營收 YoY +{rev_yoy:.0f}% 成長動能")
        # RIGHT — 市場/動能/資金
        right_claims = []
        if foreign_net > 0:
            right_claims.append(f"外資買超 +{foreign_net/1000:,.0f} 張 法人偏多")
        if sma13 and sma27 and cur > sma13 > sma27:
            right_claims.append(f"多頭排列 價 > MA13 {sma13:.0f} > MA27 {sma27:.0f}")
        if ret_60 > 0.1:
            right_claims.append(f"60d 動能 +{ret_60:.0f}% 順風")
        if rsi14 and 50 <= rsi14 <= 70:
            right_claims.append(f"RSI {rsi14:.0f} 中性偏強")
        elif rsi14 and rsi14 < 30:
            right_claims.append(f"RSI {rsi14:.0f} 超賣（可能是撿便宜機會）")

        # 決定 LEFT/RIGHT 訊號
        left_strong = len(left_claims) >= 2
        right_strong = len(right_claims) >= 2
        if left_strong and right_strong:
            thesis = "🟢 **多頭共識** — LEFT 數字 + RIGHT 市場 雙重確認"
        elif left_strong and not right_strong:
            thesis = "🟡 **價值陷阱疑慮** — LEFT 好但 RIGHT 沒跟，建議等市場確認"
        elif right_strong and not left_strong:
            thesis = "🟡 **動能拉抬** — RIGHT 強但 LEFT 數字弱，可能 overvalued"
        else:
            thesis = "🔴 **觀望** — LEFT/RIGHT 都沒明顯訊號"

        md = f"### {thesis}\n\n"
        # 4 段都改成「一行一訊息」純 bullet
        md += "**📊 LEFT — 數字/估值/財務體質：**\n"
        if left_claims:
            for c in left_claims:
                md += f"- ✅ {c}\n"
        else:
            md += "- ⚪ LEFT 訊號不足\n"
        md += "\n**📈 RIGHT — 市場/法人/動能/板塊：**\n"
        if right_claims:
            for c in right_claims:
                md += f"- ✅ {c}\n"
        else:
            md += "- ⚪ RIGHT 訊號不足\n"
        md += "\n**🔑 What must be true：**\n"
        if left_strong and right_strong:
            md += "- LEFT：基本面持續強勁（ROE、月營收 YoY 維持）\n- RIGHT：法人續買、技術維持多頭\n"
        elif left_strong:
            md += "- LEFT：基本面需維持強勁\n- RIGHT：等待法人/技術轉強訊號\n"
        elif right_strong:
            md += "- RIGHT：動能延續\n- LEFT：基本面接續上來（需驗證月營收/ROE）\n"
        else:
            md += "- 等待 LEFT 或 RIGHT 任一訊號強化\n"
        md += "\n**❌ Falsification：**\n"
        falses = []
        if rsi14 and rsi14 > 70:
            falses.append(f"RSI {rsi14:.0f} 超買 → 短期回檔風險")
        if foreign_net < -1000:
            falses.append(f"外資大賣 {foreign_net/1000:,.0f} 張 → 法人棄守")
        if ret_60 < -0.15:
            falses.append(f"60d 跌 {ret_60:.0f}% → 趨勢反轉")
        if pe and pe > 40:
            falses.append(f"P/E {pe:.0f} 過高 → 估值修正風險")
        if not falses:
            falses.append("目前無明確反轉訊號")
        for f in falses:
            md += f"- {f}\n"
        md += "\n_來源：build-thesis skill_\n"
        return md
    except Exception as e:
        return f"_build-thesis 失敗：{e}_"


def section_backtest(data: Dict, db_latest: Dict, history: List[Dict]) -> str:
    """backtest-orchestrator — 多策略回測 (使用 DB 歷史).
    Strategies:
      1. MA cross (close > sma_27)
      2. RSI oversold recovery (rsi < 35 → 持有 20 日)
      3. Foreign net inflow (3 日連買 → 持有 20 日)
    Walk-forward: 過去 240 天，每 30 日檢查一次
    """
    try:
        if not history or len(history) < 60:
            return "_資料不足 (< 60 日) 無法回測_"
        ticker = data["ticker"]
        # Build cleaned history
        rows = []
        for r in history:
            try:
                rows.append({
                    "date": r.get("Date"),
                    "close": float(r.get("Close") or 0),
                    "foreign": int(r.get("ForeignNet") or 0),
                    "rsi": float(r.get("rsi_14") or 50),
                    "sma27": float(r.get("sma_27") or 0),
                })
            except (TypeError, ValueError):
                continue
        if len(rows) < 60:
            return "_歷史資料不足_"

        def _backtest_strategy(sig_fn, hold=20, step=30):
            """sig_fn(idx, rows) -> True to enter, hold 20 days, return trades list."""
            trades = []
            for i in range(60, len(rows) - hold, step):
                if sig_fn(i, rows):
                    entry = rows[i]["close"]
                    exit_idx = min(i + hold, len(rows) - 1)
                    exit_p = rows[exit_idx]["close"]
                    ret = (exit_p - entry) / entry * 100
                    trades.append({"entry": rows[i]["date"], "exit": rows[exit_idx]["date"], "ret": ret})
            return trades

        def _stats(trades):
            if not trades:
                return None
            wins = [t for t in trades if t["ret"] > 0]
            losses = [t for t in trades if t["ret"] <= 0]
            win_rate = len(wins) / len(trades) * 100
            avg_ret = sum(t["ret"] for t in trades) / len(trades)
            max_win = max(t["ret"] for t in trades)
            max_loss = min(t["ret"] for t in trades)
            import statistics
            std = statistics.stdev(t["ret"] for t in trades) if len(trades) > 1 else 0
            sharpe = (avg_ret / std) if std > 0 else 0
            return {
                "n": len(trades), "wins": len(wins), "losses": len(losses),
                "win_rate": win_rate, "avg_ret": avg_ret,
                "max_win": max_win, "max_loss": max_loss, "sharpe": sharpe,
            }

        # Strategy 1: MA cross
        def s_ma(i, rs):
            return rs[i]["close"] > rs[i]["sma27"] and rs[i]["sma27"] > 0
        # Strategy 2: RSI oversold recovery
        def s_rsi(i, rs):
            return 30 <= rs[i]["rsi"] <= 45
        # Strategy 3: Foreign net 3-day positive
        def s_fgn(i, rs):
            if i < 3: return False
            return sum(rs[j]["foreign"] for j in range(i-2, i+1)) > 0

        strategies = [
            ("MA 趨勢 (close > MA27)", s_ma),
            ("RSI 中性偏低 (30~45)", s_rsi),
            ("外資 3 日連買", s_fgn),
        ]

        md = f"### Backtest 多策略回測 (過去 {len(rows)} 日)\n\n"
        md += f"_回測期間_: {rows[0]['date']} ~ {rows[-1]['date']}\n\n"
        md += "| 策略 | 交易次數 | 勝率 | 平均報酬 | 最大獲利 | 最大虧損 | Sharpe |\n"
        md += "|---|---|---|---|---|---|---|\n"
        all_valid = False
        for name, fn in strategies:
            trades = _backtest_strategy(fn, hold=20, step=30)
            s = _stats(trades)
            if s is None:
                md += f"| {name} | 0 | — | — | — | — | — |\n"
            else:
                all_valid = True
                md += f"| {name} | {s['n']} | {s['win_rate']:.0f}% | {s['avg_ret']:+.2f}% | {s['max_win']:+.2f}% | {s['max_loss']:+.2f}% | {s['sharpe']:.2f} |\n"
        if not all_valid:
            return "_無符合條件的交易可回測_"
        # 整體建議
        md += "\n**綜合判斷**：\n"
        # Best strategy
        best = max(((_stats(_backtest_strategy(fn, hold=20, step=30)) or {"avg_ret": -999})["avg_ret"] for _, fn in strategies))
        if best > 1:
            md += f"- 🟢 有 {best:+.1f}% 最佳策略報酬，建議關注對應訊號\n"
        elif best > -2:
            md += f"- 🟡 策略表現普通 (-2% ~ +1%)，無強烈訊號\n"
        else:
            md += f"- 🔴 策略整體偏弱 (< -2%)，建議觀望\n"
        md += "\n_來源：backtest-orchestrator skill (OpenAlice) — 簡化版 walk-forward_\n"
        return md
    except Exception as e:
        return f"_backtest 失敗：{e}_"


def section_traderhub(data: Dict, db_latest: Dict) -> str:
    """traderhub — 進出場點位 (entry/exit/stop/target).
    Uses ATR-based position sizing.
    """
    try:
        cur = float(db_latest.get("Close") or 0) if db_latest else 0
        atr14 = float(db_latest.get("atr_14") or 0) if db_latest else 0
        sma13 = float(db_latest.get("sma_13") or 0) if db_latest else 0
        sma27 = float(db_latest.get("sma_27") or 0) if db_latest else 0
        rsi14 = float(db_latest.get("rsi_14") or 0) if db_latest else 0
        if not cur or not atr14:
            return "_無價格資料_"
        # 進場策略：拉回到 MA13 附近 + RSI < 70
        entry_aggressive = round(cur, 2)
        entry_conservative = round(sma13, 2) if sma13 else round(cur * 0.98, 2)
        # 停損：-2 ATR
        stop_loss = round(cur - 2 * atr14, 2)
        # 目標：+3 ATR (風險報酬比 1.5:1)
        target_1 = round(cur + 2 * atr14, 2)
        target_2 = round(cur + 3 * atr14, 2)
        target_3 = round(cur + 5 * atr14, 2)
        # Kelly 建議倉位
        # Win rate ~ 55%, payoff 1.5:1 → Kelly ≈ 5% of capital
        kelly_pct = 5
        # 風險/股 (每股 1 張 = 1000 股)
        risk_per_share = cur - stop_loss
        shares_per_lot = 1000
        max_loss_per_lot = risk_per_share * shares_per_lot
        # Sizing: 假設單筆最大虧損 = 帳戶 1%
        if max_loss_per_lot > 0:
            account_size = 1_000_000  # 假設 100 萬
            max_lots = int(account_size * 0.01 / max_loss_per_lot)
        else:
            max_lots = 0
        md = f"### TraderHub 進出場策略 (ATR-based)\n\n"
        md += f"**現價**：{cur:.2f} · **ATR(14)**：{atr14:.2f} (波動度)\n\n"
        md += "| 項目 | 價格 | 說明 |\n|---|---|---|\n"
        md += f"| 進場（積極）| **{entry_aggressive:.2f}** | 現價直接進場 |\n"
        md += f"| 進場（保守）| **{entry_conservative:.2f}** | 拉回 MA13 進場 |\n"
        md += f"| 停損 | **{stop_loss:.2f}** | -2 ATR ({abs(stop_loss-cur)/cur*100:.1f}% from 現價) |\n"
        md += f"| 目標 1 | {target_1:.2f} | +2 ATR ({abs(target_1-cur)/cur*100:.1f}%) |\n"
        md += f"| 目標 2 | **{target_2:.2f}** | +3 ATR ({abs(target_2-cur)/cur*100:.1f}%) |\n"
        md += f"| 目標 3 | {target_3:.2f} | +5 ATR ({abs(target_3-cur)/cur*100:.1f}%) |\n"
        md += "\n**倉位建議**（Kelly 簡化）\n"
        md += f"- 單筆風險佔比：**{kelly_pct}%** of capital\n"
        md += f"- 每張最大虧損：{max_loss_per_lot:,.0f} 元 (假設 1 張 = 1000 股)\n"
        md += f"- 100 萬帳戶最多 {max_lots} 張 (1% 帳戶風險)\n"
        if rsi14 and rsi14 > 70:
            md += "\n⚠️ **警示**：RSI {0:.0f} 超買，建議分批進場或觀望\n".format(rsi14)
        md += "\n_來源：traderhub skill (OpenAlice) — 簡化版 ATR 倉位法_\n"
        return md
    except Exception as e:
        return f"_traderhub 失敗：{e}_"


EXPERT_VIEWS = {
    # 12 投資大師 — 每個大師的多個視角 (視角名, 觸發條件, 數據顯示, 白話意思)
    # 數據顯示用 {key} 佔位符，key 會被實際數值替換
    "巴菲特": [
        ("護城河", "roe > 0.15", "ROE {roe}", "公司賺錢效率極高，護城河很寬（一般 >15% 就算好，{roe} 顯示競爭優勢）"),
        ("價值", "0 < pe < 15", "P/E {pe}", "本益比 {pe} 倍，股價相對內在價值有折價，符合巴菲特「用 5 毛買 1 塊」原則"),
        ("大市值", "mcap > 1e12", "市值 {mcap_str}", "市值 {mcap_str} 屬大型權值股，符合巴菲特「只買大公司」偏好"),
    ],
    "芒格": [
        ("優質合理", "roe > 0.20 and 0 < pe < 25", "ROE {roe} P/E {pe}", "用合理價格買頂級公司：ROE {roe} + P/E {pe} 倍，是芒格口中的「胖球」"),
        ("合理價位", "rsi14 >= 40 and rsi14 <= 60 and ret_240 > 0.1", "RSI {rsi}", "RSI {rsi} 中性區間，加上 240d +{ret} 動能，芒格會說「現在買不丟人」"),
    ],
    "葛拉漢": [
        ("淨值", "0 < pb < 1.5", "P/B {pb}", "股價淨值比 {pb}，低於 1.5 代表市場低估資產價值，葛拉漢的安全邊際"),
        ("價值", "0 < pe < 10", "P/E {pe}", "本益比 {pe} 倍，葛拉漢式深度價值標的（<10 就算便宜）"),
    ],
    "林奇": [
        ("PEG", "rev_yoy is not None and rev_yoy > 0 and pe is not None and 0 < pe/rev_yoy < 1.0", "PEG {peg}", "PEG = P/E ÷ 成長率 = {peg}，<1 代表便宜，{peg} 極度便宜 → 林奇眼中的「十倍股」候選"),
        ("動能強", "ret_120 > 0.3 and ret_60 > 0.1", "120d +{r120}", "120d 漲 {r120} 加上 60d 漲 {r60}，林奇會繼續持有（「兩年翻倍就抱住」）"),
    ],
    "達摩達蘭": [
        ("估值偏高", "pe > 30 and (rev_yoy is None or rev_yoy < 10)", "P/E {pe}", "本益比 {pe} 但營收成長跟不上 → 估值教授警告：股價已透支未來"),
        ("合理估值", "10 < pe < 20", "P/E {pe}", "本益比 {pe} 倍，達摩達蘭算出來的合理價位區間"),
    ],
    "伯里": [
        ("深度價值", "rsi14 < 30 and 0 < pb < 1.0", "P/B {pb} RSI {rsi}", "P/B {pb} < 1 且 RSI {rsi} 嚴重超賣，伯里最愛的「市場錯價」標的"),
        ("外資棄守", "foreign_net < -1000 and cur < sma27", "外資 {fval} 張", "外資淨賣超 {fval} 張且跌破 MA27 — 聰明的錢正在撤離，是伯里逆向布局的訊號"),
    ],
    "伍德": [
        ("顛覆性成長", "rev_yoy is not None and rev_yoy > 50", "YoY +{yoy}", "月營收年增 {yoy}，伍德會找這種「破壞式創新」的高成長公司"),
        ("小巨人", "mcap is not None and 0 < mcap < 1e11 and ret_240 > 1.0", "240d +{ret}", "市值 < 100 億但 240d 漲 {ret}，伍德口中的「破壞式創新小巨人」"),
    ],
    "阿克曼": [
        ("大型價值", "mcap is not None and mcap > 5e11 and 0 < pb < 2.0", "P/B {pb}", "市值 > 5,000 億 + P/B {pb}，阿克曼會出手做「價值釋放」activist"),
        ("困境反轉", "roe is not None and roe > 0.10 and ret_120 < -0.2", "ROE {roe} 跌 {r120}", "ROE {roe} 體質好但 120d 跌 {r120}，阿克曼眼中的「被錯殺的優質股」"),
    ],
    "德魯肯米勒": [
        ("高 β 順風", "beta is not None and beta > 1.3 and ret_60 > 0.15", "β {beta}", "β {beta} 高敏感 + 60d 漲 {r60}，德魯肯米勒會加槓桿放大順風"),
        ("動能爆發", "ret_60 > 0.3", "60d +{r60}", "60d 漲 {r60}，德魯肯米勒會「All in」這種短期爆發"),
    ],
    "費雪": [
        ("高成長", "rev_yoy is not None and rev_yoy > 20", "YoY +{yoy}", "月營收年增 {yoy}，費雪的「15 個問題」會被滿足"),
        ("長股", "ret_240 > 0.5", "240d +{ret}", "240d 漲 {ret}，費雪會「買進後永遠不放」"),
    ],
    "帕布萊": [
        ("撿便宜", "rsi14 < 35", "RSI {rsi}", "RSI {rsi} 嚴重超賣，帕布萊「Dhandho 投資法」會出手"),
        ("低風險", "beta is not None and beta < 0.8", "β {beta}", "β {beta} (<1) 股價波動比大盤小，帕布萊會說「小風險大回報」"),
    ],
    "鈕亨沃拉": [
        ("龍頭新興", "ret_240 > 0.3 and roe is not None and roe > 0.15", "ROE {roe} 240d +{ret}", "ROE {roe} + 240d 漲 {ret}，鈕亨沃拉的「印度 Tata 集團」標的 — 行業龍頭"),
        ("中小龍頭", "mcap is not None and 1e10 < mcap < 5e10 and ret_120 > 0.2", "120d +{r120}", "市值 100-500 億 + 120d 漲 {r120}，新興市場的「未來台積電」"),
    ],
    # 4 專業分析師
    "估值師": [
        ("低估", "pe is not None and pe < 12 and roe is not None and roe > 0.10", "P/E {pe} + ROE {roe}", "P/E {pe} + ROE {roe}，明顯被低估"),
        ("高估", "pe is not None and pe > 40", "P/E {pe}", "P/E {pe} 過高，估值師建議觀望"),
    ],
    "情緒師": [
        ("法人看多", "foreign_net > 1000", "外資 +{fval} 張", "外資買超 {fval} 張，法人情緒偏多"),
        ("法人看空", "foreign_net < -1000", "外資 {fval} 張", "外資賣超 {fval} 張，法人情緒偏空"),
    ],
    "基本面師": [
        ("優質", "roe is not None and roe > 0.20", "ROE {roe}", "ROE {roe}，基本面師認可的優質股"),
        ("營收加速", "rev_yoy is not None and rev_yoy > 30", "YoY +{yoy}", "月營收 YoY +{yoy}，基本面成長加速"),
    ],
    "技術師": [
        ("多頭排列", "sma13 and sma27 and cur > sma13 > sma27", "MA13 > MA27", "均線多頭排列（價 {cur} > MA13 {sma13} > MA27 {sma27}），技術派會加碼"),
        ("空頭排列", "sma13 and sma27 and cur < sma13 < sma27", "MA13 < MA27", "均線空頭排列（價 {cur} < MA13 {sma13} < MA27 {sma27}），技術派會減碼"),
        ("RSI 甜蜜區", "rsi14 and 50 <= rsi14 <= 65", "RSI {rsi}", "RSI {rsi} 中性偏強，技術派最愛的位置"),
    ],
    "風險師": [
        ("高 β 注意", "beta is not None and beta > 1.5", "β {beta}", "β {beta} 高度波動，風險師建議控制倉位"),
        ("超買風險", "rsi14 and rsi14 > 75", "RSI {rsi}", "RSI {rsi} 過熱，短期回檔風險高"),
        ("超賣注意止損", "rsi14 and rsi14 < 25", "RSI {rsi}", "RSI {rsi} 嚴重超賣，風險師提醒要設好止損"),
    ],
    "組合經理": [
        ("多頭共識", "bull_signals >= 4", "{n}/5 訊號一致", "{n} 個多頭訊號（基本面/動能/法人/技術/總經）一致，組合經理建議加碼"),
        ("空頭共識", "bull_signals <= 1", "{n}/5 訊號反向", "{n} 個空頭訊號，組合經理建議減碼或避開"),
    ],
}


def _trigger_expert_views(data: Dict, db_latest: Dict) -> List[Dict]:
    """Evaluate each expert view condition and return triggered views."""
    if not db_latest:
        return []
    yf = data.get("yfinance", {}) or {}
    val = data.get("valuation", {}) or {}
    pe = val.get("pe")
    pb = val.get("pb")
    mcap = val.get("market_cap")
    roe = yf.get("returnOnEquity")
    beta = yf.get("beta")
    cur = float(db_latest.get("Close") or 0) if db_latest else 0
    sma13 = float(db_latest.get("sma_13") or 0) if db_latest else 0
    sma27 = float(db_latest.get("sma_27") or 0) if db_latest else 0
    rsi14 = float(db_latest.get("rsi_14") or 0) if db_latest else 0
    foreign_net = int(db_latest.get("ForeignNet") or 0) if db_latest else 0
    rev_yoy = None
    rev_list = data.get("monthly_revenue", [])
    if rev_list and isinstance(rev_list[-1], dict):
        rev_yoy = rev_list[-1].get("yoy_pct")
    rets = db.long_term_returns_batch([data["ticker"]], str(db_latest.get("Date")) if db_latest else None)
    r = rets.get(data["ticker"], {})
    ret_60 = (r.get("ret_60d") or 0) * 100
    ret_120 = (r.get("ret_120d") or 0) * 100
    ret_240 = (r.get("ret_240d") or 0) * 100

    # Compute bull_signals for 組合經理
    bull_signals = sum([
        1 if (roe and roe > 0.15) else 0,
        1 if (ret_240 and ret_240 > 0.3) else 0,
        1 if (foreign_net > 0) else 0,
        1 if (rev_yoy is not None and rev_yoy > 15) else 0,
        1 if (sma13 and sma27 and cur > sma13 > sma27) else 0,
    ])

    # Build context dict for condition eval
    ctx = {
        "roe": roe, "pe": pe, "pb": pb, "mcap": mcap, "beta": beta,
        "cur": cur, "sma13": sma13, "sma27": sma27, "rsi14": rsi14,
        "foreign_net": foreign_net, "rev_yoy": rev_yoy,
        "ret_60": ret_60, "ret_120": ret_120, "ret_240": ret_240,
        "bull_signals": bull_signals,
    }

    triggered = []
    # Build a substitution dict with all known values
    peg_val = (pe / rev_yoy) if (rev_yoy and rev_yoy > 0 and pe) else None
    subs = {
        "roe": f"{roe*100:.0f}%" if roe else "—",
        "pe": f"{pe:.1f}" if pe else "—",
        "pb": f"{pb:.2f}" if pb else "—",
        "rsi": f"{rsi14:.0f}",
        "r60": f"{ret_60:.0f}%",
        "r120": f"{ret_120:.0f}%",
        "ret": f"{ret_240:.0f}%",
        "yoy": f"{rev_yoy:.0f}%" if rev_yoy is not None else "—",
        "beta": f"{beta:.2f}" if beta else "—",
        "n": bull_signals,
        "fval": f"{foreign_net/1000:,.0f}",
        "mcap_str": _fmt_num(mcap),
        "peg": f"{peg_val:.1f}" if peg_val else "—",
        "cur": f"{cur:.0f}",
        "sma13": f"{sma13:.0f}",
        "sma27": f"{sma27:.0f}",
    }
    for expert, views in EXPERT_VIEWS.items():
        for view_name, condition, fmt_str, template in views:
            try:
                if eval(condition, {}, ctx):
                    val_str = fmt_str.format(**subs)
                    explanation = template.format(**subs)
                    triggered.append({
                        "expert": expert,
                        "view": view_name,
                        "data": val_str,
                        "explain": explanation,
                    })
            except Exception:
                pass
    return triggered


def section_expert_views(data: Dict, db_latest: Dict) -> str:
    """18 大師 tags — 卡片式佈局：每個大師一張 card，內含多個 view chips。"""
    views = _trigger_expert_views(data, db_latest)
    if not views:
        return "<div class='expert-empty'>_18 大師中無觸發任何視角（資料不足或條件不符）_</div>"
    # Group by expert
    by_expert: Dict[str, List[Dict]] = {}
    for v in views:
        by_expert.setdefault(v["expert"], []).append(v)
    # 12 大師 + 6 分析師 emoji
    master_icons = {
        "巴菲特": "👴", "芒格": "🧓", "葛拉漢": "📚", "林奇": "🎯",
        "達摩達蘭": "🧮", "伯里": "🏛", "伍德": "🚀", "阿克曼": "🦁",
        "德魯肯米勒": "⚡", "費雪": "🔬", "帕布萊": "💎", "鈕亨沃拉": "🌏",
        "估值分析師": "💹", "情緒分析師": "💭", "基本面分析師": "📊", "技術分析師": "📈",
        "風險管理師": "🛡", "投資組合經理": "🎯",
    }
    html = "<div class='expert-grid'>"
    for expert, items in by_expert.items():
        icon = master_icons.get(expert, "💡")
        html += f"<div class='expert-card'>"
        html += f"<div class='expert-head'><span class='expert-icon'>{icon}</span><span class='expert-name'>{_esc(expert)}</span><span class='expert-count'>{len(items)} 視角</span></div>"
        html += "<div class='expert-views'>"
        for v in items:
            html += "<div class='view-chip'>"
            html += f"<div class='view-title'>{_esc(v['view'])} <span class='view-data'>{_esc(v['data'])}</span></div>"
            html += f"<div class='view-explain'>{_esc(v['explain'])}</div>"
            html += "</div>"
        html += "</div></div>"
    html += "</div>"
    html += "<div class='expert-meta'>共觸發 {} 個視角，分屬 {} 位大師 · 資料來源：hedge-fund-expert-team skill</div>".format(len(views), len(by_expert))
    return html


def section_observations(data: Dict, db_latest: Dict) -> str:
    """觀察重點 — 卡片式網格，每張卡 = 一個觀察維度，含白話說明。"""
    if not db_latest:
        return "<div class='obs-foot'>_無觀察資料_</div>"
    rsi14 = float(db_latest.get("rsi_14") or 0)
    foreign_net = float(db_latest.get("ForeignNet") or 0)
    val = data.get("valuation", {}) or {}
    pe = val.get("pe")
    roe = (data.get("yfinance") or {}).get("returnOnEquity")
    rev = data.get("monthly_revenue", [])
    last_yoy = rev[-1].get("yoy_pct") if rev and isinstance(rev[-1], dict) else None

    cards = []

    # 1) RSI
    if rsi14:
        if rsi14 > 70:
            cards.append({
                "cat": "動能", "icon": "🔥", "val": f"{rsi14:.0f}", "senti": "pos",
                "title": "RSI 過熱", "explain": "RSI 介於 0~100，目前 <code>>70</code> 屬「超買區」。過去 14 天漲勢可能過急，<b>留意短線回檔風險</b>。建議等量縮止穩再進場。",
            })
        elif rsi14 < 30:
            cards.append({
                "cat": "動能", "icon": "❄️", "val": f"{rsi14:.0f}", "senti": "neg",
                "title": "RSI 超賣", "explain": "RSI <code><30</code> 屬「超賣區」。過去 14 天跌勢可能過深，<b>可能醞釀反彈</b>，但需確認止穩訊號（例：紅 K 帶量突破）。",
            })
        else:
            cards.append({
                "cat": "動能", "icon": "⚖️", "val": f"{rsi14:.0f}", "senti": "neu",
                "title": "RSI 中性", "explain": "RSI 落在 30~70 區間，<b>動能持平</b>，沒有明顯超買或超賣訊號。<br><span style='color:var(--muted);font-size:0.78rem'>💡 RSI = Relative Strength Index，近 14 天漲跌力道指標。70+ 過熱、30- 超冷。</span>",
            })

    # 2) 外資
    if foreign_net:
        fk = foreign_net / 1000.0
        if fk > 0:
            cards.append({
                "cat": "法人", "icon": "💰", "val": f"+{fk:,.0f} 張", "senti": "pos",
                "title": "外資今日買超", "explain": "三大法人中最大主力偏多，通常對股價有正面推升。連續買超 <code>3 日以上</code> 訊號更強。",
            })
        else:
            cards.append({
                "cat": "法人", "icon": "💸", "val": f"{fk:,.0f} 張", "senti": "neg",
                "title": "外資今日賣超", "explain": "外資退場可能造成短期賣壓。若連續 <code>3 日以上</code> 賣超且跌破月線，宜減倉觀望。",
            })

    # 3) P/E
    if pe:
        if pe > 30:
            cards.append({
                "cat": "估值", "icon": "💎", "val": f"{pe:.1f}", "senti": "neg",
                "title": "本益比偏高", "explain": "P/E <code>>30</code> 表示市場對未來成長有很高期待。<b>估值偏貴</b>，需強勁成長支撐，否則有下修風險。",
            })
        elif pe < 12:
            cards.append({
                "cat": "估值", "icon": "💰", "val": f"{pe:.1f}", "senti": "pos",
                "title": "本益比偏低", "explain": "P/E <code><12</code> 通常被視為<b>價值浮現</b>，或市場看淡成長。建議檢視營收 / 獲利是否同步下滑。",
            })
        else:
            cards.append({
                "cat": "估值", "icon": "⚖️", "val": f"{pe:.1f}", "senti": "neu",
                "title": "本益比合理", "explain": "P/E 落在 12~30 區間，<b>估值中性</b>。對照同業平均可判斷相對位置。",
            })

    # 4) ROE
    if roe:
        r_pct = roe * 100
        if r_pct > 20:
            cards.append({
                "cat": "品質", "icon": "🏆", "val": f"{r_pct:.1f}%", "senti": "pos",
                "title": "ROE 優異", "explain": "股東權益報酬率 <code>>20%</code>，每 1 元股東資金能賺 0.2 元以上，<b>護城河深</b>、經營效率高。",
            })
        elif r_pct < 5:
            cards.append({
                "cat": "品質", "icon": "📉", "val": f"{r_pct:.1f}%", "senti": "neg",
                "title": "ROE 偏弱", "explain": "ROE <code><5%</code>，股東資金運用效率不佳，<b>競爭力不足</b>。需檢視是否低毛利或資產周轉慢。",
            })
        else:
            cards.append({
                "cat": "品質", "icon": "📊", "val": f"{r_pct:.1f}%", "senti": "neu",
                "title": "ROE 中等", "explain": "ROE 落在 5~20%，普通水準。優於 <code>10%</code> 算可接受，<code>>15%</code> 才算優質。",
            })

    # 5) 月營收 YoY
    if last_yoy is not None:
        if last_yoy > 20:
            cards.append({
                "cat": "營收", "icon": "🚀", "val": f"+{last_yoy:.1f}%", "senti": "pos",
                "title": "月營收高速成長", "explain": "YoY <code>>+20%</code>，比去年同期成長 20% 以上，<b>業務在加速擴張</b>。持續 3 個月以上趨勢更明確。",
            })
        elif last_yoy < -20:
            cards.append({
                "cat": "營收", "icon": "⚠️", "val": f"{last_yoy:.1f}%", "senti": "neg",
                "title": "月營收大幅衰退", "explain": "YoY <code><-20%</code>，較去年同期衰退 20% 以上，<b>業績動能轉弱</b>。需注意是否為單月事件或趨勢性下滑。",
            })
        else:
            cards.append({
                "cat": "營收", "icon": "📊", "val": f"{last_yoy:+.1f}%", "senti": "neu",
                "title": "月營收持平", "explain": "YoY 變動在 ±20% 區間，<b>與去年同期相當</b>。建議觀察連續 3 個月趨勢判斷方向。",
            })

    if not cards:
        return "<div class='obs-foot'>_無可觀察的指標_</div>"

    parts = ["<div class='obs-grid'>"]
    for c in cards:
        s = c["senti"]
        parts.append(
            f"<div class='obs-card s-{s}'>"
            f"<div class='obs-head'>"
            f"<span class='obs-icon'>{c['icon']}</span>"
            f"<span class='obs-cat'>{_esc(c['cat'])}</span>"
            f"</div>"
            f"<div class='obs-val s-{s}'>{_esc(c['val'])}</div>"
            f"<div class='obs-title'>{_esc(c['title'])}</div>"
            f"<div class='obs-explain'>{c['explain']}</div>"
            f"</div>"
        )
    parts.append("</div>")
    parts.append(
        "<div class='obs-foot'>"
        "💡 觀察重點 = 快速掃描 <b>動能</b> + <b>法人</b> + <b>估值</b> + <b>品質</b> + <b>營收</b> 5 個維度"
        "</div>"
    )
    return "".join(parts)


# ---- Main render ----

def render_ticker_full(ticker: str, data: Dict, output_dir: str = r"C:\Groove-Lab\analyze") -> str:
    """Render full HTML for one ticker. data = output of cross_source_runner.assemble()."""
    ticker = ticker.strip()
    db_latest = _fetch_db_technicals(ticker)
    history = _fetch_history(ticker, days=240)

    yf = data.get("yfinance", {}) or {}
    name = data.get("company_name") or yf.get("longName") or ticker
    industry = data.get("industry") or yf.get("industry") or "—"
    val = data.get("valuation", {}) or {}

    # Hero
    close = float(db_latest.get("Close") or 0) if db_latest else 0
    rows = db.ticker_history(ticker, days=2)
    prev = rows[-2] if len(rows) >= 2 else {}
    prev_close = float(prev.get("Close") or 0)
    change_pct = (close - prev_close) / prev_close * 100 if prev_close else 0
    pcls = "up" if change_pct > 0 else "down" if change_pct < 0 else ""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    market_label = "上市" if len(ticker) == 4 else "上櫃" if len(ticker) == 5 else "—"
    sources = data.get("_meta", {}).get("sources", [])

    # Master tags (hedge-fund: 巴菲特/芒格/葛拉漢/費雪/達摩達蘭/帕布萊 for all tickers)
    try:
        tags_html = master_tags_full(ticker, data, db_latest)
    except Exception as e:
        tags_html = f'<div class="tags"><span class="tag tag-yellow">tags 取得失敗: {e}</span></div>'

    # Summary cards
    summary = []
    if close:
        summary.append(f'<div class="card"><div class="k">收盤</div><div class="v">{close:,.2f}</div></div>')
    pe = val.get("pe")
    if pe:
        summary.append(f'<div class="card"><div class="k">P/E</div><div class="v">{pe:.1f}</div></div>')
    pb = val.get("pb")
    if pb:
        summary.append(f'<div class="card"><div class="k">P/B</div><div class="v">{pb:.2f}</div></div>')
    roe = yf.get("returnOnEquity")
    if roe is not None:
        summary.append(f'<div class="card"><div class="k">ROE</div><div class="v">{roe*100:.1f}%</div></div>')
    dy = val.get("dividend_yield")
    if dy is not None:
        # yfinance dividendYield may be in fraction (0.01) or percentage (1.0) — detect
        dy_pct = dy if dy > 0.5 else dy * 100
        summary.append(f'<div class="card"><div class="k">殖利率</div><div class="v">{dy_pct:.2f}%</div></div>')
    mcap = val.get("market_cap")
    if mcap:
        summary.append(f'<div class="card"><div class="k">市值</div><div class="v">{_fmt_num(mcap)}</div></div>')
    rsi14 = float(db_latest.get("rsi_14") or 0) if db_latest else 0
    if rsi14:
        summary.append(f'<div class="card"><div class="k">RSI(14)</div><div class="v">{rsi14:.1f}</div></div>')

    # Sections
    news_md = section_news(data) if data.get("news") else section_news_db(ticker)
    news_title = "📰 新聞" + (" (FinMind)" if data.get("news") else " (DB)")
    sections = {
        "info":     ("🏢 公司基本資料", section_company(data)),
        "price":    ("💰 即時價格", section_price(data, db_latest)),
        "tech":     ("📊 技術分析", section_technical(data, db_latest)),
        "val":      ("💎 估值 (雙源驗證)", section_valuation(data, history)),
        "fin":      ("📊 季報 (FinMind)", section_fundamentals(data)),
        "roe":      ("🧬 ROE", section_finlab_roe(data, history)),
        "rev":      ("📈 月營收 (FinMind)", section_monthly_revenue(data)),
        "div":      ("💵 配息歷史", section_dividends(data)),
        "inst":     ("🏛 法人 (近 10 日)", section_institutional(ticker, db_latest)),
        "margin":   ("💴 融資融券 (近 30 日)", section_margin(ticker, db_latest)),
        "news":     (news_title, news_md),
        "zen":      ("🧘 纏論 (Chanlun)", section_zen(data, history)),
        "experts":  ("🧠 18 大師解讀", section_expert_views(data, db_latest)),
        "minerva":  ("🧮 Minerva 量化評分", section_minerva(data, db_latest, history)),
        "thesis":   ("🎯 Build-Thesis 多空", section_build_thesis(data, db_latest)),
        "backtest": ("📊 Backtest 因子驗證", section_backtest(data, db_latest, history)),
        "trader":   ("💹 TraderHub 進出場", section_traderhub(data, db_latest)),
        "obs":      ("💡 觀察重點", section_observations(data, db_latest)),
    }

    # Deep-dive prompt
    try:
        cand = ms.Candidate(
            ticker=ticker, name=name, industry=industry or "",
            close=close, change_pct=change_pct,
            volume=int(db_latest.get("Volume") or 0) if db_latest else 0,
            three_net=int(db_latest.get("ThreeNet") or 0) if db_latest else 0,
            foreign_net=int(db_latest.get("ForeignNet") or 0) if db_latest else 0,
            margin_balance=int(db_latest.get("MarginBalance") or 0) if db_latest else 0,
            short_balance=int(db_latest.get("ShortBalance") or 0) if db_latest else 0,
            foreign_ratio=0,
            sma13=float(db_latest.get("sma_13") or 0) if db_latest else 0,
            sma27=float(db_latest.get("sma_27") or 0) if db_latest else 0,
            sma54=float(db_latest.get("sma_54") or 0) if db_latest else 0,
            rsi14=rsi14, atr14=float(db_latest.get("atr_14") or 0) if db_latest else 0,
            is_gap=0, excess_return_240d=0,
        )
        dd_prompt = ddp.render_prompt(cand)
    except Exception as e:
        dd_prompt = f"(deep-dive prompt 取得失敗: {e})"
    dd_html = f'<div class="dd-prompt"><button class="copy-btn" onclick="copyText(this)">📋 複製</button><pre>{_esc(dd_prompt)}</pre></div>'

    sec_html = []
    for key, (title, content) in sections.items():
        sec_html.append(f'<div class="section"><h2>{title}</h2>{beautify(content)}</div>')
    sec_html.append(f'<div class="section"><h2>🤖 Deep-dive (Perplexity Prompt)</h2>{dd_html}</div>')

    skillbar = "".join(f'<span class="sk" title="{_esc(d)}">{_esc(n)}</span>' for n, d in SKILL_LINKS)
    source_label = " · ".join(sources) if sources else "DB only"

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(ticker)} {_esc(name)} | tw-invest-suite</title>
<style>{CSS}</style>
</head>
<body>
<div class="topbar">
  <div class="brand">📊 個股分析 <small>{_esc(ticker)} · {_esc(name)} · {now_str[:10]}</small></div>
  <form class="search-form" action="https://groovelab.dev/analyze.html" method="get">
    <input name="ticker" placeholder="股號" maxlength="6" required>
    <button type="submit">分析 →</button>
  </form>
</div>
<div class="skillbar">{skillbar}</div>
<main>
  <div class="hero">
    <div>
      <div><span class="ticker">{_esc(ticker)}</span><span class="name">{_esc(name)}</span></div>
      <div class="industry">{_esc(industry)} · {market_label} · 資料源: {source_label}</div>
    </div>
    <div class="price {pcls}">{close:,.2f} <small style="font-size:0.5em;color:var(--muted)">元</small> <span style="font-size:0.5em">{change_pct:+.2f}%</span></div>
  </div>
  <div class="summary-bar">{"".join(summary)}</div>
  {tags_html}
  {"".join(sec_html)}
  <div class="disclaimer">
    <strong>資料來源：</strong>{source_label}。本報告為研究參考，<strong>非投資建議</strong>。
  </div>
</main>
<footer>tw-invest-suite · {now_str}</footer>
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

    # Save
    out_path = Path(output_dir) / f"{ticker}.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return str(out_path)


# ============================================================
#  Tabbed UI renderer (new design — charts + clickable tabs)
# ============================================================

TAB_CSS = """
.tabs-bar { display: flex; gap: 2px; background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 4px; margin: 16px 20px 0; overflow-x: auto; scrollbar-width: thin; position: sticky; top: 64px; z-index: 50; }
.tabs-bar::-webkit-scrollbar { height: 4px; }
.tabs-bar::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
.tab-btn { background: transparent; color: var(--muted); border: none; padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 0.85rem; font-weight: 500; white-space: nowrap; transition: all 0.15s; display: flex; align-items: center; gap: 4px; }
.tab-btn:hover { background: rgba(95,177,255,0.1); color: var(--ink); }
.tab-btn.active { background: linear-gradient(135deg, var(--acc), var(--cyan)); color: #000; font-weight: 600; }
.tab-btn .ic { font-size: 1rem; }
.tab-panel { display: none; padding: 20px; max-width: 1400px; margin: 0 auto; }
.tab-panel.active { display: block; }
.tab-panel h2 { color: var(--acc); font-size: 1.05rem; margin: 0 0 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.charts-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 14px; }
@media (max-width: 900px) { .charts-row { grid-template-columns: 1fr; } }
.chart-card { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }
.chart-card h3 { color: var(--muted); font-size: 0.78rem; margin: 0 0 8px; text-transform: uppercase; letter-spacing: 0.4px; font-weight: 600; }
.chart-card canvas { width: 100% !important; height: 240px !important; }
.action-bar { display: flex; gap: 8px; flex-wrap: wrap; margin: 20px; padding: 14px 16px; background: var(--panel); border: 1px solid var(--border); border-radius: 10px; }
.action-bar a { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; background: rgba(95,177,255,0.1); color: var(--acc); border: 1px solid var(--border); border-radius: 6px; text-decoration: none; font-size: 0.85rem; font-weight: 500; transition: all 0.15s; }
.action-bar a:hover { background: var(--acc); color: #000; border-color: var(--acc); }
.section-inner { background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 16px 20px; }
.expert-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; margin: 12px 0; }
.expert-card { background: linear-gradient(135deg, rgba(95,177,255,0.06), rgba(57,197,207,0.04)); border: 1px solid var(--border); border-left: 3px solid var(--acc); border-radius: 8px; padding: 12px 14px; transition: all 0.15s; }
.expert-card:hover { border-left-color: var(--cyan); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(95,177,255,0.1); }
.expert-head { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.expert-icon { font-size: 1.4rem; }
.expert-name { font-weight: 600; color: var(--ink); flex: 1; }
.expert-count { background: var(--border); color: var(--muted); padding: 2px 8px; border-radius: 10px; font-size: 0.7rem; }
.expert-views { display: flex; flex-direction: column; gap: 8px; }
.view-chip { background: rgba(0,0,0,0.2); border: 1px solid var(--border); border-radius: 6px; padding: 8px 10px; }
.view-title { font-weight: 600; color: var(--acc); font-size: 0.9rem; margin-bottom: 4px; }
.view-data { color: var(--amber); font-family: 'Consolas', 'Monaco', monospace; font-size: 0.85rem; font-weight: 500; }
.view-explain { color: var(--muted); font-size: 0.8rem; line-height: 1.5; }
.expert-meta { color: var(--muted); font-size: 0.78rem; text-align: right; margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border); }
.expert-empty { color: var(--muted); padding: 20px; text-align: center; background: rgba(0,0,0,0.2); border-radius: 8px; }
.news-list { display: flex; flex-direction: column; gap: 6px; }
.news-item { padding: 8px 12px; background: rgba(0,0,0,0.2); border-left: 3px solid var(--border); border-radius: 4px; transition: all 0.15s; }
.news-item:hover { background: rgba(95,177,255,0.08); border-left-color: var(--acc); }
.news-meta { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; font-size: 0.72rem; color: var(--muted); }
.news-icon { font-size: 0.9rem; }
.news-icon.news-pos { color: #ec7063; }
.news-icon.news-neg { color: #58d68d; }
.news-date { font-family: 'Consolas', 'Monaco', monospace; }
.news-source { background: var(--border); padding: 1px 6px; border-radius: 4px; font-size: 0.7rem; }
.news-title { color: var(--ink); font-size: 0.88rem; line-height: 1.5; text-decoration: none; }
a.news-title:hover { color: var(--acc); text-decoration: underline; }
.news-empty { color: var(--muted); padding: 20px; text-align: center; }

/* ===== 法人 (Institutional) - 視覺化表格 ===== */
.inst-summary { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 0 0 16px; }
.inst-sum-card { background: linear-gradient(135deg, rgba(95,177,255,0.08), rgba(57,197,207,0.04)); border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; }
.inst-sum-label { color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
.inst-sum-grid { display: grid; grid-template-columns: auto 1fr; gap: 2px 8px; font-size: 0.78rem; }
.inst-sum-key { color: var(--muted); }
.inst-sum-val { font-family: 'Consolas','Monaco',monospace; font-weight: 600; text-align: right; }
.inst-sum-val.pos { color: #ec7063; }
.inst-sum-val.neg { color: #58d68d; }
.inst-table-wrap { overflow-x: auto; border: 1px solid var(--border); border-radius: 8px; }
.inst-table { width: 100%; border-collapse: collapse; font-size: 0.84rem; font-family: 'Consolas','Monaco',monospace; }
.inst-table thead { background: var(--panel); }
.inst-table th { padding: 8px 6px; text-align: right; color: var(--muted); font-weight: 600; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.3px; border-bottom: 1px solid var(--border); white-space: nowrap; }
.inst-table th.date-col { text-align: left; }
.inst-table tbody tr { border-bottom: 1px solid var(--border); transition: background 0.1s; }
.inst-table tbody tr:hover { background: rgba(95,177,255,0.05); }
.inst-table tbody tr:last-child { border-bottom: none; }
.inst-table td { padding: 6px 6px; text-align: right; white-space: nowrap; }
.inst-table td.date-col { text-align: left; color: var(--ink); font-weight: 500; }
.inst-table td.zero { color: var(--muted); opacity: 0.55; }
.inst-cell { display: flex; align-items: center; gap: 4px; justify-content: flex-end; min-width: 60px; }
.inst-bar-wrap { flex: 1; height: 6px; background: rgba(255,255,255,0.04); border-radius: 3px; overflow: hidden; min-width: 24px; max-width: 50px; }
.inst-bar { height: 100%; border-radius: 3px; }
.inst-bar.pos { background: linear-gradient(90deg, #ec7063, #f1948a); }
.inst-bar.neg { background: linear-gradient(90deg, #58d68d, #82e0aa); }
.inst-num { font-weight: 600; min-width: 38px; text-align: right; }
.inst-num.pos { color: #ec7063; }
.inst-num.neg { color: #58d68d; }
.inst-num.total { color: var(--amber); font-weight: 700; }
.inst-table td.total-cell { background: rgba(255,184,77,0.06); }
.inst-table tr.hot-up { background: rgba(236,112,99,0.07); }
.inst-table tr.hot-dn { background: rgba(88,214,141,0.07); }
.inst-source { color: var(--muted); font-size: 0.72rem; margin-top: 10px; text-align: right; }

/* ===== 觀察重點 (Observations) - 卡片式網格 ===== */
.obs-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; margin-top: 8px; }
.obs-card { background: linear-gradient(135deg, rgba(95,177,255,0.06), rgba(57,197,207,0.03)); border: 1px solid var(--border); border-left: 3px solid var(--acc); border-radius: 8px; padding: 12px 14px; transition: all 0.15s; }
.obs-card:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(95,177,255,0.08); }
.obs-card.s-pos { border-left-color: #ec7063; }
.obs-card.s-neg { border-left-color: #58d68d; }
.obs-card.s-neu { border-left-color: var(--muted); }
.obs-head { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.obs-icon { font-size: 1.1rem; }
.obs-cat { color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.4px; font-weight: 600; }
.obs-val { font-size: 1.3rem; font-weight: 700; color: var(--ink); margin-bottom: 4px; font-family: 'Consolas','Monaco',monospace; }
.obs-val.s-pos { color: #ec7063; }
.obs-val.s-neg { color: #58d68d; }
.obs-title { color: var(--ink); font-weight: 600; font-size: 0.92rem; margin-bottom: 4px; }
.obs-explain { color: var(--muted); font-size: 0.82rem; line-height: 1.5; }
.obs-explain code { background: rgba(0,0,0,0.3); padding: 1px 4px; border-radius: 3px; color: var(--amber); font-size: 0.78rem; }
.obs-foot { color: var(--muted); font-size: 0.72rem; margin-top: 12px; padding-top: 8px; border-top: 1px solid var(--border); text-align: center; }
"""


def _build_chart_data(history: List[Dict]) -> str:
    """Build Chart.js data from history rows."""
    if not history:
        return "[]"
    dates = [str(r.get("Date", "")) for r in history]
    closes = [float(r.get("Close") or 0) for r in history]
    sma13 = [float(r.get("sma_13") or 0) for r in history]
    sma27 = [float(r.get("sma_27") or 0) for r in history]
    sma54 = [float(r.get("sma_54") or 0) for r in history]
    rsi14 = [float(r.get("rsi_14") or 0) for r in history]
    import json
    return json.dumps({
        "dates": dates, "close": closes,
        "sma13": sma13, "sma27": sma27, "sma54": sma54, "rsi14": rsi14,
    }, ensure_ascii=False)


def render_ticker_tabbed(ticker: str, data: Dict, output_dir: str = r"C:\Groove-Lab\analyze") -> str:
    """Tabbed UI version — clickable skill tabs + charts in 技術 tab."""
    ticker = ticker.strip()
    db_latest = _fetch_db_technicals(ticker)
    history = _fetch_history(ticker, days=120)

    yf = data.get("yfinance", {}) or {}
    name = data.get("company_name") or yf.get("longName") or ticker
    industry = data.get("industry") or yf.get("industry") or "—"
    val = data.get("valuation", {}) or {}

    close = float(db_latest.get("Close") or 0) if db_latest else 0
    rows = db.ticker_history(ticker, days=2)
    prev = rows[-2] if len(rows) >= 2 else {}
    prev_close = float(prev.get("Close") or 0)
    change_pct = (close - prev_close) / prev_close * 100 if prev_close else 0
    pcls = "up" if change_pct > 0 else "down" if change_pct < 0 else ""
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    market_label = "上市" if len(ticker) == 4 else "上櫃" if len(ticker) == 5 else "—"
    sources = data.get("_meta", {}).get("sources", [])

    # Master tags
    try:
        tags_html = master_tags_full(ticker, data, db_latest)
    except Exception as e:
        tags_html = f'<div class="tags"><span class="tag tag-yellow">tags 取得失敗: {e}</span></div>'

    # Summary cards
    summary = []
    if close:
        summary.append(f'<div class="card"><div class="k">收盤</div><div class="v">{close:,.2f}</div></div>')
    pe = val.get("pe")
    if pe:
        summary.append(f'<div class="card"><div class="k">P/E</div><div class="v">{pe:.1f}</div></div>')
    pb = val.get("pb")
    if pb:
        summary.append(f'<div class="card"><div class="k">P/B</div><div class="v">{pb:.2f}</div></div>')
    roe = yf.get("returnOnEquity")
    if roe is not None:
        summary.append(f'<div class="card"><div class="k">ROE</div><div class="v">{roe*100:.1f}%</div></div>')
    dy = val.get("dividend_yield")
    if dy is not None:
        dy_pct = dy if dy > 0.5 else dy * 100
        summary.append(f'<div class="card"><div class="k">殖利率</div><div class="v">{dy_pct:.2f}%</div></div>')
    mcap = val.get("market_cap")
    if mcap:
        summary.append(f'<div class="card"><div class="k">市值</div><div class="v">{_fmt_num(mcap)}</div></div>')
    rsi14 = float(db_latest.get("rsi_14") or 0) if db_latest else 0
    if rsi14:
        summary.append(f'<div class="card"><div class="k">RSI(14)</div><div class="v">{rsi14:.1f}</div></div>')

    # Build all sections
    news_md = section_news(data) if data.get("news") else section_news_db(ticker)
    news_title = "📰 新聞" + (" (FinMind)" if data.get("news") else " (DB)")
    section_data = {
        "info":     ("🏢 公司基本資料", section_company(data)),
        "price":    ("💰 即時價格", section_price(data, db_latest)),
        "tech":     ("📊 技術分析", section_technical(data, db_latest)),
        "val":      ("💎 估值 (雙源驗證)", section_valuation(data, history)),
        "fin":      ("📊 季報 (FinMind)", section_fundamentals(data)),
        "roe":      ("🧬 ROE", section_finlab_roe(data, history)),
        "rev":      ("📈 月營收 (FinMind)", section_monthly_revenue(data)),
        "div":      ("💵 配息歷史", section_dividends(data)),
        "inst":     ("🏛 法人 (近 10 日)", section_institutional(ticker, db_latest)),
        "margin":   ("💴 融資融券 (近 30 日)", section_margin(ticker, db_latest)),
        "news":     (news_title, news_md),
        "zen":      ("🧘 纏論 (Chanlun)", section_zen(data, history)),
        "minerva":  ("🧮 Minerva 量化評分", section_minerva(data, db_latest, history)),
        "thesis":   ("🎯 Build-Thesis 多空", section_build_thesis(data, db_latest)),
        "backtest": ("📊 Backtest 因子驗證", section_backtest(data, db_latest, history)),
        "trader":   ("💹 TraderHub 進出場", section_traderhub(data, db_latest)),
        "experts":  ("🧠 18 大師解讀", section_expert_views(data, db_latest)),
        "obs":      ("💡 觀察重點", section_observations(data, db_latest)),
    }

    # Tab order (primary tabs shown in bar, default = 技術)
    PRIMARY_TABS = ["zen", "tech", "val", "inst", "margin", "fin", "roe", "rev", "div", "news", "obs"]
    SECONDARY_TABS = ["minerva", "thesis", "backtest", "trader", "experts", "info", "price"]

    # Build tab bar
    tab_buttons = []
    for key in PRIMARY_TABS:
        title, _ = section_data[key]
        ic = title.split()[0] if title else ""
        nm = title.split(" ", 1)[1] if " " in title else title
        tab_buttons.append(
            f'<button class="tab-btn" data-tab="{key}"><span class="ic">{_esc(ic)}</span><span>{_esc(nm)}</span></button>'
        )
    tab_buttons.append('<span style="width:1px;background:var(--border);margin:4px 4px"></span>')
    for key in SECONDARY_TABS:
        title, _ = section_data[key]
        ic = title.split()[0] if title else ""
        nm = title.split(" ", 1)[1] if " " in title else title
        tab_buttons.append(
            f'<button class="tab-btn" data-tab="{key}"><span class="ic">{_esc(ic)}</span><span>{_esc(nm)}</span></button>'
        )
    tabs_bar_html = "".join(tab_buttons)

    # Build tab panels — 技術 / 法人 get charts
    chart_data_json = _build_chart_data(history)
    # Extract institutional chart data from section content (we added <!--CHART_DATA_INST ... -->)
    inst_chart_json = "{}"
    inst_content = section_data.get("inst", ("", ""))[1]
    if "<!--CHART_DATA_INST" in inst_content:
        import re
        m = re.search(r'<!--CHART_DATA_INST\s+(.*?)\s+-->', inst_content, re.S)
        if m:
            inst_chart_json = m.group(1)
    panels = []
    for key, (title, content) in section_data.items():
        if key == "tech":
            inner = f"""
            <div class="charts-row">
              <div class="chart-card"><h3>📈 收盤價 + 均線 (近 60 日)</h3><canvas id="c-main"></canvas></div>
              <div class="chart-card"><h3>📊 RSI(14) — 動能指標 (超買 >70 / 超賣 <30)</h3><canvas id="c-rsi"></canvas></div>
            </div>
            <div class="section-inner">{beautify(content)}</div>
            """
        elif key == "inst":
            # Strip the CHART_DATA_INST marker from displayed content
            display_content = re.sub(r'<!--CHART_DATA_INST\s+.*?\s+-->', '', content, flags=re.S)
            inner = f"""
            <div class="chart-card" style="margin-bottom:14px">
              <h3>🏛 法人買賣超 (近 20 日，紅=買超 / 綠=賣超)</h3>
              <canvas id="c-inst" style="width:100%!important;height:280px!important"></canvas>
            </div>
            <div class="section-inner">{beautify(display_content)}</div>
            <script>const INST_DATA = {inst_chart_json};</script>
            """
        else:
            inner = f'<div class="section-inner">{beautify(content)}</div>'
        panels.append(f'<div class="tab-panel" id="tab-{key}" data-title="{_esc(title)}">{inner}</div>')
    panels_html = "".join(panels)

    # Bottom action bar (link to other tools)
    action_bar = f"""
    <div class="action-bar">
      <a href="https://groovelab.dev/analyze.html?ticker={_esc(ticker)}" target="_blank">🔍 重查</a>
      <a href="https://groovelab.dev/watchlist.html" target="_blank">📊 Market Report</a>
      <a href="https://groovelab.dev/analyze/patterns.html" target="_blank">🎛 Ticker Dashboard</a>
      <a href="https://groovelab.dev/analyze.html" target="_blank">🏛 Wall Street</a>
      <a href="https://groovelab.dev/analyze.html" target="_blank">📚 Research</a>
    </div>
    """

    skillbar = "".join(f'<span class="sk" title="{_esc(d)}">{_esc(n)}</span>' for n, d in SKILL_LINKS)
    source_label = " · ".join(sources) if sources else "DB only"

    # Deep-dive prompt
    try:
        rsi14_v = float(db_latest.get("rsi_14") or 0) if db_latest else 0
        cand = ms.Candidate(
            ticker=ticker, name=name, industry=industry or "",
            close=close, change_pct=change_pct,
            volume=int(db_latest.get("Volume") or 0) if db_latest else 0,
            three_net=int(db_latest.get("ThreeNet") or 0) if db_latest else 0,
            foreign_net=int(db_latest.get("ForeignNet") or 0) if db_latest else 0,
            margin_balance=int(db_latest.get("MarginBalance") or 0) if db_latest else 0,
            short_balance=int(db_latest.get("ShortBalance") or 0) if db_latest else 0,
            foreign_ratio=0,
            sma13=float(db_latest.get("sma_13") or 0) if db_latest else 0,
            sma27=float(db_latest.get("sma_27") or 0) if db_latest else 0,
            sma54=float(db_latest.get("sma_54") or 0) if db_latest else 0,
            rsi14=rsi14_v, atr14=float(db_latest.get("atr_14") or 0) if db_latest else 0,
            is_gap=0, excess_return_240d=0,
        )
        dd_prompt = ddp.render_prompt(cand)
    except Exception as e:
        dd_prompt = f"(deep-dive prompt 取得失敗: {e})"
    dd_html = f'<div class="dd-prompt"><button class="copy-btn" onclick="copyText(this)">📋 複製</button><pre>{_esc(dd_prompt)}</pre></div>'

    html = f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_esc(ticker)} {_esc(name)} | tw-invest-suite</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>{CSS}{TAB_CSS}</style>
</head>
<body>
<div class="topbar">
  <div class="brand">📊 個股分析 <small>{_esc(ticker)} · {_esc(name)} · {now_str[:10]}</small></div>
  <form class="search-form" action="https://groovelab.dev/analyze.html" method="get">
    <input name="ticker" placeholder="股號" maxlength="6" required>
    <button type="submit">分析 →</button>
  </form>
</div>
<div class="skillbar">{skillbar}</div>
<main style="max-width:none;padding:0">
  <div class="hero">
    <div>
      <div><span class="ticker">{_esc(ticker)}</span><span class="name">{_esc(name)}</span></div>
      <div class="industry">{_esc(industry)} · {market_label} · 資料源: {source_label}</div>
    </div>
    <div class="price {pcls}">{close:,.2f} <small style="font-size:0.5em;color:var(--muted)">元</small> <span style="font-size:0.5em">{change_pct:+.2f}%</span></div>
  </div>
  <div class="summary-bar">{"".join(summary)}</div>
  {tags_html}
</main>
<div class="tabs-bar" id="tabs-bar">
  {tabs_bar_html}
</div>
{panels_html}
{action_bar}
<div class="section" style="margin:20px"><h2>🤖 Deep-dive (Perplexity Prompt)</h2>{dd_html}</div>
<div class="disclaimer" style="margin:20px">
  <strong>資料來源：</strong>{source_label}。本報告為研究參考，<strong>非投資建議</strong>。
</div>
<footer>tw-invest-suite · {now_str}</footer>
<script>
const CHART_DATA = {chart_data_json};
function showTab(key) {{
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  const panel = document.getElementById('tab-' + key);
  const btn = document.querySelector('.tab-btn[data-tab="' + key + '"]');
  if (panel) panel.classList.add('active');
  if (btn) btn.classList.add('active');
  if (history.replaceState) history.replaceState(null, '', '#' + key);
  if (key === 'tech') renderCharts();
  if (key === 'inst') renderInstChart();
  const bar = document.getElementById('tabs-bar');
  if (btn && bar) btn.scrollIntoView({{behavior: 'smooth', inline: 'center', block: 'nearest'}});
}}
document.querySelectorAll('.tab-btn').forEach(b => {{
  b.addEventListener('click', () => showTab(b.dataset.tab));
}});
let chartsInited = false;
function renderCharts() {{
  if (chartsInited) return;
  if (!CHART_DATA.dates || CHART_DATA.dates.length === 0) return;
  const d = CHART_DATA;
  const last60 = d.dates.slice(-60);
  const close60 = d.close.slice(-60);
  const sma13_60 = d.sma13.slice(-60);
  const sma27_60 = d.sma27.slice(-60);
  const sma54_60 = d.sma54.slice(-60);
  const rsi60 = d.rsi14.slice(-60);
  const ctx1 = document.getElementById('c-main');
  if (ctx1) new Chart(ctx1, {{
    type: 'line',
    data: {{
      labels: last60,
      datasets: [
        {{ label: '收盤', data: close60, borderColor: '#5fb1ff', backgroundColor: 'rgba(95,177,255,0.1)', borderWidth: 2, pointRadius: 0, tension: 0.2 }},
        {{ label: 'MA13', data: sma13_60, borderColor: '#58d68d', borderWidth: 1.2, pointRadius: 0, tension: 0.2 }},
        {{ label: 'MA27', data: sma27_60, borderColor: '#f5b041', borderWidth: 1.2, pointRadius: 0, tension: 0.2 }},
        {{ label: 'MA54', data: sma54_60, borderColor: '#bc8cff', borderWidth: 1.2, pointRadius: 0, tension: 0.2 }},
      ]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ display: true, position: 'top', labels: {{ color: '#8aa0c0', font: {{ size: 10 }} }} }} }},
      scales: {{
        x: {{ ticks: {{ color: '#8aa0c0', maxTicksLimit: 8, font: {{ size: 9 }} }}, grid: {{ color: 'rgba(255,255,255,0.04)' }} }},
        y: {{ ticks: {{ color: '#8aa0c0', font: {{ size: 9 }} }}, grid: {{ color: 'rgba(255,255,255,0.04)' }} }}
      }}
    }}
  }});
  const ctx2 = document.getElementById('c-rsi');
  if (ctx2) new Chart(ctx2, {{
    type: 'line',
    data: {{ labels: last60, datasets: [{{ label: 'RSI(14)', data: rsi60, borderColor: '#39c5cf', borderWidth: 1.5, pointRadius: 0, tension: 0.2, fill: false }}] }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        x: {{ ticks: {{ color: '#8aa0c0', maxTicksLimit: 8, font: {{ size: 9 }} }}, grid: {{ color: 'rgba(255,255,255,0.04)' }} }},
        y: {{ min: 0, max: 100, ticks: {{ color: '#8aa0c0', font: {{ size: 9 }} }}, grid: {{ color: 'rgba(255,255,255,0.04)' }} }}
      }}
    }}
  }});
  chartsInited = true;
}}
// Institutional chart (法人) — Taiwan convention: 紅=買超 (+), 綠=賣超 (-)
let instChartInited = false;
function renderInstChart() {{
  if (instChartInited) return;
  if (typeof INST_DATA === 'undefined' || !INST_DATA.dates || INST_DATA.dates.length === 0) return;
  const ctx = document.getElementById('c-inst');
  if (!ctx) return;
  const d = INST_DATA;
  new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels: d.dates,
      datasets: [
        {{ label: '外資', data: d.foreign, backgroundColor: d.foreign.map(v => v >= 0 ? 'rgba(236,112,99,0.85)' : 'rgba(88,214,141,0.85)'), borderColor: d.foreign.map(v => v >= 0 ? '#ec7063' : '#58d68d'), borderWidth: 1 }},
        {{ label: '投信', data: d.trust, backgroundColor: d.trust.map(v => v >= 0 ? 'rgba(245,176,65,0.85)' : 'rgba(95,177,255,0.85)'), borderColor: d.trust.map(v => v >= 0 ? '#f5b041' : '#5fb1ff'), borderWidth: 1 }},
        {{ label: '自營', data: d.dealer, backgroundColor: d.dealer.map(v => v >= 0 ? 'rgba(188,140,255,0.85)' : 'rgba(57,197,207,0.85)'), borderColor: d.dealer.map(v => v >= 0 ? '#bc8cff' : '#39c5cf'), borderWidth: 1 }},
        {{ label: '合計', data: d.total, type: 'line', borderColor: '#5fb1ff', borderWidth: 2, pointRadius: 2, fill: false, tension: 0.2 }}
      ]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ display: true, position: 'top', labels: {{ color: '#8aa0c0', font: {{ size: 10 }} }} }} }},
      scales: {{
        x: {{ stacked: false, ticks: {{ color: '#8aa0c0', maxTicksLimit: 10, font: {{ size: 9 }} }}, grid: {{ color: 'rgba(255,255,255,0.04)' }} }},
        y: {{ ticks: {{ color: '#8aa0c0', font: {{ size: 9 }} }}, grid: {{ color: 'rgba(255,255,255,0.04)' }} }}
      }}
    }}
  }});
  instChartInited = true;
}}
// Init default tab from hash or first primary (tech)
const initKey = (location.hash || '#tech').replace('#', '');
showTab(initKey);
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

    out_path = Path(output_dir) / f"{ticker}.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return str(out_path)


if __name__ == "__main__":
    import sys
    import cross_source_runner as csr
    ticker = sys.argv[1] if len(sys.argv) > 1 else "2330"
    mode = sys.argv[2] if len(sys.argv) > 2 else "tabbed"
    print(f"=== Render {ticker} (mode={mode}) ===")
    data = csr.assemble(ticker, news_tier="watchlist")
    if mode == "tabbed":
        path = render_ticker_tabbed(ticker, data)
    else:
        path = render_ticker_full(ticker, data)
    size = Path(path).stat().st_size
    print(f"  → {path} ({size:,} bytes)")
