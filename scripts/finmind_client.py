"""
FinMind API client for Taiwan stock data.
Docs: https://finmindtrade.com/

Usage:
    import finmind_client as fm
    data = fm.stock_price("2330")

Token resolution order:
    1. FINMIND_TOKEN environment variable
    2. ~/.finmind_token file (single line, no newline)
"""
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Dict, List, Optional

API_BASE = "https://api.finmindtrade.com/api/v4/data"
TOKEN_FILE = os.path.expanduser("~/.finmind_token")


def _get_token() -> str:
    """Resolve FinMind token from env or file. Returns empty string if not set
    (FinMind allows limited access without a token — e.g. TaiwanStockInfo)."""
    token = os.environ.get("FINMIND_TOKEN", "").strip()
    if token:
        return token
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as f:
            raw = f.read()
        # Strip UTF-8 BOM if present (Windows editors and Out-File add it)
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]
        token = raw.decode("utf-8", errors="ignore").strip()
        if token:
            return token
    return ""


def query(
    dataset: str,
    stock_id: str = "",
    start_date: str = "",
    end_date: str = "",
    token: Optional[str] = None,
    data_id: str = "",
    timeout: int = 30,
    max_retries: int = 3,
) -> List[Dict]:
    """Query a FinMind dataset. Returns a list of records (dicts).

    FinMind API quirk: omitting either `start_date` or `end_date` causes a
    misleading 400 "Token is illegal" error. We always pass a default range
    (last 365 days) when the caller doesn't provide one.

    Note: FinMind's free/limited tokens may ignore the `stock_id` filter at
    the server side. We always filter client-side as well to be safe.

    `data_id` is the alternate filter param (some sponsor-only datasets like
    TaiwanStockTradingDailyReport expect `data_id` instead of `stock_id`).
    If both are given, `stock_id` wins (sent as both for max compat).

    Auth: the official FinMind docs show `Authorization: Bearer <token>`
    header. We send both header AND query param for max compatibility.
    """
    if token is None:
        token = _get_token()

    if not start_date or not end_date:
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=365)
        if not end_date:
            end_date = end_dt.strftime("%Y-%m-%d")
        if not start_date:
            start_date = start_dt.strftime("%Y-%m-%d")

    params = {"dataset": dataset, "token": token}
    if stock_id:
        params["stock_id"] = stock_id
        params["data_id"] = stock_id  # belt-and-suspenders
    elif data_id:
        params["data_id"] = data_id
    params["start_date"] = start_date
    params["end_date"] = end_date

    url = f"{API_BASE}?{urllib.parse.urlencode(params)}"
    last_err: Optional[Exception] = None

    for attempt in range(max_retries):
        try:
            headers = {
                "User-Agent": "tw-invest-suite/0.1",
                "Authorization": f"Bearer {token}",
            }
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            if payload.get("status") != 200:
                raise RuntimeError(
                    f"FinMind error ({dataset}): {payload.get('msg', 'unknown')}"
                )
            rows = payload.get("data", []) or []
            # Client-side filter (server-side may be ignored depending on token)
            if stock_id:
                rows = [r for r in rows if str(r.get("stock_id", "")).strip() == str(stock_id).strip()]
            return rows
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="ignore")
            except Exception:  # noqa: BLE001
                pass
            last_err = RuntimeError(f"HTTP {e.code}: {body[:300]}")
        except Exception as e:  # noqa: BLE001
            last_err = e
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)

    raise RuntimeError(f"FinMind query failed after {max_retries} retries: {last_err}")


# ----- convenience helpers for common datasets -----

def stock_info(stock_id: str) -> List[Dict]:
    """Company info (name, industry, market)."""
    return query("TaiwanStockInfo", stock_id=stock_id)


def stock_price(stock_id: str, start_date: str = "", end_date: str = "") -> List[Dict]:
    """Daily OHLCV."""
    return query("TaiwanStockPrice", stock_id=stock_id,
                 start_date=start_date, end_date=end_date)


def stock_per(stock_id: str, start_date: str = "", end_date: str = "") -> List[Dict]:
    """Daily P/E and P/B ratio."""
    return query("TaiwanStockPER", stock_id=stock_id,
                 start_date=start_date, end_date=end_date)


def stock_dividend(stock_id: str, start_date: str = "", end_date: str = "") -> List[Dict]:
    """Historical cash + stock dividends."""
    return query("TaiwanStockDividend", stock_id=stock_id,
                 start_date=start_date, end_date=end_date)


def stock_institutional(
    stock_id: str, start_date: str = "", end_date: str = ""
) -> List[Dict]:
    """Daily net buy/sell by foreign, investment trust, dealer."""
    return query(
        "TaiwanStockInstitutionalInvestorsBuySell",
        stock_id=stock_id,
        start_date=start_date,
        end_date=end_date,
    )


def stock_margin(
    stock_id: str, start_date: str = "", end_date: str = ""
) -> List[Dict]:
    """個股融資融券表 (TaiwanStockMarginPurchaseShortSale).

    Free tier / sandbox accounts may return only a single day.
    Fields: date, stock_id, MarginPurchaseBuy/Sell/TodayBalance, ShortSaleBuy/Sell/TodayBalance, etc.
    """
    return query(
        "TaiwanStockMarginPurchaseShortSale",
        stock_id=stock_id,
        start_date=start_date,
        end_date=end_date,
    )


def stock_securities_lending(
    stock_id: str, start_date: str = "", end_date: str = ""
) -> List[Dict]:
    """借券成交明細 (TaiwanStockSecuritiesLending).

    Fields: date, stock_id, transaction_type, volume, fee_rate, close, etc.
    """
    return query(
        "TaiwanStockSecuritiesLending",
        stock_id=stock_id,
        start_date=start_date,
        end_date=end_date,
    )


def total_institutional(
    start_date: str = "", end_date: str = ""
) -> List[Dict]:
    """台灣市場整體法人買賣表 (TaiwanStockTotalInstitutionalInvestors).

    Note: this is a market-wide dataset, not per-stock.
    """
    return query(
        "TaiwanStockTotalInstitutionalInvestors",
        start_date=start_date,
        end_date=end_date,
    )


# --- Sponsor-tier datasets ---

def stock_margin_maintenance(
    stock_id: str, start_date: str = "", end_date: str = ""
) -> List[Dict]:
    """個股融資維持率 (TaiwanStockMarginMaintenance) — sponsor tier.

    Fields: date, stock_id, margin_balance (張), margin_cost, margin_ratio, margin_maintenance (%)
    """
    return query(
        "TaiwanStockMarginMaintenance",
        stock_id=stock_id,
        start_date=start_date,
        end_date=end_date,
    )


def stock_government_bank_buysell(
    stock_id: str, start_date: str = "", end_date: str = ""
) -> List[Dict]:
    """八大行庫買賣表 (TaiwanStockGovernmentBankBuySell) — sponsor tier.

    NOTE: Like TaiwanStockNews, this dataset is too large to accept end_date.
    We go direct to the API without it.
    """
    token = _get_token()
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    params = {
        "dataset": "TaiwanStockGovernmentBankBuySell",
        "stock_id": stock_id,
        "start_date": start_date,
        "token": token,
    }
    url = f"{API_BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "tw-invest-suite/0.1", "Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.loads(r.read().decode("utf-8"))
    if payload.get("status") != 200:
        raise RuntimeError(f"FinMind govbank error: {payload.get('msg', 'unknown')}")
    rows = payload.get("data", []) or []
    if stock_id:
        rows = [r for r in rows if str(r.get("stock_id", "")).strip() == str(stock_id).strip()]
    return rows


def stock_trading_daily_report(
    stock_id: str, start_date: str = "", end_date: str = ""
) -> List[Dict]:
    """台股分點資料表 (TaiwanStockTradingDailyReport) — sponsor tier.

    Expects `data_id` param (handled in query()).
    """
    return query(
        "TaiwanStockTradingDailyReport",
        stock_id=stock_id,
        start_date=start_date,
        end_date=end_date,
    )


def total_exchange_margin_maintenance(
    start_date: str = "", end_date: str = ""
) -> List[Dict]:
    """台灣大盤融資維持率 (TaiwanTotalExchangeMarginMaintenance) — backer/sponsor.

    Market-wide, not per-stock.
    """
    return query(
        "TaiwanTotalExchangeMarginMaintenance",
        start_date=start_date,
        end_date=end_date,
    )


def stock_news(stock_id: str, start_date: str = "", end_date: str = "") -> List[Dict]:
    """News mentions for the stock.

    NOTE: FinMind's TaiwanStockNews dataset explicitly forbids end_date.
    The query() default-fill below would still inject one, so we go direct.
    """
    token = _get_token()
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    params = {"dataset": "TaiwanStockNews", "stock_id": stock_id,
              "start_date": start_date, "token": token}
    url = f"{API_BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": "tw-invest-suite/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.loads(r.read().decode("utf-8"))
    if payload.get("status") != 200:
        raise RuntimeError(f"FinMind news error: {payload.get('msg', 'unknown')}")
    rows = payload.get("data", []) or []
    if stock_id:
        rows = [r for r in rows if str(r.get("stock_id", "")).strip() == str(stock_id).strip()]
    return rows


def stock_shareholding(
    stock_id: str, start_date: str = "", end_date: str = ""
) -> List[Dict]:
    """Shareholding % (e.g. major shareholders, board)."""
    return query("TaiwanStockShareholding", stock_id=stock_id,
                 start_date=start_date, end_date=end_date)


def stock_financial(
    stock_id: str, start_date: str = "", end_date: str = ""
) -> List[Dict]:
    """Quarterly income statement."""
    return query("TaiwanStockFinancialStatements", stock_id=stock_id,
                 start_date=start_date, end_date=end_date)


def stock_balance_sheet(
    stock_id: str, start_date: str = "", end_date: str = ""
) -> List[Dict]:
    """Quarterly balance sheet."""
    return query("TaiwanStockBalanceSheet", stock_id=stock_id,
                 start_date=start_date, end_date=end_date)


if __name__ == "__main__":
    import sys

    stock_id = sys.argv[1] if len(sys.argv) > 1 else "2330"
    print(f"[smoke] Fetching {stock_id} price (last 60 days)...")
    rows = stock_price(stock_id)
    if not rows:
        print("  no data — check token or stock id")
        sys.exit(1)
    print(f"  {len(rows)} rows, latest date: {rows[-1].get('date')}")
    print(f"  latest close: {rows[-1].get('close')}")
