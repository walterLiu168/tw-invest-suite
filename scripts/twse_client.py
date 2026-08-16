"""
TWSE (Taiwan Stock Exchange) OpenAPI client — free, no auth, real-time.

Docs: https://www.twse.com.tw/exchangeReport/STOCK_DAY
Returns per-month daily OHLCV. We aggregate multiple months to get historical.
Note: TWSE only covers listed (上市) stocks. For OTC (上櫃) use TPEx API.
"""
import json
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Dict, List, Optional

BASE = "https://www.twse.com.tw/exchangeReport/STOCK_DAY"

# TWSE SSL cert sometimes fails to verify on Windows — bypass
_SSL_CTX = ssl.create_default_context()
_SSL_CTX.check_hostname = False
_SSL_CTX.verify_mode = ssl.CERT_NONE


def _roc_date(dt: datetime) -> str:
    """Return YYYMMDD for TWSE API."""
    return f"{dt.year}{dt.month:02d}{dt.day:02d}"


def fetch_month(year: int, month: int, stock_id: str) -> List[Dict]:
    """Fetch one month of daily OHLCV for a TWSE-listed stock."""
    # TWSE date param is the FIRST day of the month we want
    date_param = f"{year}{month:02d}01"
    url = f"{BASE}?response=json&date={date_param}&stockNo={stock_id}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "tw-invest-suite/0.1",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30, context=_SSL_CTX) as r:
        body = json.loads(r.read().decode("utf-8"))
    if body.get("stat") != "OK":
        return []
    rows = []
    for row in body.get("data") or []:
        # Row format: [date, volume_shares, amount, open, high, low, close, change, transactions, _]
        try:
            roc_date = row[0]  # e.g. "115/08/12"
            # Convert ROC date to ISO: 115/08/12 -> 2026-08-12
            d_parts = roc_date.split("/")
            roc_y = int(d_parts[0])
            iso = f"{roc_y + 1911}-{int(d_parts[1]):02d}-{int(d_parts[2]):02d}"
            close = float(row[6].replace(",", ""))
            open_p = float(row[3].replace(",", ""))
            high = float(row[4].replace(",", ""))
            low = float(row[5].replace(",", ""))
            vol_shares = int(row[1].replace(",", ""))
            amount = int(row[2].replace(",", ""))
            # TWSE volume in 股, change is +/- price difference
            change = row[7]
            try:
                change_val = float(change.replace(",", ""))
            except (ValueError, AttributeError):
                change_val = 0
            rows.append({
                "date": iso,
                "stock_id": stock_id,
                "open": open_p,
                "max": high,
                "min": low,
                "close": close,
                "Trading_Volume": vol_shares,
                "Trading_money": amount,  # TWSE provides this directly
                "spread": change_val,
            })
        except (ValueError, IndexError, AttributeError):
            continue
    return rows


def stock_price_history(stock_id: str, months: int = 12) -> List[Dict]:
    """Fetch the last N months of daily OHLCV for a TWSE-listed stock.

    Returns rows sorted ascending by date.
    """
    all_rows: List[Dict] = []
    end = datetime.now()
    # Walk back N months
    for i in range(months):
        # Calculate target year/month for `i` months back
        m_target = end.month - i
        y_target = end.year
        while m_target <= 0:
            m_target += 12
            y_target -= 1
        rows = fetch_month(y_target, m_target, stock_id)
        all_rows.extend(rows)
    # Sort by date asc and dedupe
    all_rows.sort(key=lambda r: r.get("date", ""))
    seen = set()
    deduped = []
    for r in all_rows:
        if r["date"] in seen:
            continue
        seen.add(r["date"])
        deduped.append(r)
    return deduped


if __name__ == "__main__":
    import sys
    sid = sys.argv[1] if len(sys.argv) > 1 else "2330"
    print(f"Fetching {sid} — 12 months...")
    rows = stock_price_history(sid, months=12)
    print(f"Got {len(rows)} rows")
    if rows:
        print(f"First: {rows[0]}")
        print(f"Last:  {rows[-1]}")
