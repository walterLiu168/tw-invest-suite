"""
TPEx (Taipei Exchange) OpenAPI client — 上櫃 (OTC) stocks. Free, no auth.

API: https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/
Returns per-day quotes. We walk back day-by-day for the requested window.

Compare with twse_client.py for the listed (上市) equivalent.
"""
import json
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Dict, List, Optional

BASE = "https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php"
# Backup endpoint (sometimes works when the primary is rate-limited)
BASE_ALT = "https://www.tpex.org.tw/web/stock/aftertrading/otc_quotes_no1430/stk_wn1430_result.php"

_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


def _roc_date(dt: datetime) -> str:
    """YYYY/MM/DD format expected by TPEx."""
    return f"{dt.year - 1911}/{dt.month:02d}/{dt.day:02d}"


def fetch_day(target: datetime, retries: int = 3) -> List[Dict]:
    """Fetch one day of OTC stock quotes."""
    d_str = _roc_date(target)
    last_err: Optional[Exception] = None
    for attempt in range(retries):
        try:
            url = f"{BASE}?l=zh-tw&d={d_str}&o=json"
            req = urllib.request.Request(url, headers={
                "User-Agent": "tw-invest-suite/0.1",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as r:
                body = json.loads(r.read().decode("utf-8"))
            # TPEx returns "ok" lowercase (TWSE returns "OK" uppercase — inconsistent)
            if body.get("stat", "").lower() != "ok":
                return []
            rows = []
            # The OTC table has header row, then per-stock rows
            tables = body.get("tables") or []
            if not tables:
                return []
            table = tables[0]
            data_rows = table.get("data", [])
            for row in data_rows:
                try:
                    # TPEx row format (zh-tw, from official fields list):
                    # [代號, 名稱, 收盤, 漲跌, 開盤, 最高, 最低, 均價, 成交股數, 成交金額, 成交筆數, ...]
                    stock_id = str(row[0]).strip()
                    close = float(str(row[2]).replace(",", ""))
                    spread = float(str(row[3]).replace(",", "")) if row[3] not in (None, "", "--") else 0
                    open_p = float(str(row[4]).replace(",", "")) if row[4] not in (None, "", "--") else close
                    high = float(str(row[5]).replace(",", "")) if row[5] not in (None, "", "--") else close
                    low = float(str(row[6]).replace(",", "")) if row[6] not in (None, "", "--") else close
                    vol_str = str(row[8]).replace(",", "")  # index 8 is 成交股數
                    vol_shares = int(vol_str) if vol_str not in (None, "", "--") else 0
                    amount_str = str(row[9]).replace(",", "")  # index 9 is 成交金額
                    amount = int(float(amount_str)) if amount_str not in (None, "", "--") else 0
                    rows.append({
                        "date": target.strftime("%Y-%m-%d"),
                        "stock_id": stock_id,
                        "open": open_p,
                        "max": high,
                        "min": low,
                        "close": close,
                        "Trading_Volume": vol_shares,
                        "Trading_money": amount,
                        "spread": spread,
                    })
                except (ValueError, IndexError, AttributeError, TypeError):
                    continue
            return rows
        except Exception as e:  # noqa: BLE001
            last_err = e
    return []


def stock_price_history(stock_id: str, days: int = 250) -> List[Dict]:
    """Walk back `days` trading days from today, fetching per-day OTC data.

    Note: TPEx returns ALL OTC stocks per query (~800 stocks). Each fetch is one
    HTTP call. For 250 days that's 250 calls. We could batch with month-level
    endpoints but they don't exist for TPEx, so day-by-day it is.
    """
    all_rows: List[Dict] = []
    today = datetime.now()
    seen_dates = set()
    cur = today
    attempts_left = days * 2  # generous cap in case of weekends/holidays
    while attempts_left > 0 and len(seen_dates) < days:
        # Skip weekends
        if cur.weekday() < 5:
            rows = fetch_day(cur)
            for r in rows:
                if r["stock_id"] == stock_id:
                    all_rows.append(r)
                    seen_dates.add(r["date"])
                    break
        cur -= timedelta(days=1)
        attempts_left -= 1
    all_rows.sort(key=lambda r: r.get("date", ""))
    return all_rows


if __name__ == "__main__":
    import sys
    sid = sys.argv[1] if len(sys.argv) > 1 else "8069"
    days = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    print(f"Fetching OTC {sid} for last {days} days...")
    rows = stock_price_history(sid, days=days)
    print(f"Got {len(rows)} rows")
    if rows:
        print(f"First: {rows[0]}")
        print(f"Last:  {rows[-1]}")
