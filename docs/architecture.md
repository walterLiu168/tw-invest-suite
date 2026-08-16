# Architecture — tw-invest-suite

## 系統總覽

```
                ┌──────────────────────────────────────┐
                │  Windows Task Scheduler 22:25        │
                │  tw-invest-suite-daily              │
                └───────────────┬──────────────────────┘
                                ▼
                ┌──────────────────────────────────────┐
                │  scripts\run_daily.ps1               │
                │  (5-stage pipeline orchestrator)     │
                └───────────────┬──────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                       ▼
  ┌──────────┐           ┌──────────┐           ┌──────────┐
  │ Stage 1  │           │ Stage 2  │           │ Stage 3  │
  │ yfinance │           │  FinMind │           │   News   │
  │  batch   │           │  batch   │           │  batch   │
  └────┬─────┘           └────┬─────┘           └────┬─────┘
       │                      │                      │
       ▼                      ▼                      ▼
  ┌─────────────────────────────────────────────────────────┐
  │  cache_manager.py — disk-based TTL cache                │
  │  ~/.cache_manager/{yfinance,finmind_pe,finmind_div,...} │
  └────────────────────────────┬────────────────────────────┘
                                │
                                ▼
  ┌──────────────────────────────────────┐
  │  Stage 4: cross_source_runner        │
  │  (assemble + verify)                 │
  └───────────────┬──────────────────────┘
                  │
                  ▼
  ┌──────────────────────────────────────┐
  │  Stage 5: render_ticker_full         │
  │  (1,962 × 17-tab HTML)               │
  └───────────────┬──────────────────────┘
                  │
        ┌─────────┼─────────┐
        ▼         ▼         ▼
   ┌────────┐ ┌────────┐ ┌────────────┐
   │GitHub  │ │groove- │ │  Groove-   │
   │ Pages  │ │lab.dev │ │  Lab local │
   └────────┘ └────────┘ └────────────┘
```

---

## 資料源優先序

```
1. MySQL tw_elec  (主倉儲，必須先查)
2. yfinance        (補估值、即時價)
3. FinMind         (補 PE/div/fin/month/news)
4. FinLab          (只 2018-Q3 之前，幾乎不用)
```

每次 fetch 都有 cache，cache TTL：
| 資料 | TTL | 理由 |
|---|---|---|
| yfinance quote | 1d | 每日收盤後更新 |
| FinMind PE | 1d | 每日更新 |
| FinMind ROE | 7d | 季報出來才動 |
| FinMind 月營收 | 30d | 每月初更新 |
| FinMind 配息 | 30d | 除息後更新 |
| FinMind 季報 | 30d | 季報後更新 |
| 公司基本資料 | 30d | 變動少 |

---

## 5-stage Pipeline 細節

### Stage 1: yfinance batch
- 1,962 隻 ticker × yf.Ticker
- 抓 quote + info（含 PE、PB、殖利率、ROE、市值）
- 寫到 cache：`~/.cache_manager/yfinance/<TICKER>.json`
- 失敗 fail-fast（連續 30 隻 fail → 停）

### Stage 2: FinMind batch
- 4 datasets × 1,962 隻
  - `TaiwanStockPER` (PE)
  - `TaiwanStockDividend` (配息)
  - `TaiwanStockFinancialStatements` (季報)
  - `TaiwanStockMonthRevenue` (月營收)
- 1.05s / call 限速
- fail-fast per-dataset（30 隻 fail → 跳該 dataset）

### Stage 3: FinMind news
- watchlist 24 隻（其他 ticker 用 DB `stock_news`）
- 4h 新聞
- fail-fast（20 隻 fail → 停）

### Stage 4: cross_source assemble
- 每隻 ticker 組裝 dict：
  ```python
  {
    "ticker": "2330",
    "company_name": "台積電",
    "industry": "半導體業",
    "yfinance": {...},
    "valuation": {"pe": 28.5, "pb": 6.2, "dividend_yield": 1.5, "market_cap": ...},
    "monthly_revenue": [...],
    "dividends": [...],
    "fundamentals": [...],
    "news": [...],
    "_meta": {"sources": ["db", "yfinance", "finmind_pe"]}
  }
  ```
- verify 階段比對 yfinance PE vs FinMind PE，差 > 20% 寫 `_debug/cross_verify.jsonl`

### Stage 5: render
- 1,962 × `render_ticker_tabbed()`
- 17 tabs + Chart.js
- 8 workers parallel
- 預計 ~50 分鐘

---

## 17 Tabs 結構

```
PRIMARY (主頁籤列):
  zen / tech / val / inst / margin / fin / roe / rev / div / news / obs

SECONDARY (分隔線右側):
  minerva / thesis / backtest / trader / experts / info / price
```

每個 tab 是一個 `section_xxx(ticker, data, db_latest)` 函式：
- 輸入：`data` (cross_source dict), `db_latest` (DB 最新一天 row)
- 輸出：HTML 字串（不要 markdown，要 HTML 卡片式）

URL hash 記憶：URL 用 `#inst` 進入直接定位 tab。

---

## 法人 tab 視覺結構（重點）

```
┌─────────────────────────────────────────────────┐
│  法人買賣超 (近 20 日)  Chart.js stacked bar   │
│  (紅 = 買超 / 綠 = 賣超)                       │
└─────────────────────────────────────────────────┘
        ┌──────────┬──────────┬──────────┐
        │ 5 日累計 │ 10 日累計│ 20 日累計│
        │ 合計 ... │ 合計 ... │ 合計 ... │
        │ 外資 ... │ 外資 ... │ 外資 ... │
        │ 投信 ... │ 投信 ... │ 投信 ... │
        │ 自營 ... │ 自營 ... │ 自營 ... │
        └──────────┴──────────┴──────────┘
┌──────────────────────────────────────────────────┐
│ 日期   外資(張)  投信(張)  自營(張)  合計(張)   │
│  08-14 ██+5,118   0     █+171    ███+5,289  │
│  08-13 █+3,590   0      +24     ██+3,615   │
│  08-12 ███-4,757 +7    █-214    ████-4,964  │
│  ...                                              │
└──────────────────────────────────────────────────┘
   圖例: ■ 買超 · ■ 賣超 · 資料來源 MySQL
```

每個 cell 內嵌小色塊（bar 寬度 = 該日合計相對最大絕對值的比例）。
合計欄有 amber 背景高亮。
大買/大賣日（>60% 最大絕對值）整列背景 highlight。

---

## 觀察重點 tab 視覺結構

5 張卡片網格（auto-fit minmax(260px, 1fr)）：

```
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ 動能     │ │ 法人     │ │ 估值     │ │ 品質     │
│  🔥      │ │  💰      │ │  💎      │ │  🏆      │
│ 70       │ │ +5,118   │ │ 28.5     │ │ 22.3%    │
│ RSI 過熱 │ │ 外資買超 │ │ PE 偏高  │ │ ROE 優異 │
│ 白話...  │ │ 白話...  │ │ 白話...  │ │ 白話...  │
└──────────┘ └──────────┘ └──────────┘ └──────────┘
┌──────────┐
│ 營收     │
│  🚀      │
│ +44.7%   │
│ 月營收高速│
│ 白話...  │
└──────────┘
```

每張卡左邊色條按情緒編碼（紅=正面、綠=負面、灰=中性）。

---

## 部署

```
C:\Groove-Lab\
├── analyze.html        ← 入口
├── watchlist.html      ← 24 檔精選
├── index.html
└── analyze\
    ├── patterns.html
    ├── 2330.html       ← 1,962 個
    ├── 8039.html
    └── ...

發佈:
  1. GitHub Pages → walterLiu168/stock-report/
  2. groovelab.dev   → 直接 file serve
  3. Cloudflared     → outbound 被擋，不用
```
