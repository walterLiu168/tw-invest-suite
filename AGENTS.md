# AGENTS.md — 給 agent 讀的工作手冊

> 此檔案遵循 [agents.md](https://agents.md/) 規範，供 OpenCode/Codex/Cursor/Aider/Devin/Gemini CLI 等 agent 自動載入。

## 專案範圍

`tw-invest-suite` — 每日 22:25 自動跑全台股 1,962 檔的 cross-source 分析、rendering、發佈。

**IN 範圍：**
- 從 MySQL `tw_elec` 倉儲（主） + yfinance + FinMind 抓資料
- 渲染 17-tab HTML 個股頁
- 篩選 24 檔 watchlist（4 價位 bucket × 3 long + 3 short）
- 8 種技術型態偵測 + 240 日 walk-forward 回測
- 發佈到 GitHub Pages + groovelab.dev

**OUT 範圍：**
- 個股下單 / 交易
- 投資建議（免責聲明已寫入每頁）
- 衍生性商品即時報價

---

## 環境

- OS: Windows 11 + PowerShell 5.1
- Python: 3.11（建議）/ 3.10/3.13/3.14 都有
- MySQL: 8.0 at `localhost:3306` / `root` / `1234` / `tw_elec`
- GPU: NVIDIA RTX 3060 Ti 8GB（目前未用，未來 ML 用）

---

## 重要約定（必須遵守）

### 1. DB-first
**永遠先讀 MySQL，沒資料才打 API。**
- `daily_data2_full` 涵蓋 OHLCV + 三大法人 + 融資融券（20 年+）
- `stock_news` 2.3M 筆新聞
- DB 欄位都是 snake_case

### 2. 週末規則
**週六日不抓資料，只 render + publish。**
- 因為 FinMind 沒新資料，浪費 quota
- 邏輯在 `run_daily.ps1` 的 `Is-Weekend()`

### 3. 週末渲染資料源
**週末渲染用「上週五」收盤為最新。**
- 例如週六渲染 → 顯示 8/14（五）收盤
- DB 自動 fallback 到 last trading day

### 4. FinMind rate limit
**1.05 秒 / call = 57/min = 3,420/hr**（安全遠低於 sponsor 6,000/hr，但觸發 anti-abuse 會 ban IP）
- 1,962 隻全跑約 35 分鐘（每隻 4 datasets）
- 不要並行

### 5. Cache 策略
**disk-based TTL cache**（`~/.cache_manager/`）
- PE: 1d
- ROE: 7-30d
- 月營收: 30d
- 配息: 30d
- 公司資料: 30d
- yfinance quote: 1d

### 6. 體積單位
**全部用「張」(1,000 股)，不要用「股」**

### 7. 顏色台灣慣例
**紅色 = 上漲 / 綠色 = 下跌**（與美股相反）
- CSS 變數 `--red: #ec7063` / `--green: #58d68d`
- 在 `render_ticker_html.py` 的 `:root` swap
- **不要**用 `--red` 表示負值

### 8. 殖利率格式
- yfinance 兩種格式都會回傳：> 0.5 視為百分比（如 1.5 = 1.5%），< 0.5 視為小數（如 0.015 = 1.5%）
- 顯示一律 `1.00%` 格式（不要 100%）

### 9. 語言
**全部用繁體中文**，標點用「／」不是「/」

---

## 指令速查

### 每日 batch
```powershell
# 全跑
.\scripts\run_daily.ps1

# 模式
.\scripts\run_daily.ps1 -Mode render      # 只重 render（cache-only）
.\scripts\run_daily.ps1 -Mode publish     # 只發佈
.\scripts\run_daily.ps1 -Force            # 強制（即使週末也跑）
.\scripts\run_daily.ps1 -SkipYfinance     # 跳 yfinance
.\scripts\run_daily.ps1 -SkipFinmind      # 跳 FinMind
.\scripts\run_daily.ps1 -TimeoutMin 240   # 4 小時 timeout
```

### 單檔 render
```powershell
python scripts\render_ticker_full.py <TICKER> tabbed
python scripts\render_ticker_full.py <TICKER> full    # 舊版（保留 fallback）
```

### 單 dataset
```powershell
python scripts\batch_yfinance_only.py
python scripts\batch_finmind_only.py --fail-threshold 30
python scripts\batch_finmind_news.py --fail-threshold 20
```

### 排程狀態
```powershell
.\scripts\daily_status_check.ps1
Get-ScheduledTask -TaskName "tw-invest-suite-daily"
```

---

## 必讀文件

按優先順序：
1. `docs/architecture.md` — 系統架構 + 資料流
2. `docs/data-schema.md` — DB / cache 欄位
3. `docs/decision-log.md` — 為何這樣選（避免重新發明輪子）
4. `docs/skills.md` — 14 個 skill 怎麼協作
5. `docs/schedule.md` — 22:25 排程設定

---

## 不要做的事

1. **不要**把所有 1,962 個 HTML commit 進 git（用 `.gitignore` 排除）
2. **不要**用 FinLab 的 `data` API（只到 2018-Q3，已死）
3. **不要**用 Cloudflared tunnel（outbound 被擋）
4. **不要**每次都打 FinMind API（cache 優先）
5. **不要**用 `Remove-Item` 刪檔（會被擋），改 `Move-Item` 到 `_debug/`
6. **不要**改 `:root` 的 `--red`/`--green` selector（會反轉顏色意義）
7. **不要**用 bash 跑 > 30 min 的 batch（會 timeout），改用 `render_chunk.py` 拆 4 chunks 並行
8. **不要**用 `pip install` 一次裝太多 ML package，預設只裝 xgboost + scikit-learn
9. **不要**用 LLM commentary 沒設 API key 跑（會 401），先 `--dry-run` 驗 prompt

---

## 待辦與 Roadmap

詳見 `TODO.md` 與 [docs/decision-log.md](docs/decision-log.md)
