# Cache Format — disk-based TTL cache

## 路徑

`~/.cache_manager/<dataset>/<TICKER>.json`

例：`~/.cache_manager/yfinance/2330.json`

## TTL

| dataset | TTL (sec) | 對應天數 |
|---|---|---|
| yfinance | 86400 | 1d |
| finmind_pe | 86400 | 1d |
| finmind_div | 2592000 | 30d |
| finmind_fin | 2592000 | 30d |
| finmind_month | 2592000 | 30d |
| finmind_news | 14400 | 4h |

## 通用 schema

```json
{
  "data": <payload>,
  "fetched_at": "2026-08-15T22:30:12",
  "ttl_sec": 86400,
  "_stale": false   // optional, set by cache_manager if past TTL
}
```

## 各 dataset payload

### yfinance

```json
{
  "currentPrice": 1230.5,
  "marketCap": 31880000000000,
  "trailingPE": 28.5,
  "priceToBook": 6.2,
  "dividendYield": 0.015,
  "returnOnEquity": 0.22,
  "beta": 0.85,
  "longName": "台灣積體電路製造股份有限公司",
  "industry": "Semiconductors",
  "fiftyTwoWeekHigh": 1340.0,
  "fiftyTwoWeekLow": 920.0,
  "sector": "Technology",
  "sharesOutstanding": 25930000000
}
```

### finmind_pe (TaiwanStockPER)

```json
[
  {
    "date": "2026-08-14",
    "stock_id": "2330",
    "PER": 28.5,
    "dividend_yield": 1.5
  },
  ...
]
```

### finmind_div (TaiwanStockDividend)

```json
[
  {
    "date": "2025-07-15",
    "stock_id": "2330",
    "year": 2025,
    "stock_and_cache_dividend": 4.5
  },
  ...
]
```

### finmind_fin (TaiwanStockFinancialStatements)

```json
[
  {
    "date": "2026-Q1",
    "stock_id": "2330",
    "type": "Q1",
    "Revenue": 800000000000,
    "NetIncome": 250000000000,
    "EPS": 9.6
  },
  ...
]
```

### finmind_month (TaiwanStockMonthRevenue)

```json
[
  {
    "date": "2026-07-01",
    "stock_id": "2330",
    "revenue": 234000000000,
    "revenue_month": 7,
    "revenue_year": 2026
  },
  ...
]
```

### finmind_news (TaiwanStockNews)

```json
[
  {
    "date": "2026-08-15T09:30:00",
    "stock_id": "2330",
    "title": "台積電 Q2 營收創新高",
    "source": "MoneyDJ",
    "link": "https://..."
  },
  ...
]
```

## Read/Write 範例

```python
from cache_manager import get_cache

cache = get_cache("yfinance", ttl_sec=86400)
data = cache.get("2330")  # 自動讀 + 標 stale

if cache.is_stale("2330") or data is None:
    # 抓新資料
    new_data = yf.Ticker("2330").info
    cache.set("2330", new_data)
else:
    pass
```
