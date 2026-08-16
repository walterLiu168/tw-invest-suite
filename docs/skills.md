# Skills — 14 個協作 skill 怎麼互動

本專案是 meta-skill，包了 14 個專門 skill 一起工作。

## 總覽

```
                        ┌─────────────────┐
                        │  tw-invest-suite │  ← 本專案（meta-orchestrator）
                        └────────┬────────┘
                                 │
        ┌────────┬────────┬──────┴──────┬────────┬────────┐
        ▼        ▼        ▼             ▼        ▼        ▼
    [data]   [analysis] [rendering] [signals]  [ui]   [publish]
```

---

## 1️⃣ Data Layer（資料層）

### `twse-api` (TWSE OpenAPI)
- 抓每日收盤 OHLCV
- 三大法人買賣超
- 融資融券
- 上市/上櫃基本資料
- **頻率**：每日 14:00 後（盤後）
- **MySQL 倉儲**：`tw_elec.daily_data2_full`

### `finmind`
- PE ratio (TaiwanStockPER)
- 配息 (TaiwanStockDividend)
- 季報 (TaiwanStockFinancialStatements)
- 月營收 (TaiwanStockMonthRevenue)
- 新聞 (TaiwanStockNews)
- **頻率**：每日 batch
- **rate limit**：1.05s/call = 57/min
- **sponsor tier**：6,000/hr 但 anti-abuse 敏感

### `yahoo-finance`
- 即時報價
- 估值（PE/PB/dividend yield/marketCap）
- ROE
- 52 週高低
- **無 quota limit**（偶爾被限流）
- **cache**：1 天

### `finlab` ⚠️
- **不再使用** — 只到 2018-Q3
- 歷史回測用，不在 daily 跑

---

## 2️⃣ Analysis Layer（分析層）

### `zen` (纏論)
- 結構：分型、筆、線段、中樞
- 訊號：買點、賣點、失效條件
- 位置：偏多/偏空
- **輸入**：DB 歷史 OHLCV (120 日)
- **輸出**：`ZenRead` 物件

### `minerva`
- 量化評分
- 多策略：趨勢 / RSI / 法人 / 籌碼
- 進出場訊號
- **輸入**：DB 歷史 + 即時報價
- **輸出**：score + signals

### `wall-street-tw-stock-analysis`
- 華爾街視角技術分析
- 中長期趨勢判斷
- 補主視角

### `hedge-fund-expert-team`
- 18 位大師框架：
  - 12 投資大師：巴菲特、芒格、葛拉漢、林奇、達摩達蘭、伯里、伍德、阿克曼、德魯肯米勒、費雪、帕布萊、鈕亨沃拉
  - 4 專業分析師：估值、情緒、基本面、技術
  - 2 管理專家：風險管理、組合管理
- **輸出**：每隻 ticker 4-line 視角（標籤/視角/關鍵數據/白話意思）

### `stock-selection-decision`
- 選股決策框架
- 4 價位 bucket（small/mid/large/mega）
- 每 bucket 3 long + 3 short = 24 檔

---

## 3️⃣ Rendering Layer（渲染層）

### `ui`
- UI 設計規範
- 17 tab 元件
- Chart.js 整合
- 顏色台灣慣例

### `ticker-dashboard`
- 個股 dashboard 視覺
- 整合 17 tab 渲染

### `tw-stock-info`
- 個股基本資料視覺
- 整合在公司基本 tab

---

## 4️⃣ Signal Layer（訊號層）

### `tw-futures-options`
- 衍生性商品數據
- Backtest 因子驗證
- 3 策略：MA trend / RSI / Foreign 3-day

### `ai-telegram-research-check`
- 推播研究結果
- Telegram 整合（可選）

---

## 5️⃣ Publish Layer（發佈層）

### 自建 publish script
- `publish_analyze_ghpages.py` → GitHub Pages
- `publish_groovelab.py` → groovelab.dev

---

## Skill 互動流程

```
1. 22:25  Task Scheduler 觸發 run_daily.ps1
2. ↓ 依序跑 batch_yfinance / batch_finmind / batch_finmind_news
3. ↓ 寫到 cache (~/.cache_manager/)
4. ↓ cross_source_runner.assemble() 組合
5. ↓ render_ticker_tabbed() 跑 17 個 section
6.   - section_zen() → zen skill
7.   - section_valuation() → yfinance + finmind
8.   - section_observations() → 5 維度 auto
9.   - section_expert_views() → hedge-fund-expert-team
10.   - section_minerva() → minerva skill
11.   - section_backtest() → tw-futures-options
12. ↓ publish_analyze_ghpages.py
13. ↓ 推 GitHub Pages + groovelab.dev
```

---

## 何時不要用某個 skill

- 周末 → 跳過 batch_yfinance / batch_finmind（沒新資料）
- 重新 render → 跳過 batch，只用 cache（`--no-yfinance --no-news`）
- 急產出 → 用 `render_only.py`（cache-only mode）
- 個別 ticker debug → 用 `render_ticker_full.py <TICKER> tabbed`
