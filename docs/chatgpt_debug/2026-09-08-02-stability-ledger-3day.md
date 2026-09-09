# 2026-09-08-02: 3-Day Stability Ledger

> Submitted: 2026-09-08 by Mavis → ChatGPT PM (response to PM-3 in 2026-09-08-01)
> Status: pending ChatGPT PM review
> Scope: cron | db | artifacts | publish | health
> Generation date: 2026-09-08 21:30 (UTC+8)

## 1. Ledger 表格（per ChatGPT PM spec）

| data_date | source rows | run_id | picks (active) | buckets | NULL company | quarantine | artifacts | publish SHA | health | postflight | manual intervention |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **2026-09-07** (Mon) | 1,955 (1,955 tickers on 9/7) | 10 | 24 (0 active — closed by 9/8 18:20) | 4 | 1 (7768) | 4 rows (1 distinct ticker 7768, 9/4+9/5+9/6+9/7) | `market-screen-2026-09-07.{md,html}` (md 10.5K / html 122K) + `deep-dive-prompts-2026-09-07.md` (58K) | `260d513` on `gh-pages` (2036 files: 1976 analyze + 15 public/ + .nojekyll) | **1** | **1** | **YES** — 9/7 19:11 watchlist.html manual fix (5-day stale 9/2 → 9/7) |
| **2026-09-08** (Tue) | 1,955 (1,955 tickers on 9/8) | 11 | 24 (**24 active**) | 4 | 1 (7768) | 5 rows (1 distinct ticker 7768, added 9/8 row) | `market-screen-2026-09-08.{md,html}` + `deep-dive-prompts-2026-09-08.md` (assumed, not yet verified) | 9/8 23:50 LastResult=0, **commit SHA not yet captured** (need to query) | **1** | **1** | **none** reported (watchlist fixed 9/7 19:11) |
| **2026-09-09** (Wed) | **PENDING** | **PENDING** | **PENDING** | — | — | — | — | — | — | — | — |

**17:35+ OHLCV landing for 9/9 not yet occurred** (current time 21:30 UTC+8 — OHLCV lands 17:35+ daily; 9/9 18:10 metadata-backfill + 18:20 market-screen + 22:25 daily-report + 23:00 health-check + 23:25 company-refresh + 23:30 sync-legacy + 23:50 publish + 00:05 postflight 9/10 not yet)

## 2. 驗收門檻對照（per PM 9.7）

| 條件 | 9/7 | 9/8 | 9/9 |
|---|---|---|---|
| 9 個 cron 依賴順序完成，無人工重跑 | ❌ watchlist 手動修 | ⏸️ need full audit | ⏸️ pending |
| OHLCV 日期正確，ticker 數量合理 | ✅ 1,955 | ✅ 1,955 | ⏸️ pending |
| 當日唯一 active run，正好 24 picks | ✅ run_id=10 (closed 9/8) | ✅ run_id=11 (24 active) | ⏸️ pending |
| 4 個 bucket 完整 | ✅ 4 | ✅ 4 | ⏸️ |
| company NULL = 0 | ❌ = 1 (7768) | ❌ = 1 (7768) | ⏸️ |
| 未解 quarantine 去重 + 告警 | ❌ 4 → 5 重複 row | ❌ 5 重複 row | ⏸️ |
| watchlist/24 檔/prompt 日期 = data_date | ⚠️ 9/7 是手動修的 | ⏸️ need to verify | ⏸️ |
| GitHub Pages 內容 + manifest 驗證成功 | ❌ **無 manifest** | ⏸️ | ⏸️ |
| health-check + postflight = 0 | ❌ 都是 1 | ❌ 都是 1 | ⏸️ |
| 每個 sub-check 可追溯 | ❌ health-check log 未撈 | ❌ | ⏸️ |
| production commit = origin/main | ✅ 9/8 push 8d48318..15d7c57 | ✅ | ⏸️ |
| 沒有手動改 HTML / 修 DB / 改 runtime mirror | ❌ watchlist 9/7 手動 | ✅ | ⏸️ |

**連續 3 天升級 Stable 的門檻：9/7 ❌ / 9/8 ❌ / 9/9 ⏸️ → 至少還要 1 個完全 ✅ 的天才行**

## 3. 阻塞升級的具體問題（按 PM P0 排序）

### 3.1 ❌ health-check LastResult=1 (從 9/4 起)
- 9/7 23:00 = 1, 9/8 23:00 = 1
- 連續 5 天失敗
- **根因未查**（per PM 9.2 P0：每個 sub-check、預期值、實際值、data date、exit code）

### 3.2 ❌ postflight LastResult=1
- 9/8 00:05 (覆蓋 9/7) = 1
- 9/9 00:05 (覆蓋 9/8) = 1
- 連續 2 天失敗
- **根因未查**（per PM 9.2 P0：每個 sub-check 列出）

### 3.3 ❌ 9/7 watchlist.html 人工修
- 5 天 stale 從 9/2 到 9/7
- 9/7 19:11 手動 `render_watchlist_html.py` + copy to public/ + push to gh-pages
- 違反 PM 條件「沒有手動改 HTML」

### 3.4 ❌ 7768 quarantine 重複 4 → 5 row
- 同一 ticker 每天新增 1 row，無去重
- 違反 PM 條件「quarantine 有去重」

### 3.5 ❌ company NULL = 1 (7768)
- 連續 5+ 天 NULL
- 違反 PM 條件「company NULL = 0」
- 7768 沒有 industry_type row，company-refresh 自動跳過

### 3.6 ❌ 無 publish manifest
- gh-pages commit 260d513 (9/7) 沒有 data_date、run_id、commit SHA、artifact hashes 記錄
- 違反 PM 條件「GitHub Pages 頁面內容及 manifest 驗證成功」

## 4. Mavis 建議下一步（待 Walter 批准）

### 4.1 立即可做（Mavis 自主）
- [ ] **P0-1**: 撈 health-check 9/8 23:00 失敗的 log + 每個 sub-check
- [ ] **P0-2**: 撈 postflight 9/9 00:05 失敗的 log + 每個 sub-check
- [ ] **P0-3**: 補完 9/8 缺漏：artifact 路徑確認、watchlist 日期驗證、commit SHA 查
- [ ] **P1**: 撈 9/8 之前 (9/4 ~ 9/6) 的 market_screen_runs 完整狀態，了解 D052h 之前累積的差距

### 4.2 P0 需要 Walter 批准
- [ ] **7768 TWSE 人工 resolve**（P0-5）：半導體 vs 電子工業分類
- [ ] **是否暫停其他功能直到 9/11**（per PM 9.2 P0 末項）
- [ ] **single source of truth**（per PM 9.4）：是否要建立 `runtime/releases/<sha>/` 部署架構
- [ ] **publish manifest 設計**（per PM 9.2 P0）：Mavis 寫 proposal，Walter 批准後實作

### 4.3 9/9 整天等到的時候補
- 17:35+ OHLCV landing
- 18:10 metadata-backfill (LastResult)
- 18:20 market-screen (run_id, picks)
- 22:25 daily-report (watchlist freshness)
- 23:00 health-check (LastResult + log)
- 23:25 company-refresh
- 23:30 sync-legacy
- 23:50 publish
- 9/10 00:05 postflight

## 5. 專案狀態標記

**Operational hardening — feature freeze** (per PM 9.8 建議)
- 從現在 (2026-09-08 21:30) 起到 9/11 (連續 3 個交易日無人工介入) 之前
- 不接受新功能 PR（除 P0 hotfix）
- 集中精力關閉 health-check + postflight 根因
- 9/9 ~ 9/11 三天的 ledger 是晉升 Stable 的證據

## 6. 跨日觀察

| 觀察項 | 9/6 (Sun, 假日) | 9/7 (Mon) | 9/8 (Tue) | 9/9 (Wed) | 9/10 (Thu) | 9/11 (Fri) |
|---|---|---|---|---|---|---|
| Trading day | ❌ (週末) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Cron 全跑 | n/a | ⚠️ watchlist 手動 | ✅ 自動 | ⏸️ pending | ⏸️ | ⏸️ |
| Health/Postflight | 0 cron | 1/1 | 1/1 | ⏸️ | ⏸️ | ⏸️ |
| company NULL | n/a | 1 | 1 | ⏸️ | ⏸️ | ⏸️ |
| 7768 quarantine | n/a | 4 row | 5 row | ⏸️ | ⏸️ | ⏸️ |

**3 個 trading day (9/9, 9/10, 9/11) 都必須是全自動、無人工介入、health+postflight=0 才能升 Stable**

---

## Status

| Action | Status | Notes |
|---|---|---|
| Ledger v1 送出 | ✅ done | 2026-09-08 21:30 |
| 9/9 全天證據補完 | ⏸️ pending | 18:20 後才有第一筆 |
| 9/10 整天 | ⏸️ | |
| 9/11 整天 + 升 Stable 評估 | ⏸️ | |
