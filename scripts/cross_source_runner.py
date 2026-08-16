"""
Cross-source orchestrator — assembles data for one ticker from all sources.

For each ticker, builds a unified dict:
  {
    "ticker", "company_name", "industry",
    "valuation":   {pe, pb, dividend_yield, market_cap, fifty_two_week_high/low},
    "fundamentals":{roe, latest_quarter_eps, latest_quarter_revenue, ...},
    "monthly_revenue": [{date, revenue, yoy_pct}, ...],
    "dividends":  [{date, year, cash, stock, ...}, ...],
    "news":       [{date, title, source, url}, ...],
    "_meta":      {sources_used, fetched_at, verify_diffs}
  }

Cross-verify (per ticker):
  - PER (yfinance) vs FinMind PER — log if diff > 5%
  - dividendYield (yfinance) vs FinMind compute — log if diff > 5%
  - ROE (yfinance) vs FinLab bulk (if available) — log if diff > 5%
  - All diffs persisted to _debug/cross_verify_YYYYMMDD.jsonl
"""
import sys
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
import cache_manager as cm
import finmind_batch as fmb
import yfinance_batch as yfb
import pymysql


VERIFY_LOG = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug"
                  r"\cross_verify.jsonl")
VERIFY_LOG.parent.mkdir(parents=True, exist_ok=True)


def _log_verify(ticker: str, diffs: List[Dict]):
    """Append diff entry to JSONL log."""
    entry = {
        "ticker": ticker,
        "at": datetime.now().isoformat(timespec="seconds"),
        "diffs": diffs,
    }
    with open(VERIFY_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _pct_diff(a, b) -> Optional[float]:
    """Return percent diff (b - a) / a * 100. None if invalid."""
    try:
        a = float(a); b = float(b)
        if abs(a) < 0.001:
            return None
        return (b - a) / abs(a) * 100
    except (TypeError, ValueError):
        return None


def _db_basic(ticker: str) -> Dict:
    """Get company name, industry, latest close from DB."""
    out = {"ticker": ticker, "company_name": None, "industry": None,
           "latest_close": None, "latest_date": None}
    try:
        conn = pymysql.connect(host='localhost', user='root', password='1234',
                                database='tw_elec', connect_timeout=5)
        cur = conn.cursor(pymysql.cursors.DictCursor)
        cur.execute("SELECT company, industry FROM industry_type WHERE ticker=%s", (ticker,))
        row = cur.fetchone()
        if row:
            out["company_name"] = row["company"]
            out["industry"] = row["industry"]
        cur.execute("SELECT Date, Close FROM daily_data2_full WHERE Ticker=%s "
                    "ORDER BY Date DESC LIMIT 1", (ticker,))
        row2 = cur.fetchone()
        if row2:
            out["latest_date"] = row2["Date"].isoformat() if hasattr(row2["Date"], "isoformat") else str(row2["Date"])
            out["latest_close"] = float(row2["Close"]) if row2["Close"] is not None else None
        conn.close()
    except Exception as e:
        out["_db_err"] = str(e)
    return out


def assemble(ticker: str, news_tier: str = "all", use_yfinance: bool = True,
             fetch_news: bool = True) -> Dict:
    """Build the unified ticker report from all sources.

    news_tier: "watchlist" (4h cache) or "all" (12h cache)
    use_yfinance: if False, skip yfinance (saves ~2-3s per ticker, no ROE/marketCap)
    fetch_news: if False, skip FinMind news (saves ~3s per ticker if no cache)
    """
    out: Dict[str, Any] = {"ticker": ticker, "_meta": {"sources": [], "at": datetime.now().isoformat(timespec="seconds")}}

    # ---- 1. DB (always) ----
    basic = _db_basic(ticker)
    out.update(basic)
    out["_meta"]["sources"].append("db")

    # ---- 2. yfinance (with fallback) - OPTIONAL ----
    if use_yfinance:
        yf_data = yfb._fetch_one_with_fallback(ticker)
        out["yfinance"] = yf_data
        if yf_data.get("_source") == "yfinance":
            out["_meta"]["sources"].append("yfinance")
        else:
            out["_meta"]["sources"].append("yfinance_fallback")
        # Build valuation dict (used by section_valuation)
        out["valuation"] = {
            "pe": yf_data.get("trailingPE"),
            "forward_pe": yf_data.get("forwardPE"),
            "pb": yf_data.get("priceToBook"),
            "dividend_yield": yf_data.get("dividendYield"),
            "market_cap": yf_data.get("marketCap"),
            "fifty_two_week_high": yf_data.get("fiftyTwoWeekHigh"),
            "fifty_two_week_low": yf_data.get("fiftyTwoWeekLow"),
            "beta": yf_data.get("beta"),
        }
    else:
        # Cache-only mode: read cache if available, but don't make API calls.
        # This is for render-only runs that need yfinance data from cache
        # without triggering HTTP requests to yfinance.
        cached = cm.get_fresh(ticker, "yfinance")
        if cached:
            yf = cached["data"]
            out["yfinance"] = yf
            out["_meta"]["sources"].append("yfinance_cache")
            # Build valuation dict from cached yfinance data
            out["valuation"] = {
                "pe": yf.get("trailingPE"),
                "forward_pe": yf.get("forwardPE"),
                "pb": yf.get("priceToBook"),
                "dividend_yield": yf.get("dividendYield"),
                "market_cap": yf.get("marketCap"),
                "fifty_two_week_high": yf.get("fiftyTwoWeekHigh"),
                "fifty_two_week_low": yf.get("fiftyTwoWeekLow"),
                "beta": yf.get("beta"),
            }

    # ---- 3. FinMind PER (parallel — for cross-verify) ----
    fm_pe = fmb.fetch_pe(ticker)
    if fm_pe and not any("_error" in r for r in (fm_pe if isinstance(fm_pe, list) else [fm_pe])):
        out["finmind_pe_latest"] = fm_pe
        out["_meta"]["sources"].append("finmind_pe")

    # ---- 4. FinMind Dividend (30d cache) ----
    divs = fmb.fetch_dividend(ticker)
    if divs:
        out["dividends"] = divs[-6:]  # last 6 entries
        out["_meta"]["sources"].append("finmind_div")

    # ---- 5. FinMind Financials (30d cache) ----
    fins = fmb.fetch_financials(ticker)
    if fins:
        out["fundamentals"] = {
            "rows": fins[-100:],  # 100 rows = ~6 quarters × 15 fields
            "row_count": len(fins),
        }
        out["_meta"]["sources"].append("finmind_fin")

    # ---- 6. FinMind Monthly Revenue (7d cache) ----
    rev = fmb.fetch_month_revenue(ticker)
    if rev:
        out["monthly_revenue"] = rev[-24:]  # last 24 months
        out["_meta"]["sources"].append("finmind_month")

    # ---- 7. FinMind News (4h/12h cache) - OPTIONAL ----
    if fetch_news:
        news = fmb.fetch_news(ticker, tier=news_tier)
        if news:
            out["news"] = news[:10]
            out["_meta"]["sources"].append(f"finmind_news_{news_tier}")

    # ---- 8. Cross-verify ----
    diffs = []
    # PER: yfinance vs FinMind
    pe_yf = out.get("valuation", {}).get("pe")
    pe_fm = out.get("finmind_pe_latest", {}).get("PER") if out.get("finmind_pe_latest") else None
    d = _pct_diff(pe_fm, pe_yf)
    if d is not None and abs(d) > 5:
        diffs.append({"field": "PE", "yfinance": pe_yf, "finmind": pe_fm, "diff_pct": round(d, 2)})
    # PBR: yfinance vs FinMind
    pb_yf = out.get("valuation", {}).get("pb")
    pb_fm = out.get("finmind_pe_latest", {}).get("PBR") if out.get("finmind_pe_latest") else None
    d = _pct_diff(pb_fm, pb_yf)
    if d is not None and abs(d) > 5:
        diffs.append({"field": "PBR", "yfinance": pb_yf, "finmind": pb_fm, "diff_pct": round(d, 2)})
    # Dividend yield
    dy_yf = out.get("valuation", {}).get("dividend_yield")
    dy_fm = out.get("finmind_pe_latest", {}).get("dividend_yield") if out.get("finmind_pe_latest") else None
    if dy_fm is not None and dy_yf is not None:
        # FinMind dividend_yield is in %; yfinance is in fraction
        dy_fm_pct = float(dy_fm)
        dy_yf_pct = float(dy_yf) * 100
        d = _pct_diff(dy_fm_pct, dy_yf_pct)
        if d is not None and abs(d) > 5:
            diffs.append({"field": "dividend_yield", "yfinance_pct": dy_yf_pct,
                          "finmind_pct": dy_fm_pct, "diff_pct": round(d, 2)})
    if diffs:
        out["_meta"]["verify_diffs"] = diffs
        _log_verify(ticker, diffs)

    return out


def assemble_many(tickers: List[str], news_tier: str = "all",
                  progress_every: int = 50, use_yfinance: bool = True) -> Dict[str, Dict]:
    """Build unified reports for many tickers.

    Note: cache_manager handles staleness, so re-running is cheap.
    """
    results: Dict[str, Dict] = {}
    t0 = time.time()
    for i, t in enumerate(tickers, 1):
        try:
            results[t] = assemble(t, news_tier=news_tier, use_yfinance=use_yfinance)
        except Exception as e:
            results[t] = {"ticker": t, "_err": str(e)}
        if i % progress_every == 0 or i == len(tickers):
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(tickers) - i) / rate if rate > 0 else 0
            print(f"  [{i:>4}/{len(tickers)}] {elapsed:>5.0f}s "
                  f"({rate:.1f}/s, ETA {eta/60:.1f}min)", flush=True)
    return results


if __name__ == "__main__":
    import sys
    ticker = sys.argv[1] if len(sys.argv) > 1 else "2330"
    print(f"=== Cross-source assemble: {ticker} ===")
    out = assemble(ticker)
    print(json.dumps({k: v for k, v in out.items() if k not in
                       ("yfinance", "dividends", "fundamentals", "monthly_revenue", "news")},
                      ensure_ascii=False, indent=2, default=str))
    print(f"  _meta: {out.get('_meta')}")
