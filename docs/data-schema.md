# Data Schema — tw-invest-suite

## MySQL — `tw_elec`

主要倉儲在 `localhost:3306`，連線設定：
```
host=localhost user=root password=1234 database=tw_elec
```

### 表 1: `daily_data2_full`
個股每日 OHLCV + 三大法人 + 融資融券

| 欄位 | 型別 | 說明 |
|---|---|---|
| Ticker | VARCHAR(6) | 股票代號（PK 第一段） |
| Date | DATE | 交易日期（PK 第二段） |
| Open | DECIMAL(10,2) | 開盤 |
| High | DECIMAL(10,2) | 最高 |
| Low | DECIMAL(10,2) | 最低 |
| Close | DECIMAL(10,2) | 收盤 |
| Volume | BIGINT | 成交量（**張**） |
| ForeignNet | BIGINT | 外資買賣超（**股**，除 1000 = 張） |
| InvestmentNet | BIGINT | 投信買賣超（股） |
| DealerNet | BIGINT | 自營買賣超（股） |
| ThreeNet | BIGINT | 三大法人合計（股） |
| MarginBalance | BIGINT | 融資餘額（**張**） |
| ShortBalance | BIGINT | 融券餘額（**張**） |
| sma_13 | DECIMAL(10,2) | 13 日 SMA（DB 預算） |
| sma_27 | DECIMAL(10,2) | 27 日 SMA |
| sma_54 | DECIMAL(10,2) | 54 日 SMA |
| rsi_14 | DECIMAL(5,2) | 14 日 RSI |
| atr_14 | DECIMAL(10,2) | 14 日 ATR |
| macd | DECIMAL(10,4) | MACD |
| macd_signal | DECIMAL(10,4) | MACD signal |
| macd_hist | DECIMAL(10,4) | MACD histogram |
| bb_upper | DECIMAL(10,2) | 布林通道上軌 |
| bb_middle | DECIMAL(10,2) | 布林中軌 |
| bb_lower | DECIMAL(10,2) | 布林下軌 |
| kd_k | DECIMAL(5,2) | KD 指標 K |
| kd_d | DECIMAL(5,2) | KD 指標 D |

**20 年+ 歷史**，1,962 隻 ticker。

### 表 2: `stock_news`
新聞（含實體 sentiment 標記）

| 欄位 | 型別 | 說明 |
|---|---|---|
| id | BIGINT | PK |
| ticker | VARCHAR(6) | 股票代號 |
| title | TEXT | 標題 |
| source | VARCHAR(64) | 來源 |
| url | TEXT | 連結 |
| published_at | DATETIME | 發布時間 |
| sentiment_label | VARCHAR(16) | pos / neg / neutral |
| body | TEXT | 內文（如有） |

**2.3M 筆**，平均每 ticker 1,200 筆新聞。

### 表 3: `industry_type`
Ticker 行業對應

| 欄位 | 型別 | 說明 |
|---|---|---|
| ticker | VARCHAR(6) | PK |
| industry | VARCHAR(64) | e.g. 半導體業 |

### 表 4: `market_screen_runs`
選股 run 紀錄

| 欄位 | 型別 | 說明 |
|---|---|---|
| id | INT AUTO_INCREMENT | PK |
| run_at | DATETIME | 跑選股的時間 |
| total_tickers | INT | 掃的 ticker 總數 |
| notes | TEXT | 備註 |

### 表 5: `market_screen_picks`
選股結果（24 檔）

| 欄位 | 型別 | 說明 |
|---|---|---|
| id | INT AUTO_INCREMENT | PK |
| run_id | INT | FK → market_screen_runs.id |
| ticker | VARCHAR(6) | 股票代號 |
| direction | ENUM('long', 'short') | 多/空 |
| price_bucket | ENUM('small', 'mid', 'large', 'mega') | 4 個價位 bucket |
| score | DECIMAL(10,4) | 評分 |
| rank_in_bucket | TINYINT | bucket 內排名（1-3） |
| reasoning | TEXT | 為何選 |

---

## Cache — `~/.cache_manager/`

disk-based TTL cache，key 為 ticker，value 為 JSON。

```
~/.cache_manager/
├── yfinance/
│   ├── 2330.json
│   ├── 8039.json
│   └── ...
├── finmind_pe/
├── finmind_div/
├── finmind_fin/
├── finmind_month/
├── finmind_news/
└── _meta.json       ← 統計
```

格式範例 `yfinance/2330.json`：
```json
{
  "data": {
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
    "fiftyTwoWeekLow": 920.0
  },
  "fetched_at": "2026-08-15T22:30:12",
  "ttl_sec": 86400
}
```

---

## Cross-source data dict

`cross_source_runner.assemble()` 輸出：

```python
{
  "ticker": "2330",
  "company_name": "台積電",
  "industry": "半導體業",
  "yfinance": {
    "currentPrice": 1230.5,
    "marketCap": 31880000000000,
    "trailingPE": 28.5,
    "priceToBook": 6.2,
    "dividendYield": 0.015,
    "returnOnEquity": 0.22,
    "beta": 0.85,
    "longName": "...",
    "industry": "Semiconductors",
    "fiftyTwoWeekHigh": 1340.0,
    "fiftyTwoWeekLow": 920.0,
  },
  "valuation": {
    "pe": 28.5,
    "pb": 6.2,
    "dividend_yield": 1.5,  # 已是百分比
    "market_cap": 31880,  # 億元
    "fifty_two_week_high": 1340.0,
    "fifty_two_week_low": 920.0,
  },
  "monthly_revenue": [
    {"date": "2026-07", "revenue": 234000000, "yoy_pct": 12.5, "mom_pct": -3.2},
    ...
  ],
  "dividends": [
    {"year": 2025, "cash": 4.5, "stock": 0.0},
    ...
  ],
  "fundamentals": [
    {"date": "2026-Q1", "revenue": 800000, "ni": 250000, "eps": 9.6},
    ...
  ],
  "news": [
    {"date": "2026-08-15", "title": "...", "source": "...", "link": "..."},
    ...
  ],
  "_meta": {
    "sources": ["db", "yfinance", "finmind_pe", "finmind_div", "finmind_fin", "finmind_month"],
    "fetched_at": "2026-08-15T22:30:12"
  }
}
```

`valuation` 永遠是「顯示格式」：PE/PB 是 ratio，dividend_yield 是百分比，market_cap 是億元（已除 1e8）。
