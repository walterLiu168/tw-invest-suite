# tw-invest-suite Daily Pipeline — Full Reference

**Last updated**: 2026-09-15 (D056-A Option A)
**Owner**: Walter Liu (walterLiu168)
**Path convention**:
- **Git repo** = `C:\Users\icemo\Projects\tw-invest-suite\`
- **Runtime scripts** = `C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\`
- 兩邊會 sync（postflight_daily.py 等關鍵檔案 SHA 一致）

---

## 1. Schedule (cron order)

| 時間 | Cron 名稱 | 動作 (Command) | 主要 Python 檔 |
|---|---|---|---|
| **17:35 / 17:45 / 17:55** | OpenAlice Daily OHLCV | `openalice_phased_download.cmd price` | (D:\CODEX\AI-Telegram 內部 scripts) |
| **18:10** | `tw-invest-suite-metadata-backfill` | `metadata_backfill_daily.ps1` | `metadata_backfill.py` |
| **18:20** | `tw-invest-suite-market-screen` | `market_screen_daily.ps1` | `market_screen_runner.py` → `market_screen.py` |
| **22:25** | `tw-invest-suite-daily-report` | `run_daily.ps1` | 5 stages（見 §3） |
| **22:30** | `tw-invest-suite-yfinance` | `yfinance_daily.ps1` | `yfinance_daily.py` |
| **23:00** | `tw-invest-suite-health-check` | `check_openalice_health.py --json` | `check_openalice_health.py` |
| **23:25** | `tw-invest-suite-company-refresh` | `company_refresh_daily.ps1` | `company_refresh.py` |
| **23:30** | `tw-invest-suite-sync-legacy` | `sync_legacy_tables_runner.ps1` | `sync_legacy_tables.py` |
| **23:55** | `tw-invest-suite-marker-watchdog` | `marker_watchdog_daily.ps1` | `_debug/marker_watchdog.py` |
| **00:05** | `tw-invest-suite-postflight` | `postflight_daily.ps1` | `postflight_daily.py` + `_debug/build_dashboard.py` |
| **00:30** | `tw-invest-suite-publish` | `publish_ghpages_daily.ps1` | `publish_manifest.py` + publish |

> **D056-A**: `run_daily.ps1` 從 17 stages 砍到 5 + 1 optional。
> D027/D029 進階 stages 7-17 改為 `-IncludeAdvancedStages` opt-in。

---

## 2. Pipeline flow (ASCII)

```
17:35+17:55 OpenAlice OHLCV
    │  (D:\CODEX\AI-Telegram\automation\openalice_phased_download.cmd price)
    ▼
18:10 metadata-backfill ─── 補 daily_data2_full 缺的 ticker metadata
    │
    ▼
18:20 market-screen ──── 跑 screener，寫 24 picks (4 buckets × 6)
    │
    ▼
22:25 daily-report ────── yfinance + FinMind + render + patterns + watchlist
    │                       (run_daily.ps1 — 5 stages, ~3-4h)
    │
    ├─ Stage 1: yfinance batch (1,962 tickers, ~30-50 min)
    ├─ Stage 2: FinMind PE/Div/Fin/Month (~2-3 hours)
    ├─ Stage 3: FinMind news (~22 min)
    ├─ Stage 4: Render HTML (1,962 pages, ~30-50 min)
    ├─ Stage 5: Pattern classifier + backtest (~10 min)
    └─ Stage 6: Margin rebound scan (OPTIONAL, degraded if fail)
    │
    ▼
22:30 yfinance (單獨 cron，補 Stage 1 沒抓到的)
    │
    ▼
23:00 health-check ───── 自檢 DB + cron state
    │
    ▼
23:25 company-refresh ── refresh daily_data2_full.company (from industry_type)
    │
    ▼
23:30 sync-legacy ────── daily_data2_full → 4 legacy tables
    │
    ▼
23:55 marker-watchdog ── 自動修補 completion marker (如果 22:25 失敗)
    │
    ▼
00:05 postflight ─────── 8 個 cron + 5 個 DB invariant 檢查
    │                    + 寫 daily_summary_YYYY-MM-DD.md
    │                    + 寫 dashboard.md (NEW: D056-A)
    │
    ▼
00:30 publish ────────── public/ → gh-pages branch (GitHub Pages)
                         + 先 build publish_manifest_YYYY-MM-DD.json
```

---

## 3. `run_daily.ps1` 22:25 內部 5 stages（細節）

| # | Stage Name | Python 指令 | Timeout | 產出 | Optional |
|---|---|---|---|---|---|
| 1 | `finmind_maint` | `src\margin_rebound\finmind_maint.py` | 10 min | `finmind_taiwan_margin_maintenance` | No |
| 2 | `render` | `render_only.py --no-yfinance --no-news` | 180 min | `public/analyze/<ticker>.html` (1,962 份) | No |
| 3 | `patterns` | `pattern_classifier.py` | 30 min | `public/data/patterns.json` | No |
| 4 | `patterns_html` | `build_patterns_html.py` | 10 min | `public/patterns.html` | No |
| 5 | `margin_scan` | `src\margin_rebound\scan.py --threshold 0 --out outputs\margin_rebound\<today>.json` | 30 min | `outputs/margin_rebound/<today>.json` | **Yes** |
| 6 | `watchlist` | `render_full_watchlist.py` | 10 min | `public/watchlist.html` + `public/data/watchlist-full.json` | No |

> **Stages 7-17 砍掉** (D027/D029 進階: sector aggregate, chips per-bucket, og.png 等)。
> 手動 opt-in: `powershell run_daily.ps1 -IncludeAdvancedStages`

---

## 4. File-by-file 用途

### 4.1 Scripts/ 主要 .py（執行順序）

#### **`market_screen_runner.py`** (D052h-fixup4)
- **觸發**: 18:20 cron → `market_screen_daily.ps1`
- **目的**: 跑 screener，寫 `market_screen_runs` + `market_screen_picks`
- **邏輯**: 跳週末 → 確認 `daily_data2_full` 最新日期 → 驗證 24 picks (4 buckets × 6) → 長短多空各 6 → 寫 DB
- **產出**: DB row in `market_screen_runs` (id, run_date, picks_count) + 24 rows in `market_screen_picks`

#### **`metadata_backfill.py`** (D052c)
- **觸發**: 18:10 cron → `metadata_backfill_daily.ps1`
- **目的**: 把 `daily_data2_full` 有但 `industry_type` 沒有的新上市 ticker 補進去
- **邏輯**: diff 兩個 table → 對缺的 ticker 從 FinMind TaiwanStockInfo 抓 metadata → stage-and-promote（不會直接覆蓋既有資料）
- **產出**: 新 rows in `industry_type`

#### **`yfinance_daily.py`** (D047)
- **觸發**: 22:30 cron → `yfinance_daily.ps1`
- **目的**: 抓 1,962 tickers 的 yfinance `.info` (PE/PB/div yield/market cap)
- **邏輯**: 透過 `cache_manager.py` (TTL 1d)，DEAD yfinance 時回傳 rc=2
- **產出**: cache 寫到 `_cache/yfinance/`，下一步 `render_only.py` 會讀

#### **`run_daily.ps1`** (D023 + D056 + D056-A)
- **觸發**: 22:25 cron
- **目的**: orchestrator — 跑 5 stages + 1 optional（見 §3）
- **邏輯**: health check → DB status → 週末 auto-skip 下載 → 跑 stages → 寫 completion marker (`_debug/last_completed.json`)
- **產出**: `public/*.html`, `public/data/*.json`, `_debug/last_completed.json`, `_debug/daily_run_<date>.log`

#### **`render_only.py`** (Stage 4 of run_daily)
- **觸發**: 22:25 run_daily → Stage 2
- **目的**: 為 1,962 tickers 各產生一份 HTML
- **邏輯**: 讀 DB + cache + FinMind fallback → render 完整分析頁
- **產出**: `public/analyze/<ticker>.html` (約 1,962 份)

#### **`pattern_classifier.py`** (Stage 3 of run_daily)
- **觸發**: 22:25 run_daily → Stage 3
- **目的**: 9 種技術型態分類 + 240d walk-forward backtest
- **產出**: `public/data/patterns.json`

#### **`build_patterns_html.py`** (Stage 4 of run_daily)
- **觸發**: 22:25 run_daily → Stage 4
- **目的**: 把 patterns.json 轉成瀏覽器頁面
- **產出**: `public/patterns.html`

#### **`render_full_watchlist.py`** (Stage 6 of run_daily)
- **觸發**: 22:25 run_daily → Stage 6
- **目的**: 把 24 picks 整理成 watchlist.html (含 18 大師詳視)
- **產出**: `public/watchlist.html`, `public/data/watchlist-full.json`

#### **`src/margin_rebound/finmind_maint.py`** (Stage 1 of run_daily)
- **觸發**: 22:25 run_daily → Stage 1
- **目的**: 抓 FinMind `TaiwanStockMarginMaintenance` (per-stock 維持率)
- **產出**: DB row in `finmind_taiwan_margin_maintenance`

#### **`src/margin_rebound/scan.py`** (Stage 5 of run_daily, optional)
- **觸發**: 22:25 run_daily → Stage 5
- **目的**: 7-dim scoring 對所有 maint<130% 候選
- **產出**: `outputs/margin_rebound/<today>.json`

#### **`company_refresh.py`** (D052f)
- **觸發**: 23:25 cron → `company_refresh_daily.ps1`
- **目的**: refresh `daily_data2_full.company` from `industry_type` 過去 7 天
- **產出**: DB update

#### **`sync_legacy_tables.py`** (D052h-fixup)
- **觸發**: 23:30 cron → `sync_legacy_tables_runner.ps1`
- **目的**: 把 `daily_data2_full` 最新一天 sync 到 4 個 legacy tables (daily_data, daily_data2, chip_daily 等)
- **產出**: 4 個 legacy table 更新

#### **`_debug/check_openalice_health.py`** (D052h-era)
- **觸發**: 23:00 cron (python 直接跑)
- **目的**: 自檢 DB + cron state，輸出 JSON
- **產出**: `_debug/check_openalice_health_<date>.log`, `_debug/hc_*.json`

#### **`_debug/marker_watchdog.py`** (D056 P2)
- **觸發**: 23:55 cron → `marker_watchdog_daily.ps1`
- **目的**: 如果 `_debug/last_completed.json` missing/stale (>36h 或 status≠ok)，從最新 `market_screen_runs` 重建 marker
- **Exit code**: 0=fresh, 1=regenerated, 2=no picks in DB, 3=invocation error
- **產出**: `_debug/last_completed.json` (regenerated if needed)

#### **`postflight_daily.py`** (D052h-fixup2 + D056-A)
- **觸發**: 00:05 cron → `postflight_daily.ps1`
- **目的**: 驗證 8 個 tw-invest-suite-* cron 跑了 + 5 個 DB invariant + 寫 daily_summary.md + 觸發 build_dashboard.py
- **邏輯**:
  - `check_market_screen`: 24 picks + 4 buckets of 6
  - `check_company_null`: daily_data2_full 當日 null company ≤ 5
  - `check_industry_count`: industry_type ≥ 1962
  - `check_quarantine`: metadata_quarantine open ≤ 10
  - `check_publish_artifact`: 找 publish log + "done (exit 0)" marker
  - `check_tasks`: Get-ScheduledTaskInfo + 對日期
- **產出**: `_debug/postflight_<date>.json`, `_debug/postflight_<date>.log`, daily_summary.md

#### **`daily_summary.py`** (D054 + D054-fixup)
- **觸發**: 00:05 postflight_daily.py 內部呼叫
- **目的**: 寫 closed-loop daily report (manifest + remote verify)
- **產出**:
  - `reports/daily_summary_YYYY-MM-DD.md`
  - `public/data/daily_summary_YYYY-MM-DD.md` (給 GH Pages)

#### **`_debug/build_dashboard.py`** (D056-A) ← NEW
- **觸發**: 00:05 postflight_daily.py 尾巴 call (subprocess)
- **目的**: 一頁式 dashboard，1 分鐘可讀完
- **邏輯**: DB 查 picks/marker/OHLCV + HEAD 6 個 GH Pages + Get-ScheduledTaskInfo 5 個 cron
- **產出**:
  - `reports/dashboard.md` (runtime)
  - `public/data/dashboard.md` (git, 給 GH Pages)
- **Exit code**: 0=green, 1=warning, 2=critical, 3=fatal

#### **`publish_manifest.py`** (D054 fixup)
- **觸發**: 00:30 publish_ghpages_daily.ps1 內部呼叫
- **目的**: build `publish_manifest_YYYY-MM-DD.json` 在 push 前
- **產出**: `public/data/publish_manifest_YYYY-MM-DD.json` (含 run_id, picks_count, OHLCV, cron status)

#### **`publish_ghpages_daily.ps1`** (D047 + D056 P0-3)
- **觸發**: 00:30 cron
- **目的**: push `public/` 到 `gh-pages` branch
- **邏輯**: 讀 `_debug/last_completed.json` 拿 data_date → build manifest → git checkout gh-pages → copy public/ → commit → push
- **產出**: GH Pages 更新 (`https://walterLiu168.github.io/tw-invest-suite/`)

### 4.2 共用 library（被以上檔案 import）

| 檔案 | 用途 |
|---|---|
| `db_client.py` | pymysql wrapper，所有 DB 存取走這 |
| `cache_manager.py` | yfinance/FinMind 結果的 disk cache (TTL) |
| `finmind_client.py` | FinMind REST API client |
| `yfinance_batch.py` | yfinance 批次抓 `.info` |
| `finmind_batch.py` | FinMind 批次抓 PE/Div/Fin/Month |
| `twse_client.py` | TWSE OpenAPI |
| `tpex_client.py` | TPEx OpenAPI |
| `cross_source_runner.py` | DB + yfinance + FinMind 三源驗證（D052 引入） |
| `watchlist.py` | watchlist builder (24 picks → HTML) |
| `zen_analyzer.py` | Chanlun/纏論 結構分析 |
| `pattern_classifier.py` | 9 patterns 分類器 |
| `market_screen.py` | 真正的 screener 邏輯 |
| `market_report.py`, `market_report_html.py` | 舊版 market report (mostly 取代) |
| `render_ticker_*.py` | 各種 ticker 渲染入口（DB only / full / html） |
| `finlab_client.py` | FinLab API (備援) |
| `deep_dive_prompts.py` | 18 大師 prompt 模板 |
| `analyze_stock.py` | 單支 stock 互動式分析 |

### 4.3 _debug/ scripts（runtime only, gitignored）

| 檔案 | 用途 |
|---|---|
| `marker_watchdog.py` | 23:55 自動補 marker |
| `build_dashboard.py` | 00:05 dashboard builder |
| `write_completion_marker.py` | 22:25 run_daily 結尾寫 `_debug/last_completed.json` |
| `run_stage.py` | PowerShell Run-Stage 的 Python wrapper（解 $p.ExitCode bug） |
| `check_openalice_health.py` | 23:00 health check |
| `verify_d056.ps1` | 13 項 D056 verify (D056 P0) |
| `last_completed.json` | completion marker（gitignored 但 runtime 重要狀態） |

---

## 5. Reports 產出清單

### 5.1 每日產出 (`public/data/`)
| 檔案 | 來源 stage | 用途 |
|---|---|---|
| `daily_summary_YYYY-MM-DD.md` | postflight → daily_summary.py | 給 ChatGPT PM 看的 closed-loop 報告 |
| `dashboard.md` | postflight → build_dashboard.py | **D056-A NEW** Walter 早上 1 分鐘讀 |
| `publish_manifest_YYYY-MM-DD.json` | publish_ghpages_daily.ps1 → publish_manifest.py | 該日 manifest (run_id, picks_count, cron state) |
| `patterns.json` | run_daily Stage 3 | 9 patterns 分類結果 |
| `chips.json`, `chips-advanced.json` | (D027/D029 進階 stage，-IncludeAdvancedStages 才跑) | chips 數據 |
| `chips-history/YYYY-MM-DD.json` | (同上) | 每日 chips snapshot |
| `sectors.json`, `tw-industry.json` | (同上) | sector/industry 彙整 |
| `tickers.json`, `concept-stocks.json` | (同上) | ticker/concept 名單 |
| `watchlist-full.json` | run_daily Stage 6 | 24 picks 詳視 |

### 5.2 每日產出 (`public/*.html`)
| 檔案 | 來源 stage | 用途 |
|---|---|---|
| `index.html` | 入口 | GH Pages 首頁 |
| `watchlist.html` | run_daily Stage 6 | 24 picks 列表 |
| `patterns.html` | run_daily Stage 4 | 9 patterns 視覺 |
| `chips.html`, `chips-advanced.html`, `chips-history.html` | (D027/D029 進階) | chips 視覺 |
| `sectors.html`, `concepts.html` | (同上) | sector/concept 視覺 |
| `analyze.html` | analyze 入口 | 多 ticker 比較 |
| `monitor.html` | monitoring dashboard | DB 狀態、cron 狀態 |
| `readme.html`, `deploy.md` | 文件 | 說明 |
| `analyze/<ticker>.html` | run_daily Stage 2 | 1,962 份單 ticker 詳視 |

### 5.3 每日產出 (runtime `_debug/`)
| 檔案 | 來源 | 用途 |
|---|---|---|
| `daily_run_<YYYYMMDD>.log` | run_daily.ps1 | 22:25 階段 log |
| `daily_status.json` | run_daily.ps1 | 外部監控用 JSON |
| `last_completed.json` | write_completion_marker.py | 22:25 completion marker |
| `postflight_<YYYYMMDD>.json` | postflight_daily.py | 00:05 結果 |
| `postflight_<YYYYMMDD_HHMMSS>.log` | postflight_daily.ps1 | 00:05 log |
| `publish_ghpages_<YYYYMMDD_HHMMSS>.log` | publish_ghpages_daily.ps1 | 00:30 log |
| `company_refresh_<YYYYMMDD_HHMMSS>.log` | company_refresh_daily.ps1 | 23:25 log |
| `sync_legacy_<YYYYMMDD_HHMMSS>.log` | sync_legacy_tables_runner.ps1 | 23:30 log |
| `yfinance_<YYYYMMDD_HHMMSS>.log` | yfinance_daily.ps1 | 22:30 log |
| `market_screen_<YYYYMMDD_HHMMSS>.log` | market_screen_daily.ps1 | 18:20 log |
| `metadata_backfill_<YYYYMMDD_HHMMSS>.log` | metadata_backfill_daily.ps1 | 18:10 log |
| `hc_*.json`, `hc_final.json` | check_openalice_health.py | 23:00 自檢 |
| `market_screen_daily_*.log` | (legacy) | 18:20 舊 log |

### 5.4 DB tables (tw_elec)
| Table | 寫入來源 | 用途 |
|---|---|---|
| `daily_data2_full` | OpenAlice 17:35+17:55 | 主 OHLCV (1,949+ tickers) |
| `industry_type` | metadata_backfill.py 18:10 | ticker metadata (1,973 rows) |
| `market_screen_runs` | market_screen_runner.py 18:20 | screener run metadata |
| `market_screen_picks` | market_screen_runner.py 18:20 | 24 picks per run |
| `finmind_taiwan_margin_maintenance` | finmind_maint.py 22:25 | per-stock 維持率 |
| `finmind_taiwan_total_margin_daily` | (結構性 weekly，**PENDING**) | 整體融資 |
| `finmind_month_revenue` | (monthly，**PENDING**) | 月營收 |
| `metadata_quarantine` | market_screen / metadata_backfill | 無法分類的 ticker (目前 11 open, 7768) |
| `daily_data`, `daily_data2`, `chip_daily`, `daily_data3` (4 legacy) | sync_legacy_tables.py 23:30 | legacy 同步表 |

---

## 6. PENDING 清單（feature freeze 期間暫停）

| 代號 | 項目 | 狀態 |
|---|---|---|
| J | 7768 quarantine (11 rows, 9/3-9/12 累積) | 等 Walter 決定（要 TWSE 官方分類） |
| Weekly Shareholding 1330 | D052h-era exit code 2 | PENDING |
| FinMind weekly | `finmind_taiwan_total_margin_daily` 卡 8/18 | 結構性 weekly cadence |
| Slack/Telegram notifier | 未實作 | PENDING |
| cloudflared 1033 | groovelab.dev | PENDING |
| runtime/releases/<sha>/ single source of truth | runtime↔git split 改進 | PENDING |
| 7768 manual close-out | quarantine 累積 | 等 PM 決定 |

---

## 7. 常用查詢指令

```ps1
# 查所有 cron 上次跑狀態
$tasks = @('tw-invest-suite-daily-report','tw-invest-suite-market-screen','tw-invest-suite-publish','tw-invest-suite-postflight','tw-invest-suite-marker-watchdog','tw-invest-suite-health-check')
foreach ($t in $tasks) {
  $i = Get-ScheduledTaskInfo -TaskName $t
  "$t  last=$($i.LastRunTime)  rc=$($i.LastTaskResult)"
}

# 看 dashboard
Get-Content C:\Users\icemo\.claude\skills\tw-invest-suite\reports\dashboard.md
# 或瀏覽器: https://walterLiu168.github.io/tw-invest-suite/data/dashboard.md

# 手動跑 postflight
powershell C:\Users\icemo\Projects\tw-invest-suite\scripts\postflight_daily.ps1

# 手動跑 build_dashboard（單獨驗證）
python C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug\build_dashboard.py

# 手動跑 marker-watchdog（如果 marker 壞了）
python C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug\marker_watchdog.py

# 手動 push（如果 00:30 publish 漏了）
python C:\Users\icemo\Projects\tw-invest-suite\scripts\publish_manifest.py --date <YYYY-MM-DD> --write-to public\data\publish_manifest_<YYYY-MM-DD>.json
powershell C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\publish_ghpages_daily.ps1

# 跑進階 stages（手動 opt-in）
powershell C:\Users\icemo\Projects\tw-invest-suite\scripts\run_daily.ps1 -Mode render -IncludeAdvancedStages
```

---

## 8. Pipeline 一句話總結

> **早上看 `dashboard.md` 1 分鐘；22:25 自動跑；00:30 自動推。紅燈叫我，其他我睡覺。**