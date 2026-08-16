"""
Single-stock deep-dive analyzer (tw-invest-suite, mode 1).

CLI:
    python analyze_stock.py <stock_id> [--out PATH] [--no-save]

Reads FinMind via finmind_client, produces a Markdown report.
"""
import argparse
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import finmind_client as fm  # noqa: E402
import finlab_client as fl  # noqa: E402
import twse_client as tw  # noqa: E402
import tpex_client as tpx  # noqa: E402


# ----- formatting helpers -----

def num(v, decimals: int = 2, default: str = "—") -> str:
    """Format number with thousands separator. None/NaN/'' -> default."""
    if v is None or v == "" or v == "NaN":
        return default
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if decimals == 0:
        return f"{f:,.0f}"
    return f"{f:,.{decimals}f}"


def pct(v, decimals: int = 2, default: str = "—") -> str:
    s = num(v, decimals, default)
    return s + "%" if s != default else s


def signed(v, decimals: int = 2) -> str:
    s = num(v, decimals, "—")
    if s == "—":
        return s
    return f"+{s}" if float(v) > 0 else s


def date_or(v, default: str = "—") -> str:
    return v if v else default


# ----- analytics helpers -----

def _roe_from_finmind(stock_id: str) -> List[Dict]:
    """Compute quarterly ROE from FinMind TaiwanStockFinancialStatements.

    ROE = NetIncome / Equity (per quarter, annualized).
    Returns list of {date, value} dicts (same shape as FinLab roe_for_dict).
    """
    try:
        rows = fm.stock_financial(stock_id, start_date="2018-01-01")
    except Exception:
        return []
    if not rows:
        return []
    # Group by quarter (date is the quarter end)
    by_q: Dict[str, Dict[str, float]] = {}
    name_map = {
        "NetIncome": ["本期淨利（淨損）", "稅後淨利（淨損）", "淨利（淨損）",
                       "IncomeFromContinuingOperations", "TotalConsolidatedProfitForThePeriod",
                       "ProfitLoss"],
        "Equity": ["權益總額", "權益總計", "Equity",
                    "EquityAttributableToOwnersOfParent", "TotalEquity"],
    }
    for r in rows:
        if not isinstance(r, dict):
            continue
        q = str(r.get("date", "")).strip()
        name = r.get("origin_name", "")
        try:
            val = float(r.get("value") or 0)
        except (TypeError, ValueError):
            continue
        if not q or not name:
            continue
        for canonical, aliases in name_map.items():
            if any(a == name or a in name for a in aliases):
                by_q.setdefault(q, {})[canonical] = val
                break
    out: List[Dict] = []
    for q in sorted(by_q):
        d = by_q[q]
        ni = d.get("NetIncome", 0)
        eq = d.get("Equity", 0)
        if eq and eq > 0:
            roe = ni / eq * 100  # quarterly ROE in %
            out.append({"date": q, "value": round(roe, 2)})
    return out


def _monthly_revenue_from_finmind(stock_id: str, months: int = 12) -> List[Dict]:
    """Monthly revenue from FinMind TaiwanStockMonthRevenue (current, with YoY).

    Returns list of {date, value, yoy} dicts.
    """
    try:
        rows = fm.query("TaiwanStockMonthRevenue", stock_id=stock_id,
                        start_date=(datetime.now() - timedelta(days=365*2)).strftime("%Y-%m-%d"))
    except Exception:
        return []
    if not rows:
        return []
    # Compute YoY
    by_key: Dict[str, float] = {}
    for r in rows:
        try:
            y = int(r.get("revenue_year", 0))
            m = int(r.get("revenue_month", 0))
            v = float(r.get("revenue", 0))
            by_key[f"{y}-{m:02d}"] = v
        except (KeyError, ValueError, TypeError):
            continue
    items: List[Dict] = []
    sorted_keys = sorted(by_key.keys(), reverse=True)[:months]
    for k in sorted_keys:
        v = by_key[k]
        y_str, m_str = k.split("-")
        prior_key = f"{int(y_str)-1}-{m_str}"
        yoy = None
        if prior_key in by_key and by_key[prior_key] > 0:
            yoy = round((v / by_key[prior_key] - 1) * 100, 2)
        # Use the 1st of the month as date for consistency
        items.append({
            "date": f"{k}-01",
            "value": v,
            "yoy": yoy,
        })
    return list(reversed(items))


def moving_average(closes: List[float], window: int) -> Optional[float]:
    if len(closes) < window:
        return None
    return sum(closes[-window:]) / window


def compute_rsi(closes: List[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(-period, 0):
        diff = closes[i] - closes[i - 1]
        if diff >= 0:
            gains.append(diff)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(-diff)
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def interpret_ma(ma5, ma20, ma60) -> str:
    if not all([ma5, ma20, ma60]):
        return "資料不足"
    if ma5 > ma20 > ma60:
        return "多頭排列，趨勢偏多"
    if ma5 < ma20 < ma60:
        return "空頭排列，趨勢偏空"
    if ma5 > ma20 and ma20 < ma60:
        return "短多長空，留意反轉"
    if ma5 < ma20 and ma20 > ma60:
        return "短空長多，留意落底"
    return "均線糾結，盤整觀望"


# ----- data fetchers -----

def fetch_all(stock_id: str) -> Dict:
    end = datetime.now()
    start_1y = (end - timedelta(days=365)).strftime("%Y-%m-%d")
    end_s = end.strftime("%Y-%m-%d")
    start_30 = (end - timedelta(days=30)).strftime("%Y-%m-%d")
    start_90 = (end - timedelta(days=90)).strftime("%Y-%m-%d")

    out: Dict = {"stock_id": stock_id, "fetch_errors": [], "market": None}

    # First, peek at the company info to detect market (上市/上櫃)
    market = None
    try:
        info_rows = fm.stock_info(stock_id)
        if info_rows:
            for r in info_rows:
                if str(r.get("stock_id", "")).strip() == stock_id:
                    market = r.get("type", "")
                    break
            if not market and info_rows:
                market = info_rows[0].get("type", "")
    except Exception as e:  # noqa: BLE001
        out["fetch_errors"].append(f"info: {e}")
        info_rows = []
    out["info"] = info_rows
    out["market"] = market

    # Price source depends on market:
    #   twse  → TWSE (12 months current, primary)
    #   tpex  → TPEx (1-day snapshot only) + FinLab (history to 2018)
    #   other → try TWSE first, fall back to FinLab
    def fetch_price():
        if market == "twse":
            try:
                rows = tw.stock_price_history(stock_id, months=12)
                if rows:
                    return rows
            except Exception as e:  # noqa: BLE001
                out["fetch_errors"].append(f"twse price: {e}")
            try:
                return fm.stock_price(stock_id, start_1y, end_s)
            except Exception as e:  # noqa: BLE001
                out["fetch_errors"].append(f"finmind price: {e}")
                return []
        elif market == "tpex":
            # OTC: TPEx current-day snapshot only. Don't merge with FinLab's
            # 2018 historical data — mixing dates produces meaningless MA/RSI.
            try:
                return tpx.stock_price_history(stock_id, days=5)
            except Exception as e:  # noqa: BLE001
                out["fetch_errors"].append(f"tpex price: {e}")
                return []
        else:
            # Unknown market — try TWSE then FinMind
            try:
                rows = tw.stock_price_history(stock_id, months=12)
                if rows:
                    return rows
            except Exception as e:  # noqa: BLE001
                out["fetch_errors"].append(f"twse price: {e}")
            try:
                return fm.stock_price(stock_id, start_1y, end_s)
            except Exception as e:  # noqa: BLE001
                out["fetch_errors"].append(f"finmind price: {e}")
                return []

    fetches = [
        ("price", fetch_price),
        ("per", lambda: fm.stock_per(stock_id, start_1y, end_s)),
        ("dividend", lambda: fm.stock_dividend(stock_id, start_date="2018-01-01")),
        ("institutional", lambda: fm.stock_institutional(stock_id, start_30, end_s)),
        # Chip data (free tier)
        ("margin", lambda: fm.stock_margin(stock_id, start_30, end_s)),
        ("securities_lending", lambda: fm.stock_securities_lending(stock_id, start_30, end_s)),
        # Sponsor-tier chip data
        ("margin_maintenance", lambda: fm.stock_margin_maintenance(stock_id, start_30, end_s)),
        ("government_bank", lambda: fm.stock_government_bank_buysell(stock_id, start_30, end_s)),
        # News dataset is restricted — must NOT pass end_date
        ("news", lambda: fm.stock_news(stock_id, start_30, "")),
        ("shareholding", lambda: fm.stock_shareholding(stock_id, start_90, end_s)),
        ("financial", lambda: fm.stock_financial(stock_id, start_date="2023-01-01")),
        ("balance_sheet", lambda: fm.stock_balance_sheet(stock_id, start_date="2023-01-01")),
        # ROE: compute from FinMind TaiwanStockFinancialStatements (current, not 2018)
        ("finlab_roe", lambda: _roe_from_finmind(stock_id)),
        # Monthly revenue: use FinMind (current), not FinLab (2018)
        ("finlab_revenue", lambda: _monthly_revenue_from_finmind(stock_id, months=12)),
    ]

    for key, fn in fetches:
        try:
            out[key] = fn()
        except Exception as e:  # noqa: BLE001
            out[key] = []
            out["fetch_errors"].append(f"{key}: {e}")
    return out


# ----- section builders -----

def section_info(d: Dict) -> str:
    rows = d.get("info") or []
    if not rows:
        return "_查無公司資料_"
    r = rows[0]
    return (
        "| 項目 | 內容 |\n"
        "|---|---|\n"
        f"| 股票代號 | {d['stock_id']} |\n"
        f"| 公司名稱 | {r.get('stock_name', '—')} |\n"
        f"| 產業別 | {r.get('industry_category', '—')} |\n"
        f"| 市場別 | {'上市' if r.get('type') == 'twse' else '上櫃' if r.get('type') == 'tpex' else r.get('type', '—')} |\n"
        f"| 公司簡稱 | {r.get('stock_id', '—')} |\n"
    )


def section_price(d: Dict) -> str:
    price = d.get("price") or []
    if not price:
        return "_查無股價資料_"
    latest = price[-1]
    prev = price[-2] if len(price) >= 2 else {}
    cur = float(latest.get("close") or 0)
    prev_close = float(prev.get("close") or 0)
    has_prev = bool(prev_close)
    change = cur - prev_close
    change_pct = (change / prev_close * 100) if has_prev else 0
    closes = [float(p.get("close") or 0) for p in price if p.get("close")]
    high_52w = max(closes) if closes else 0
    low_52w = min(closes) if closes else 0
    # Trading_Volume in FinMind is shares, not 張
    vol_shares = float(latest.get("Trading_Volume") or 0)
    vol_zhang = vol_shares / 1000.0

    change_str = f"{signed(change)} ({signed(change_pct)}%)" if has_prev else "— (僅 1 日資料)"

    return (
        "| 項目 | 數值 |\n"
        "|---|---|\n"
        f"| 收盤價 | {num(cur)} 元 |\n"
        f"| 漲跌 | {change_str} |\n"
        f"| 開盤 | {num(latest.get('open'))} |\n"
        f"| 最高 | {num(latest.get('max'))} |\n"
        f"| 最低 | {num(latest.get('min'))} |\n"
        f"| 成交量 | {num(vol_zhang, 0)} 張 |\n"
        f"| 成交額 | {num(latest.get('Trading_money'), 0)} 元 |\n"
        f"| 52週高 | {num(high_52w) if has_prev else '— (僅 1 日資料)'} |\n"
        f"| 52週低 | {num(low_52w) if has_prev else '— (僅 1 日資料)'} |\n"
        f"| 資料日期 | {date_or(latest.get('date'))} |\n"
    )


def section_technical(d: Dict) -> str:
    price = d.get("price") or []
    closes = [float(p.get("close") or 0) for p in price if p.get("close")]
    if not closes:
        return "_查無技術面資料_"

    ma5 = moving_average(closes, 5)
    ma20 = moving_average(closes, 20)
    ma60 = moving_average(closes, 60)
    rsi = compute_rsi(closes, 14)
    cur = closes[-1]

    return (
        "| 指標 | 數值 |\n"
        "|---|---|\n"
        f"| 收盤價 | {num(cur)} |\n"
        f"| MA5 | {num(ma5)} |\n"
        f"| MA20 | {num(ma20)} |\n"
        f"| MA60 | {num(ma60)} |\n"
        f"| RSI(14) | {num(rsi)} |\n"
        f"\n趨勢判讀：**{interpret_ma(ma5, ma20, ma60)}**\n"
    )


def section_valuation(d: Dict) -> str:
    per = d.get("per") or []
    price = d.get("price") or []
    dividend = d.get("dividend") or []

    latest_per = per[-1] if per else {}
    cur = float(price[-1].get("close") or 0) if price else 0
    price_date = date_or(price[-1].get("date")) if price else "—"

    # Latest yield = latest year's cash dividend / current price
    cash_div = 0
    if dividend:
        latest_year = max((x.get("year") for x in dividend if x.get("year")), default=None)
        if latest_year:
            for x in dividend:
                if x.get("year") == latest_year:
                    try:
                        cash_div += float(x.get("CashEarningsDistribution") or 0)
                    except (TypeError, ValueError):
                        pass
    yield_pct = (cash_div / cur * 100) if cur and cash_div else 0

    # Note: PER/PB comes from FinMind which may be a snapshot. Date shown is the
    # latest price date (TWSE) so the user knows which price the P/E applies to.
    return (
        "| 指標 | 數值 |\n"
        "|---|---|\n"
        f"| 本益比 (P/E) | {num(latest_per.get('PER'))} |\n"
        f"| 股價淨值比 (P/B) | {num(latest_per.get('PBR'))} |\n"
        f"| 殖利率 | {pct(yield_pct)} |\n"
        f"| 參考年度股利 | {num(cash_div, 4)} 元/股 |\n"
        f"| 股價參考日 | {price_date} |\n"
    )


def section_dividend(d: Dict) -> str:
    rows = d.get("dividend") or []
    if not rows:
        return "_查無配息資料_"
    rows_sorted = sorted(
        rows, key=lambda x: (x.get("year", 0), x.get("CashExDividendTradingDate", "")), reverse=True
    )
    lines = ["| 年度 | 現金股利 | 股票股利 | 合計 | 除息日 |", "|---|---|---|---|---|"]
    for r in rows_sorted[:8]:
        # FinMind uses CamelCase: CashEarningsDistribution, StockEarningsDistribution
        try:
            cash = float(r.get("CashEarningsDistribution") or 0)
        except (TypeError, ValueError):
            cash = 0
        try:
            stock = float(r.get("StockEarningsDistribution") or 0)
        except (TypeError, ValueError):
            stock = 0
        total = cash + stock
        ex_date = r.get("CashExDividendTradingDate") or r.get("StockExDividendTradingDate") or "—"
        lines.append(
            f"| {r.get('year', '—')} | {num(cash, 4)} | {num(stock, 4)} | "
            f"{num(total, 4)} | {ex_date} |"
        )
    return "\n".join(lines)


def section_institutional(d: Dict) -> str:
    rows = d.get("institutional") or []
    if not rows:
        return "_查無三大法人資料_"

    # Group by date, sum buy-sell across security types
    # FinMind buy/sell is in shares, convert to 張
    by_date: Dict[str, Dict[str, float]] = {}
    for r in rows:
        date = r.get("date", "")
        if not date:
            continue
        name = r.get("name", "")
        try:
            buy = float(r.get("buy") or 0) / 1000.0
            sell = float(r.get("sell") or 0) / 1000.0
        except (TypeError, ValueError):
            continue
        net = buy - sell
        by_date.setdefault(date, {})[name] = by_date.setdefault(date, {}).get(name, 0) + net

    dates_sorted = sorted(by_date.keys(), reverse=True)
    lines = ["| 日期 | 外資 | 投信 | 自營商 | 合計（張） |", "|---|---|---|---|---|"]
    for date in dates_sorted[:10]:
        v = by_date[date]
        f = v.get("Foreign_Investor", 0)
        t = v.get("Investment_Trust", 0)
        d_val = v.get("Dealer", 0)
        total = f + t + d_val
        lines.append(
            f"| {date} | {signed(f, 0)} | {signed(t, 0)} | {signed(d_val, 0)} | "
            f"{signed(total, 0)} |"
        )

    if dates_sorted:
        sum_f = sum(by_date[d].get("Foreign_Investor", 0) for d in dates_sorted)
        sum_t = sum(by_date[d].get("Investment_Trust", 0) for d in dates_sorted)
        sum_d = sum(by_date[d].get("Dealer", 0) for d in dates_sorted)
        lines.append(
            f"\n**近 {len(dates_sorted)} 日累積買超**：外資 {signed(sum_f, 0)} 張｜"
            f"投信 {signed(sum_t, 0)} 張｜自營 {signed(sum_d, 0)} 張｜"
            f"合計 {signed(sum_f + sum_t + sum_d, 0)} 張"
        )
    return "\n".join(lines)


def section_news(d: Dict, limit: int = 10) -> str:
    rows = d.get("news") or []
    if not rows:
        return "_查無近期新聞_"
    rows_sorted = sorted(rows, key=lambda x: x.get("date", ""), reverse=True)
    lines = []
    for r in rows_sorted[:limit]:
        title = r.get("title", "—")
        source = r.get("source", "—")
        date = r.get("date", "—")
        link = r.get("link", "")
        line = f"- **{date}** [{title}]({link}) — {source}" if link else f"- **{date}** {title} — {source}"
        lines.append(line)
    return "\n".join(lines)


def section_margin(d: Dict) -> str:
    """融資融券 (margin / short) — single-day snapshot from FinMind."""
    rows = d.get("margin") or []
    if not rows:
        return "_查無融資融券資料_"
    # Take latest row
    rows_sorted = sorted(rows, key=lambda x: x.get("date", ""), reverse=True)
    r = rows_sorted[0]
    date = r.get("date", "—")
    mb = int(r.get("MarginPurchaseTodayBalance") or 0)
    ms = int(r.get("ShortSaleTodayBalance") or 0)
    mb_buy = int(r.get("MarginPurchaseBuy") or 0)
    mb_sell = int(r.get("MarginPurchaseSell") or 0)
    mb_prev = int(r.get("MarginPurchaseYesterdayBalance") or 0)
    ms_buy = int(r.get("ShortSaleBuy") or 0)
    ms_sell = int(r.get("ShortSaleSell") or 0)
    mb_change = mb - mb_prev
    ratio = (mb / ms) if ms else None

    return (
        f"_資料日期：{date}_\n\n"
        "| 項目 | 融資 | 融券 |\n"
        "|---|---|---|\n"
        f"| 今日買進 | {num(mb_buy, 0)} 張 | {num(ms_buy, 0)} 張 |\n"
        f"| 今日賣出 | {num(mb_sell, 0)} 張 | {num(ms_sell, 0)} 張 |\n"
        f"| 今日餘額 | **{num(mb, 0)} 張** | **{num(ms, 0)} 張** |\n"
        f"| 昨日餘額 | {num(mb_prev, 0)} 張 | — |\n"
        f"| 餘額增減 | {signed(mb_change, 0)} 張 | — |\n"
        f"\n**融資融券比**：{num(ratio, 1) if ratio else '—'}\n"
    )


def section_margin_maintenance(d: Dict) -> str:
    """個股融資維持率 (sponsor-tier)."""
    rows = d.get("margin_maintenance") or []
    if not rows:
        return "_查無融資維持率資料（需 sponsor 帳號）_"
    rows_sorted = sorted(rows, key=lambda x: x.get("date", ""), reverse=True)[:10]
    lines = ["| 日期 | 融資餘額（張） | 融資成本線 | 維持率 |", "|---|---|---|---|"]
    for r in rows_sorted:
        lines.append(
            f"| {r.get('date', '—')} | {num(r.get('margin_balance'), 0)} | "
            f"{num(r.get('margin_cost'))} | {pct(r.get('margin_maintenance'), 2)} |"
        )
    # Highlight latest
    if rows_sorted:
        latest = rows_sorted[0]
        m = latest.get("margin_maintenance")
        if m and isinstance(m, (int, float)):
            if m < 130:
                lines.append(f"\n**警示**：融資維持率 {m:.1f}%，低於 130%，留意追繳風險。")
            elif m > 200:
                lines.append(f"\n融資維持率 {m:.1f}%，部位安全。")
    return "\n".join(lines)


def section_government_bank(d: Dict) -> str:
    """八大行庫買賣表 (sponsor-tier)."""
    rows = d.get("government_bank") or []
    if not rows:
        return "_查無八大行庫資料（需 sponsor 帳號）_"
    rows_sorted = sorted(rows, key=lambda x: x.get("date", ""), reverse=True)[:10]
    lines = ["| 日期 | 行庫買超（張） | 行庫賣超（張） |", "|---|---|---|"]
    for r in rows_sorted:
        buy = r.get("buy", 0) or 0
        sell = r.get("sell", 0) or 0
        lines.append(f"| {r.get('date', '—')} | {signed(buy, 0)} | {signed(sell, 0)} |")
    return "\n".join(lines)


def section_securities_lending(d: Dict) -> str:
    """借券成交明細 (securities lending)."""
    rows = d.get("securities_lending") or []
    if not rows:
        return "_查無借券資料_"
    rows_sorted = sorted(rows, key=lambda x: x.get("date", ""), reverse=True)[:10]
    lines = ["| 日期 | 類型 | 張數 | 費率 | 收盤價 | 原始到期 |", "|---|---|---|---|---|---|"]
    for r in rows_sorted:
        lines.append(
            f"| {r.get('date', '—')} | {r.get('transaction_type', '—')} | "
            f"{num(r.get('volume'), 0)} | {pct(r.get('fee_rate'), 2)} | "
            f"{num(r.get('close'))} | {r.get('original_return_date', '—')} |"
        )
    return "\n".join(lines)


def section_shareholding(d: Dict) -> str:
    rows = d.get("shareholding") or []
    if not rows:
        return "_查無股權結構資料_"
    # Latest date only
    latest_date = max((r.get("date", "") for r in rows), default="")
    latest = [r for r in rows if r.get("date") == latest_date]
    latest = sorted(latest, key=lambda x: x.get("ratio", 0) or 0, reverse=True)[:10]
    lines = [f"_資料日期：{latest_date}_\n", "| 持股人 | 持股比例 | 持股張數 |", "|---|---|---|"]
    for r in latest:
        lines.append(
            f"| {r.get('name', '—')} | {pct(r.get('ratio'))} | {num(r.get('shares'), 0)} |"
        )
    return "\n".join(lines)


def section_financial(d: Dict) -> str:
    """Quarterly financial statements (pivoted from FinMind long format).

    FinMind returns one row per (date, type) — we pivot to wide format.
    `type` is Chinese like '營業收入' / '基本每股盈餘' (Q1 / Q2 / Q3 / Q4).
    """
    rows = d.get("financial") or []
    if not rows:
        return "_查無季度財報_"

    # Map FinMind type names (English in the new version) to our column names
    type_map = {
        # English names (current FinMind)
        "Revenue": "revenue",
        "GrossProfit": "grossProfit",
        "OperatingIncome": "operatingIncome",
        "PreTaxIncome": "pretaxIncome",
        "IncomeAfterTaxes": "netIncome",
        "EPS": "EPS",
        # Legacy Chinese names (older FinMind)
        "營業收入": "revenue",
        "營業毛利": "grossProfit",
        "營業利益": "operatingIncome",
        "稅前淨利": "pretaxIncome",
        "本期淨利": "netIncome",
        "歸屬於母公司業主之淨利": "netIncome",
        "基本每股盈餘": "EPS",
    }
    # Pivot: (date, type) -> value
    pivot: Dict[str, Dict[str, float]] = {}
    for r in rows:
        d_str = r.get("date", "")
        t = r.get("type", "")
        v = r.get("value")
        col = type_map.get(t)
        if not col or d_str not in pivot:
            pivot.setdefault(d_str, {})
        try:
            pivot[d_str][col] = float(v) if v is not None else None
        except (TypeError, ValueError):
            continue

    if not pivot:
        return "_查無季度財報（資料格式無法解析）_"

    # Sort dates desc, take last 6
    dates = sorted(pivot.keys(), reverse=True)[:6]
    dates.reverse()
    keep = ["revenue", "grossProfit", "operatingIncome", "netIncome", "EPS"]
    headers = ["季度", "營收", "毛利", "營業利益", "淨利", "EPS"]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for d_str in dates:
        row = pivot[d_str]
        cells = [d_str]
        for k in keep:
            v = row.get(k)
            if v is None:
                cells.append("—")
            elif k == "EPS":
                cells.append(num(v, 2))
            else:
                # Large numbers in millions or thousands — show abbreviated
                cells.append(f"{v/1e8:.1f} 億" if abs(v) > 1e6 else num(v, 0))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def section_finlab_roe(d: Dict) -> str:
    """ROE history from FinMind TaiwanStockFinancialStatements (current, quarterly)."""
    rows = d.get("finlab_roe") or []
    if not rows:
        return "_查無 ROE 資料_"
    rows_sorted = sorted(rows, key=lambda x: x.get("date", ""), reverse=True)[:8]
    rows_sorted.reverse()
    lines = ["| 季度 | ROE 稅後 |", "|---|---|"]
    for r in rows_sorted:
        v = r.get("value")
        lines.append(f"| {r.get('date', '—')} | {pct(v, 2) if v is not None else '—'} |")
    if rows:
        lines.append(f"\n_資料來源：FinMind TaiwanStockFinancialStatements（current）_")
    return "\n".join(lines)


def section_finlab_revenue(d: Dict) -> str:
    """Monthly revenue with YoY from FinMind TaiwanStockMonthRevenue (current)."""
    rows = d.get("finlab_revenue") or []
    if not rows:
        return "_查無月營收資料_"
    # Most recent 12 months, sorted by date desc
    rows_sorted = sorted(rows, key=lambda x: x.get("date", ""), reverse=True)[:12]
    rows_sorted.reverse()
    lines = [
        "| 月份 | 營收（元） | 較去年同期 |",
        "|---|---|---|",
    ]
    for r in rows_sorted:
        v = r.get("value")
        yoy = r.get("yoy")
        yoy_s = f"{yoy:+.1f}%" if yoy is not None else "—"
        date_s = r.get("date", "—")
        if " " in date_s:
            date_s = date_s[:7]
        lines.append(f"| {date_s} | {num(v, 0) if v is not None else '—'} | {yoy_s} |")
    lines.append(f"\n_資料來源：FinMind TaiwanStockMonthRevenue（current）_")
    return "\n".join(lines)


def section_observations(d: Dict) -> str:
    """Auto-generate observation bullets from data."""
    bullets = []
    price = d.get("price") or []
    if len(price) >= 2:
        cur = float(price[-1].get("close") or 0)
        closes = [float(p.get("close") or 0) for p in price if p.get("close")]
        if closes:
            high = max(closes)
            low = min(closes)
            pos = (cur - low) / (high - low) * 100 if high > low else 0
            if pos > 80:
                bullets.append(f"目前股價位於近一年區間的 {pos:.0f}%（接近 52 週高），留意短線過熱風險。")
            elif pos < 20:
                bullets.append(f"目前股價位於近一年區間的 {pos:.0f}%（接近 52 週低），留意是否落底。")
            else:
                bullets.append(f"目前股價位於近一年區間的 {pos:.0f}%，處於中段。")
    elif len(price) == 1:
        bullets.append("僅有 1 日價格資料，無法判斷 52 週位置（需付費 FinMind 帳號才有歷史資料）。")

    inst = d.get("institutional") or []
    if inst:
        net_zhang = 0.0
        for r in inst:
            try:
                buy = float(r.get("buy") or 0) / 1000.0
                sell = float(r.get("sell") or 0) / 1000.0
                net_zhang += buy - sell
            except (TypeError, ValueError):
                pass
        if net_zhang > 0:
            bullets.append(f"當日三大法人合計買超 {num(net_zhang, 0)} 張，籌碼面偏多。")
        elif net_zhang < 0:
            bullets.append(f"當日三大法人合計賣超 {num(-net_zhang, 0)} 張，籌碼面偏空。")

    # Margin / short signal
    margin_rows = sorted(d.get("margin") or [], key=lambda x: x.get("date", ""), reverse=True)
    if margin_rows:
        m = margin_rows[0]
        mb_today = int(m.get("MarginPurchaseTodayBalance") or 0)
        mb_prev = int(m.get("MarginPurchaseYesterdayBalance") or 0)
        ms_today = int(m.get("ShortSaleTodayBalance") or 0)
        change = mb_today - mb_prev
        if mb_today > 0:
            if change > 0:
                bullets.append(f"融資餘額 {num(mb_today, 0)} 張，今日增 {num(change, 0)} 張，散戶加槓桿偏多。")
            elif change < 0:
                bullets.append(f"融資餘額 {num(mb_today, 0)} 張，今日減 {num(-change, 0)} 張，散戶去槓桿。")
            if ms_today > 0:
                bullets.append(f"融券餘額 {num(ms_today, 0)} 張（融券做空者少，多方力道強）。")

    per = d.get("per") or []
    if per:
        latest = per[-1]
        pe = latest.get("PER")
        if pe:
            try:
                pe_v = float(pe)
                if pe_v > 25:
                    bullets.append(f"P/E {pe_v:.1f} 偏高，估值可能偏貴。")
                elif pe_v < 12:
                    bullets.append(f"P/E {pe_v:.1f} 偏低，估值相對便宜。")
            except (TypeError, ValueError):
                pass
    if not bullets:
        bullets.append("_資料不足以產生觀察重點_")
    return "\n".join(f"- {b}" for b in bullets)


# ----- main report builder -----

def build_report(d: Dict) -> str:
    info = d.get("info") or [{}]
    company_name = info[0].get("stock_name", "") if info else ""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    err = d.get("fetch_errors") or []

    md = f"""# {d['stock_id']} {company_name} 個股分析報告

> 產出時間：{now}
> 資料來源：FinMind（涵蓋近一年）
> 工具：tw-invest-suite v0.1（個股深挖模式）

---

## 🏢 公司基本資料

{section_info(d)}

## 💰 股價概況（最近一日）

{section_price(d)}

## 📈 技術面

{section_technical(d)}

## 📊 估值

{section_valuation(d)}

## 💹 ROE 趨勢（財務體質）

{section_finlab_roe(d)}

## 💵 配息歷史

{section_dividend(d)}

## 🏦 三大法人（近 30 日）

{section_institutional(d)}

## 💰 融資融券

{section_margin(d)}

## 📊 融資維持率（sponsor 限定）

{section_margin_maintenance(d)}

## 🏛️ 八大行庫買賣（sponsor 限定）

{section_government_bank(d)}

## 📜 借券成交明細

{section_securities_lending(d)}

## 👥 股權結構（最近一筆）

{section_shareholding(d)}

## 📋 季度財報（近 6 季）

{section_financial(d)}

## 📈 月營收（近 12 個月）

{section_finlab_revenue(d)}

## 📰 近期新聞

{section_news(d)}

## 🎯 觀察重點

{section_observations(d)}

---
"""
    if err:
        md += "\n## ⚠️ 資料抓取警告\n\n"
        md += "\n".join(f"- {e}" for e in err)
        md += "\n"
    return md


def default_output_path(stock_id: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    folder = os.path.expanduser(f"~/.claude/skills/tw-invest-suite/reports/{today}")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, f"{stock_id}-deep-dive.md")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stock_id", help="Taiwan stock id, e.g. 2330")
    ap.add_argument("--out", help="output markdown path")
    ap.add_argument("--no-save", action="store_true", help="print to stdout only")
    args = ap.parse_args()

    d = fetch_all(args.stock_id)
    md = build_report(d)

    if args.no_save or not args.out:
        print(md)
    if not args.no_save:
        path = args.out or default_output_path(args.stock_id)
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        print(f"\n[saved] {path}", file=sys.stderr)


if __name__ == "__main__":
    main()
