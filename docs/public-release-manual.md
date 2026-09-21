# tw-invest-suite 公開使用與發布手冊

版本：2026-09-21
產品：Taiwan stock daily research and report site
公開輸出：GitHub Pages、Groove site、Telegram daily brief

## 1. 產品用途

tw-invest-suite 會把台股收盤資料、法人流量、融資融券、估值、營收、基本面、新聞與選股結果整理成可閱讀的單股頁、全市場報告與每日籌碼摘要。輸出是研究工具，不是自動下單系統，也不提供個人化投資建議。

## 2. 公開使用者入口

GitHub Pages canonical site：`https://walterliu168.github.io/tw-invest-suite/`
Groove site：`https://groovelab.dev/`

主要頁面：

| 路徑 | 內容 |
|---|---|
| `index.html` | 公開首頁與導覽 |
| `analyze/index.html` | 單股研究入口 |
| `analyze/<ticker>.html` | 單股 17/18 tab 深度頁 |
| `watchlist.html` | 當日選股與 watchlist |
| `patterns.html` | 型態分類與統計 |
| `chips.html` | 基礎籌碼摘要 |
| `chips-advanced.html` | 進階籌碼與 20 日特徵 |
| `chips-history.html` | 30 個交易日歷史 |
| `sectors.html` | 產業彙總 |
| `concepts.html` | 概念股彙總 |
| `market-screen-YYYY-MM-DD.html/.md` | 當日市場篩選報告 |
| `data/dashboard.md` | 認證、發布與健康狀態 |

## 3. 如何閱讀單股頁

單股頁由 `scripts/render_ticker_full.py` 產生。資訊依序分成公司、價格、技術、估值、法人、融資融券、財務、ROE、營收、股利、新聞、觀察、Minerva、thesis、backtest、trader、experts、info、price 等 tab。頁面中的：

- 成交量、法人流量以「股」儲存，畫面通常換算成「張」；融資與融券餘額本身已是張。
- 台灣市場顏色慣例為紅漲、綠跌。
- 缺值顯示 unavailable 或來源警告，不得視為零。
- 20/60/120/240/500 日報酬與 pattern 的 20 日交易觀測窗口不同，請看頁面標籤與 Design Book 的語意定義。

## 4. 每日自動發布流程

```text
資料落地 -> 日期/交易日確認 -> valuation + FinMind maintenance
-> market screen -> finalize_inputs -> render
-> patterns -> patterns_html -> optional margin_scan
-> watchlist -> all_reports -> certification marker
-> GitHub remote SHA verify -> Groove remote SHA verify
-> postflight -> Telegram chips summary
```

只有 `pipeline_state.py complete` 產生的同一個 certified marker 才能被 publisher 消費。API 回應正常、Scheduler 顯示 Done、或本機 HTML 存在，都不足以宣稱發布完成。

## 5. 公開使用者看到的報告限制

- 報告使用最新已落地的 TWSE/TPEx 交易日；週末 catch-up 只在資料已落地且日期契約成立時執行。
- pattern forward return 需要完整持有窗口；沒有資料時顯示 unavailable。
- margin scan 是 optional/degraded stage；它失敗不會偽造成功，也不應被解讀為全市場風險消失。
- 估值與 proxy 必須標示來源日期；proxy 不是實際法人交易 VWAP 或持倉成本。
- 這套系統沒有券商下單、交易授權或保證獲利功能。

## 6. 公開發布者快速流程

在 canonical repo 執行前先確認工作樹狀態與認證 marker。正常的 scheduled publisher 入口是：

```powershell
Start-ScheduledTask -TaskName 'tw-invest-suite-publish'
```

手動 prepare-only（不推送）用於驗收：

```powershell
powershell.exe -NoProfile -File .\scripts\publish_ghpages_daily.ps1 -PrepareOnly
```

正式發布由 `scripts/publish_verified_sites.ps1` 串接 GitHub、Groove、Telegram；不要直接執行舊的 `publish_html*.py` 來宣稱 canonical release。

## 7. 使用者回報問題時要提供的資料

請提供：頁面 URL、ticker、顯示日期、頁面路徑、錯誤文字與本機 dashboard 上的 `nightly_id`/`data_date`。不要提供 token、密碼、cookies 或整份私人 config。

## 8. 公開 source 與私人自動化的邊界

GitHub source release 只包含程式、文件、依賴清單與不含秘密的設定範本。AI-Telegram/OpenAlice 是選用的私人整合層；它透過 `AI_TELEGRAM_*` environment overrides 取得 DB、Telegram、FinMind 與 LLM 設定，不應把 `shared_config.local.json` 或 bot token 複製到公開 repo。

MySQL schema、來源授權、API rate limit 與第三方 notices 見 [data schema](data-schema.md) 與 [third-party notices](third-party-notices.md)。
