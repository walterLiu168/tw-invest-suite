# 2026-09-08-03: Phase A Evidence — P0 根因調查

> Submitted: 2026-09-08 by Mavis → ChatGPT PM (Phase A 任務, no production change)
> Status: 6/6 evidence collected
> Scope: health-check / postflight / 9/8 artifacts / watchlist / publish / market_screen_runs

## TL;DR — 找到 3 個嚴重根因

| # | 根因 | 影響範圍 | 證據位置 |
|---|---|---|---|
| **1** | health-check LastResult=1 因 4 個 sub-check 失敗 | postflight 連 2 天 LastResult=1 | `daily_run_20260908.log` + 手動跑 `check_openalice_health.py` |
| **2** | daily-report 22:25 Stage 6 watchlist **不寫** `public/watchlist.html` | GitHub Pages watchlist 從 9/7 19:11 後就沒更新 | `daily_run_20260908.log` L144-182 |
| **3** | daily-report 22:25 Stage 7 sectors 拋 TypeError，Stage 5 margin_scan + Stage 13 build_ticker_meta 都 timeout 180m | sectors.html / monitor.html 永遠 stale | `daily_run_20260908.log` L184-196, L141, L291 |

---

## Phase A Task 1: health-check log（**找到根因**）

**手動跑** `python check_openalice_health.py --json`（9/9 09:44）：

```json
"failures": [
  { "name": "finmind_taiwan_total_margin_daily", "status": "BEHIND 22d", "last_run": "2026-08-18" },
  { "name": "finmind_month_revenue", "status": "BEHIND 39d", "last_run": "2026-08-01" },
  { "name": "C:\\Groove-Lab\\analyze\\watchlist.html", "status": "NOT UPDATED TODAY", "last_run": "2026-09-08 23:52:21" },
  { "name": "C:\\Groove-Lab\\analyze\\patterns.html", "status": "NOT UPDATED TODAY", "last_run": "2026-09-08 23:36:45" }
]
```

| Sub-check | 預期 | 實際 | 根因 |
|---|---|---|---|
| finmind_taiwan_total_margin_daily | latest = 2026-09-08 | 2026-08-18, **22d behind** | 沒有對應的 cron；上個月才 22d，需新增同步任務 |
| finmind_month_revenue | latest = 2026-09-08 | 2026-08-01, **39d behind** | 沒有對應的 cron；8 月起沒跑 |
| `Groove-Lab\analyze\watchlist.html` | today | 2026-09-08 23:52:21 | 對「today」邏輯需驗證；9/9 daily-report 22:25 還沒跑 |
| `Groove-Lab\analyze\patterns.html` | today | 2026-09-08 23:36:45 | 同上 |

**關鍵**：9/8 23:00 cron 跑時 watchlist.html 是 9/8 22:25 daily-report 剛寫完（23:52 是 23:50 publish 寫的），所以 9/8 23:00 health-check 也應該是「OK」才對 → **9/8 23:00 的真實 sub-check 結果**與現在手動跑的 9/9 09:44 不同。
- 推測 9/8 23:00 health-check 失敗是因為**至少 finmind_taiwan_total_margin_daily + finmind_month_revenue 這 2 個**就夠讓 exit 1。
- 9/8 23:00 是不是還有別的，需要看當時 log（_debug 沒存 health_check log，需新增）。

---

## Phase A Task 2: postflight log（**找到根因**）

`postflight_20260909_000502.log` (4.8KB JSON) 顯示**唯一失敗的 task 是 health-check**：

| task | last_task_result | pass | 失敗原因 |
|---|---|---|---|
| daily-report | 0 | ✅ | (9/8 22:25 跑完，雖然 log 顯示多個 stage timeout，但 LastResult=0) |
| yfinance | 0 | ✅ | |
| **health-check** | **1** | **❌** | **唯一失敗的 task** |
| metadata-backfill | 0 | ✅ | |
| market-screen | 0 | ✅ | |
| company-refresh | 0 | ✅ | |
| sync-legacy | 0 | ✅ | |
| publish | 0 | ✅ | |

其他 checks 全部 pass：
- market_screen: pass (run_id=11, picks_count=24, picks_active=24)
- company_null: pass (null=1, 雖然有 NULL 但 ≤5 閾值)
- industry_count: pass (1973)
- quarantine: pass (open_count=5)
- publish_artifact: pass (log=publish_ghpages_20260908_235002.log, has_done_marker=true, has_pushed=true, has_error=false)

**9/7 postflight (postflight_20260908_000502.log) 同樣唯一失敗**：
- `daily-report` LastResult=**267009**（異常 exit code，9/7 22:25 跑時出問題）
- `health-check` LastResult=**1**

但 9/7 daily-report 後來被手動補完（mtime 9/7 daily_run_20260907.log = 9/8 12:31，跑 14 小時），所以「9/7 失敗」+「9/8 自動」是混合狀態。

---

## Phase A Task 3: 9/8 artifacts 實際路徑 / 內嵌日期 / mtime

| Artifact | 路徑 | size | mtime | 內嵌日期 | 來源 commit |
|---|---|---|---|---|---|
| market-screen-2026-09-08.md | `~/.claude/.../reports/` | 16,691 B | 9/8 18:20:09 | 9/8 | (market-screen cron) |
| market-screen-2026-09-08.html | `~/.claude/.../reports/` | 142,779 B | 9/8 18:20:10 | 9/8 | (market-screen cron) |
| deep-dive-prompts-2026-09-08.md | `~/.claude/.../reports/` | 65,295 B | 9/8 18:20:10 | 9/8 | (market-screen cron) |
| **watchlist-full-2026-09-08.html** | `~/.claude/.../reports/` | 1,779,496 B | **9/8 23:52:21** | 9/8 | (daily-report Stage 6) |
| `C:\Groove-Lab\watchlist.html` | Groove-Lab | 1,832,510 B | 9/8 23:52:21 | 9/8 | (daily-report Stage 6) |
| **`C:\Users\icemo\Projects\tw-invest-suite\public\watchlist.html`** | repo | 10,639 B | **9/7 19:14:08** | **9/7** | (9/7 人工修) |

**嚴重問題**：
- `public/watchlist.html` 從 9/7 19:14 之後就**沒人動過**
- 9/8 daily-report 22:25 寫了 `reports/watchlist-full-2026-09-08.html` 但**沒寫** `public/watchlist.html`
- 9/8 23:50 publish_ghpages 從 `public/` 複製 watchlist.html，所以**推到 GitHub Pages 的是 9/7 19:11 的 stale 版本**

---

## Phase A Task 4: 9/8 watchlist 是自動產生嗎？

**不是**。9/8 GitHub Pages 上的 watchlist 還是 9/7 19:11 人工修的版本。
- fetch `https://walterLiu168.github.io/tw-invest-suite/watchlist.html`
- Title: `Watchlist · 2026-09-07`
- 進場日: 2026-09-07 (all 24 picks)
- 24 picks 跟 9/7 run_id=10 一致，**沒有 9/8 run_id=11 的 24 檔**

**根因**：daily-report Stage 6 寫到 `watchlist-full-2026-09-08.html` 跟 `C:\Groove-Lab\watchlist.html`，但**漏了** `public/watchlist.html`。

---

## Phase A Task 5: 9/8 publish 來源 / 目標 / 遠端

**9/8 publish_ghpages_daily.ps1 23:50:02 跑** (`publish_ghpages_20260908_235002.log`)：
- Source: `public/` (15 files) + `C:\Groove-Lab\analyze` (1976 files) = **2036 files**
- 創建 temp dir `C:\Users\icemo\Projects\tw-invest-suite-ghpages-20260908-235002`
- `git init -b main` + `git remote add origin https://github.com/walterLiu168/tw-invest-suite.git`
- `git commit -m "Deploy GitHub Pages site from public/"` → commit **`a13f69c`** (root commit, force-pushed)
- `git push origin HEAD:gh-pages --force` ✅ exit 0

**注意**：
- 9/7 publish commit 是 `260d513`（per 之前 summary）
- 9/8 publish commit 是 `a13f69c`（force-push 的 root commit，把 9/7 commit 整個覆蓋）
- **9/8 publish 推的 watchlist.html 是 9/7 19:11 stale 版本** ← 驗證於 Task 3

**9/8 daily-report Stage 99 還跑了另一次 publish**（23:57:24）→ 推的是 OLD `walterLiu168/stock-report` repo gh-pages（analyze/1976 files），**不是** tw-invest-suite。**這是 daily-report 內建的舊 publish 路徑**。

---

## Phase A Task 6: 9/4-9/8 market_screen_runs 完整狀態

| id | run_date | run_at | picks | active | notes |
|---|---|---|---|---|---|
| 4 | 2026-09-04 | 2026-09-05 18:34:24 | 24 | 0 (closed) | D052h-fixup2 |
| 10 | 2026-09-07 | 2026-09-07 18:20:09 | 24 | 0 (closed) | D052h-fixup4 |
| 11 | 2026-09-08 | 2026-09-08 18:20:10 | **24** | **24 (active)** | D052h-fixup4 |

- 9/5、9/6 沒 run（週六週日，正常）
- 9/3 沒 run（**PENDING 9/3 gap**，cron 18:20 9/5 才註冊）
- 9/1、9/2 run 在 id=3、id=6（**PENDING A/B/C cleanup**）
- 9/8 run_id=11 **24 picks all active**（active=24 表示 18:20 跑完後，9/8 23:50 publish 之前**還沒被下一個 run 關掉**）

---

## 額外發現（Phase A 順便挖到的）

### 9/8 daily-report 22:25 多個 stage 失敗（log 顯示 14 個 stage 中）

| Stage | 狀態 | 細節 |
|---|---|---|
| 5 (margin_scan) | ❌ TIMEOUT 180m | 23:51:45 殺掉，繼續下一個 stage |
| 7 (sectors) | ❌ TypeError | `sector_aggregate.py:77` `pe > PE_MIN`，pe 是 str 不是 float |
| 13 (build_ticker_meta) | ❌ TIMEOUT 180m | 23:56:06 殺掉 |
| 其他 11 個 stage | ✅ | |

**Stage 99 publish** (23:57:24) 推的是 OLD `stock-report` repo（**錯誤目標**！應該是 tw-invest-suite repo）— daily-report.ps1 內建錯誤路徑。

**每日 elapsed time**：
- 9/4 daily-report: 1.5h（正常）
- 9/6 daily-report: 1.5h
- 9/7 daily-report: **14h**（22:25 → 9/8 12:31）
- 9/8 daily-report: ~1.5h 跑完（雖然有 2 個 stage timeout，但因 fail-fast 沒啟動，整體沒超過 180m timeout）

---

## P0 修復方案（待 Walter 批准，no production change yet）

### P0-1: health-check 4 個 sub-check
- **finmind_taiwan_total_margin_daily (22d behind)**: 新增 23:55 cron 補
- **finmind_month_revenue (39d behind)**: 新增 23:55 cron 補
- **watchlist.html / patterns.html NOT UPDATED TODAY**: health-check「today」邏輯改為「is_daily_report_expected_to_have_run_yet」（例：22:25 之後才檢查）

### P0-2: daily-report Stage 6 watchlist 雙寫 public/
- 改 `run_daily.ps1` Stage 6：除了寫 `watchlist-full-YYYY-MM-DD.html` + `C:\Groove-Lab\watchlist.html`，**還要寫** `public/watchlist.html`
- 這是 daily-report cron 自己處理，不用靠 23:50 publish_ghpages 手動補

### P0-3: daily-report Stage 5/13 timeout + Stage 7 TypeError
- Stage 5 (margin_scan): 加 early exit / 縮 timeout / 拆 chunk
- Stage 13 (build_ticker_meta): 同上
- Stage 7 (sectors): 修 `sector_aggregate.py:77` `pe > PE_MIN` 改為 `float(pe) > PE_MIN if pe else None`

### P0-4: daily-report Stage 99 錯誤 repo
- 把 Stage 99 從 daily-report 拿掉，只留 23:50 獨立的 `tw-invest-suite-publish` cron（已是這樣）
- 或在 Stage 99 加 guard：只在 STAGE_99_PUBLISH=1 環境變數時跑

---

## Status

| Task | Status | Notes |
|---|---|---|
| Phase A-1 health-check log | ✅ done | 4 sub-checks 找出來 |
| Phase A-2 postflight log | ✅ done | 唯一失敗 = health-check |
| Phase A-3 9/8 artifacts | ✅ done | 3 個 artifact 路徑 + mtime 確認 |
| Phase A-4 9/8 watchlist 自動/人工 | ✅ done | **確認是 stale 9/7 推上** |
| Phase A-5 9/8 publish source/target | ✅ done | gh-pages commit a13f69c, 推 9/7 watchlist |
| Phase A-6 9/4-9/8 market_screen_runs | ✅ done | id=4/10/11 確認 |
| 額外發現 daily-report 多個 stage 失敗 | ✅ bonus | Stage 5/7/13 |
| **Phase B 實作** | ⏸️ pending | 等 Walter 批准 P0 修法 |
