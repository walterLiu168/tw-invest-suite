# tw-invest-suite

> 🇹🇼 Taiwan Stock Market 全市場分析套件 — 1,962 檔個股 × 14 種 skill × 18 位大師觀點

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org)
[![Daily Update](https://img.shields.io/badge/daily-22:25_TW-brightgreen.svg)](docs/schedule.md)
[![Live Site](https://img.shields.io/badge/live-groovelab.dev-blueviolet.svg)](https://groovelab.dev/analyze.html)

每日 22:25 自動跑完全市場 1,962 檔台股的 cross-source 數據蒐集 → 渲染 → 發佈，產出
- 全市場個股分析頁（17 個 tab + Chart.js + 18 大師解讀）
- Watchlist 24 檔精選（含每日 4h 新聞）
- 8 種型態 240 日 walk-forward 回測

---

## 🎯 這是什麼

`tw-invest-suite` 是一個把「台股個股分析」這件事全部自動化的開源工具鏈：

1. **抓資料**：MySQL `tw_elec` 倉儲（主） + yfinance + FinMind（sponsor tier）+ 驗證
2. **算訊號**：技術指標、纏論結構、法人籌碼、估值、ROE、月營收、配息、新聞
3. **產頁面**：1,962 個獨立 HTML（單頁 17 個 tab）+ watchlist + patterns dashboard
4. **選股**：每日 4 個價位 bucket × 3 long + 3 short = 24 檔精選
5. **大師解讀**：18 位投資大師 / 分析師 / 管理專家視角
6. **型態辨識**：8 種型態 + 240 日 walk-forward 回測
7. **發佈**：GitHub Pages + groovelab.dev

---

## 📁 結構

```
tw-invest-suite/
├── README.md                  ← 你正在看
├── AGENTS.md                  ← 給 agent 讀的入口
├── LICENSE                    ← MIT
├── docs/
│   ├── architecture.md        ← 系統架構圖、資料流
│   ├── decision-log.md        ← 重要決策紀錄（含為何這樣選）
│   ├── data-schema.md         ← MySQL / cache 欄位定義
│   ├── skills.md              ← 14 個 skill 怎麼協作
│   └── schedule.md            ← 每日 22:25 排程設定
├── scripts/                   ← 每日 batch pipeline
│   ├── run_daily.ps1          ← 主入口（5 stage pipeline）
│   ├── batch_yfinance_only.py ← yfinance 1,962 檔
│   ├── batch_finmind_only.py  ← FinMind PE/div/fin/month
│   ├── batch_finmind_news.py  ← FinMind 新聞
│   ├── cross_source_runner.py ← cross-source data assembler
│   ├── cache_manager.py       ← disk-based TTL cache
│   ├── db_client.py           ← MySQL context manager
│   ├── render_ticker_full.py  ← 17-tab HTML renderer
│   ├── render_only.py         ← cache-only fast batch
│   ├── daily_full_tickers.py  ← 主 daily pipeline
│   ├── pattern_classifier.py  ← 8 型態偵測
│   ├── build_patterns_html.py ← 型態 dashboard 產生
│   ├── publish_analyze_ghpages.py ← GitHub Pages push
│   ├── render_full_watchlist.py    ← watchlist.html
│   └── ...
├── public/                    ← 靜態網站（部署用）
│   ├── analyze.html           ← ticker 搜尋
│   ├── watchlist.html         ← 24 檔精選 + 型態搜尋按鈕
│   ├── index.html
│   └── analyze/               ← 1,962 個 ticker HTML
│       ├── 2330.html
│       ├── 8039.html
│       └── patterns.html
├── src/                       ← LLM/ML 程式碼（Phase 2+）
│   ├── commentary/            ← LLM 每日 commentary
│   └── ml/                    ← LSTM/XGBoost 預測
├── tests/                     ← 單元測試
├── data/                      ← schema docs, sample CSV
└── outputs/                   ← 本地輸出（gitignored）
```

---

## 🚀 快速開始

### 環境需求
- Windows 10/11 + PowerShell 5.1+
- Python 3.10+（建議 3.11）
- MySQL 8.0（`tw_elec` 資料庫）
- Node 24+（非必要，部署用）
- FinMind sponsor token（`~/.finmind_token`）

### 安裝
```powershell
git clone https://github.com/walterLiu168/tw-invest-suite
cd tw-invest-suite
pip install pymysql yfinance requests pandas
# 設定 FinMind token
echo "YOUR_TOKEN" > ~\.finmind_token
```

### 每日 batch
```powershell
.\scripts\run_daily.ps1                      # 全跑
.\scripts\run_daily.ps1 -Mode render         # 只重 render（用 cache）
.\scripts\run_daily.ps1 -SkipYfinance        # 跳過 yfinance（週末）
.\scripts\run_daily.ps1 -Force               # 強制重跑
```

### 單檔 render
```powershell
python scripts\render_ticker_full.py 2330 tabbed
# → C:\Groove-Lab\analyze\2330.html
```

---

## 📊 17 個 tab 是什麼

| # | Tab | Skill | 資料源 |
|---|---|---|---|
| 1 | 🧘 纏論 (Chanlun) | zen | DB + zen engine |
| 2 | 📊 技術分析 | tw-stock-info | yfinance + DB |
| 3 | 💎 估值 (雙源驗證) | twse + finmind | yfinance + FinMind PE |
| 4 | 🏛 法人 (近 20 日) | twse-api | MySQL `daily_data2_full` |
| 5 | 💴 融資融券 (近 30 日) | twse-api | MySQL `daily_data2_full` |
| 6 | 📊 季報 (FinMind) | finmind | FinMind `FinancialStatements` |
| 7 | 🧬 ROE | finlab + finmind | yfinance TTM + FinMind quarterly |
| 8 | 📈 月營收 (FinMind) | finmind | FinMind `MonthRevenue` |
| 9 | 💵 配息歷史 | finmind | FinMind `Dividend` |
| 10 | 📰 新聞 (DB) | — | MySQL `stock_news` |
| 11 | 💡 觀察重點 | — | 5 維度 auto-generated |
| 12 | 🧮 Minerva 量化評分 | minerva | scoring engine |
| 13 | 🎯 Build-Thesis 多空 | build-thesis | LLM 框架 |
| 14 | 📊 Backtest 因子驗證 | tw-futures-options | 3 策略 walk-forward |
| 15 | 💹 TraderHub 進出場 | minerva | entry/exit signals |
| 16 | 🧠 18 大師解讀 | hedge-fund-expert-team | 12 大師 + 4 分析師 + 2 管理 |
| 17 | 💰 即時價格 | yahoo-finance | yfinance quote |

---

## 🛠 14 個協作 skill

| Skill | 角色 |
|---|---|
| `tw-invest-suite` | 總入口（本專案） |
| `hedge-fund-expert-team` | 18 位大師框架 |
| `zen` | 纏論結構分析 |
| `yahoo-finance` | 即時報價、估值 |
| `tw-stock-info` | 個股基本資料 |
| `finmind` | PE/div/fin/month/news |
| `twse-api` | 三大法人、融資融券 |
| `minerva` | 量化評分 |
| `wall-street-tw-stock-analysis` | 華爾街視角 |
| `ticker-dashboard` | 個股 dashboard |
| `ai-telegram-research-check` | 推播研究 |
| `stock-selection-decision` | 選股決策 |
| `ui` | UI 設計 |
| `tw-futures-options` | 衍生性商品 |

詳見 [docs/skills.md](docs/skills.md)

---

## 🌐 線上展示

- 🔍 個股搜尋：<https://groovelab.dev/analyze.html>
- 📊 Watchlist 24 檔：<https://groovelab.dev/watchlist.html>
- 🎛 型態 dashboard：<https://groovelab.dev/analyze/patterns.html>
- 📈 個股範例（台積電）：<https://groovelab.dev/analyze/2330.html>
- 📈 個股範例（台虹）：<https://groovelab.dev/analyze/8039.html>
- 🌐 GitHub Pages：<https://walterLiu168.github.io/stock-report/analyze/>

---

## 📜 License

MIT — 詳見 [LICENSE](LICENSE)

---

## 🙏 致謝

- [FinMind](https://finmindtrade.com/) — sponsor tier API access
- [yfinance](https://github.com/ranaroussi/yfinance) — 即時報價
- [MySQL](https://www.mysql.com/) — 倉儲
- 18 位投資大師的智慧（巴菲特、芒格、林奇、達摩達蘭⋯⋯）
