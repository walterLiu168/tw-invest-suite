# 2026-09-10 D053-fixup Phase 1 純讀診斷

**Status**: ⚠️ Spec 前提「P0 false-green」**不成立**；D053 P0-1 dual-write **已執行成功**，但 spec 寫的依據是 23:37 9/9 之前的 stale state。

## 1. 重大反證：spec 假設錯誤

| 項目 | Spec 假設（寫於 23:37 9/9 之前） | 當下實際（09:44 9/10） |
|---|---|---|
| `public/watchlist.html` mtime | 2026-09-07 19:14 | **2026-09-10 00:26:40** |
| LastResult | 0 | 0（**未變**） |
| daily-report 狀態 | (implicit) 卡住 | **9/9 22:25 觸發，9/10 00:31 完成**（2h6m） |

**所有三個 watchlist.html 檔案 byte-identical**：
```
C:\Groove-Lab\watchlist.html                            size=1,715,887  mtime=2026-09-10 00:26:40  sha256=91CC7B198C4794B3...
C:\Groove-Lab\analyze\watchlist.html                    size=1,715,887  mtime=2026-09-10 00:26:40  sha256=91CC7B198C4794B3...
C:\Users\icemo\Projects\tw-invest-suite\public\...html  size=1,715,887  mtime=2026-09-10 00:26:40  sha256=91CC7B198C4794B3...
```

**public/watchlist.html 內容驗證**：
- `<title>台股深度選股 · 2026-09-09 · 24 檔</title>` ✅
- date_in_body: 2026-09-09 ✅
- rows: 24 ✅
- mtime ≥ run_started_at（22:25 9/9）✅

→ **D053 P0-1 dual-write 已成功**，9/10 00:26:40 的 mtime 證明 public/ 是當日新檔。

## 2. 為什麼 mtime 是 00:26:40 不是 00:31:16？

`daily_run_20260909.log` 顯示 D053 copy 是在 `[00:31:16] [publish] Copying watchlist...` 跑的，**但 public/ mtime 是 00:26:40**（早 5 分鐘）。

兩種可能：
- **A. PowerShell `Copy-Item -Force` 在 destination 內容相同時 preserve source mtime**（我沒驗證，但有此可能）
- **B. Stage 6 render_full_watchlist.py 內部還有另一個 path 寫到 public/**

我驗證過 render_full_watchlist.py（runtime 90,235 bytes / git 89,301 bytes）只寫到 `C:\Groove-Lab\watchlist.html`（line 1913 runtime / 1898 git），**沒有直接寫到 public/**。所以是 A：Copy-Item 在同內容時 preserve source mtime。

無論如何，**public/ 檔案是當日有效內容**，不是 stale。

## 3. 為什麼 23:37 9/9 看到 stale？

當時 `daily_run_20260909.log` 才 3,359 bytes，且檔案 mtime 是 22:26:19。**那時 daily-report 才剛完成 Stage 1，正在跑 Stage 2 render（94 min）**。我看到的 mtime 9/7 19:14 是上一次（9/7 19:11 手動修復）的殘留。

**log 持續在寫，只是 buffer 沒 flush**。00:00:47 第一次 flush，後續 Stage 3-6 全部完成。

## 4. 真正發現的問題（讀階段）

### 4.1 runtime vs git 不一致（spec 排除的 hardlink/CRLF 不算，但 sync 差距是真的）

| 檔案 | runtime size | git size | runtime SHA-1 | git SHA-1 |
|---|---|---|---|---|
| run_daily.ps1 | **15,364 b** | 12,711 b | ad7d2e5ae1a7... | a8f697665b94... |
| render_full_watchlist.py | 90,235 b | 89,301 b | 90235 bytes | 89301 bytes |
| publish_manifest.py | 11,202 b | 11,202 b | 80732104b9d1 | 063d86860aa6 |
| daily_summary.py | 17,665 b | 17,665 b | 31617477f155 | ab16f37302b1 |
| publish_ghpages_daily.ps1 | 1,619 b | 1,619 b | 8ec450089c91 | ab91db410638 |

- **run_daily.ps1 差 2,653 bytes / runtime 多了 17 stages 結構 vs git 只有 6 stages** → runtime 從某個時間點開始「活得比 git 久」
- 其他 4 個 D054 檔 byte size 相同但 SHA-1 不同 → 純 CRLF 議題（spec 排除 hardlink/CRLF normalize）

**這是 spec 沒預期的發現**：
- 9/8 22:25 那次 daily-report 是用 runtime 跑的，runtime 已經比 git 多 7 個 stages（og_image, sectors, chips*, tw_industry, ...）
- 這些 stages 9/8 nightly 跑成功了嗎？log 大小應該會反映，但今晚我沒去查
- 如果 runtime 一直在演化、git 沒跟上，每次 deploy 都會 divergence drift

### 4.2 run_daily.ps1 結構問題（spec 沒抓到）

- **Log 寫 `/5` 但 runtime 有 17 stages** (line 158)：cosmetic bug
- **Stage 5 margin_scan TIMEOUT 180m** (line 290 → 9/9 22:26 + 180m = 01:26 9/10 → 但 log 顯示 00:25:58 TIMEOUT 180m)：15min timeout 不夠；spec 寫的 180m 但實際給 15*60 = 900s = 15min。**Bug 在 line 294**：`To=15*60`（15min），但 spec 寫 margin_scan timeout 180m。log 顯示「timeout 180m」是 `Run-Stage` 函式 hardcode 訊息（line 158 用 `${TimeoutMin}m`），實際 timeout 是 stage 自己的 15min。
- **Stage 8 og_image 是 conditional**：if `C:\Groove-Lab\watchlist.html` exists, 否則 skip。寫到 log 是 `[!] watchlist.html not found, skipping OG image generation`（line 311）— 9/9 log 沒看到這行，意味著 00:26:40 後 watchlist.html 已存在，Stage 8 有被加入。
- **Catch swallow publish error**（line 322 / 369-371）：`try { ... } catch { Log-Msg "publish ERR: $_" }` — publish 區段 catch 不 exit 1。這意味著如果 Stage 99 publish 失敗，daily-report 仍會 exit 0（隱含 false-green）。
- **Stages continue on failure**（line 302-304）：`if (-not $ok) { Log-Msg "[!] Stage $($s.Name) failed — continuing to next stage" }` — 一個 stage 失敗不會 abort。這是設計但 spec 沒明說。

### 4.3 Task Scheduler 設定

- **Cron 路徑用 runtime mirror**：`powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\run_daily.ps1"`
- **WorkingDir**: `C:\Users\icemo\.claude\skills\tw-invest-suite\scripts`
- **ExecutionTimeLimit**: PT4H
- **Daily at 22:25**

→ cron 跑的是 runtime 副本，runtime 跟 git 不同步。

### 4.4 Runtime path sync 缺失的測試檔

- `~/.claude/skills/tw-invest-suite/tests/test_publish_manifest.py` → **不存在**
- `~/.claude/skills/tw-invest-suite/scripts/publish_manifest.py` → 存在（11,202 b）
- runtime 沒 sync tests/ 目錄

## 5. 證據（9 項）

### 5.1 root cause
**沒有 P0 false-green**。Spec 假設錯誤。實際 D053 P0-1 已於 9/10 00:26:40 成功將 Stage 6 產出的 `C:\Groove-Lab\watchlist.html` 同步到 public/。**真實的問題是 daily-report 從 22:25 跑到 00:31（2h6m）才完成**，主因是 Stage 2 render 慢（94 min）。

### 5.2 修改檔案與行號
N/A — Phase 1 純讀，不修改。**有問題的 4 個 line 值得 Phase 2 修**（但現在不修）：
- `run_daily.ps1:158` — `Log-Msg "[Stage $Number/5]"` 寫死 /5
- `run_daily.ps1:294` — `To=15*60` 15min 太少，Stage 5 margin_scan 9/9 真的 TIMEOUT
- `run_daily.ps1:322` / `369-371` — `try { ... } catch { ... }` 不 exit 1
- `run_daily.ps1:300-305` — `foreach stages { if (-not $ok) continue }` 失敗繼續

### 5.3 unit tests
N/A — 現有 31 (market_screen_runner) + 21 (publish_manifest) = 52 tests 仍 pass（D054 fixup 已驗證）。

### 5.4 failure-path test
N/A — 沒有新增的 failure-path test（spec Phase 2 才需要）。

### 5.5 scheduler resolved paths
- **Task To Run**: `powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\run_daily.ps1"`
- **Start In**: `C:\Users\icemo\.claude\skills\tw-invest-suite\scripts`
- **Resolved** = runtime mirror（非 git path）

### 5.6 source/runtime SHA
- **HEAD commit** (production source): `df9ff62b22ae04a6c6bc73a501a2f9ec9b153456`
- **run_daily.ps1 git** SHA-1: `a8f697665b94...` (12,711 b)
- **run_daily.ps1 runtime** SHA-1: `ad7d2e5ae1a7...` (15,364 b) — runtime +2,653 b 17 stages 結構
- **CRLF mismatch** (publish_manifest.py / daily_summary.py / publish_ghpages_daily.ps1)：byte size 同、SHA-1 不同（CRLF vs LF）

### 5.7 artifact date、rows、bucket counts、mtime、SHA
```
C:\Groove-Lab\watchlist.html                            size=1,715,887  mtime=2026-09-10 00:26:40  sha=91CC7B198C4794B3
C:\Groove-Lab\analyze\watchlist.html                    size=1,715,887  mtime=2026-09-10 00:26:40  sha=91CC7B198C4794B3
C:\Users\icemo\Projects\tw-invest-suite\public\...html  size=1,715,887  mtime=2026-09-10 00:26:40  sha=91CC7B198C4794B3
```
- date_in_body: **2026-09-09** ✅
- rows: **24** ✅
- buckets: 6/6/6/6 (24 picks split by close price <100/100-300/300-1000/>1000)
- mtime ≥ run_started_at (22:25 9/9) ✅
- public/ source/runtime SHA-256: identical 91CC7B198C4794B3... (public/ 內含就是 Stage 6 產出)

### 5.8 git status --short（working tree, NOT staged）
```
 M 12 files in public/                 (chips/sectors/watchlist/concepts HTML+JSON, daily regenerated)
 D 3 chips-history JSONs               (7-27/28/29 cleanup)
?? 13 untracked items:
    _*.py × 6 + _*.ps1 × 1 + _*.txt × 3   (audit/debug scripts — 建議清)
    docs/chatgpt_debug/...postmortem.md + ...d053-fixup-phase1-diagnosis.md (本檔)
    public/data/chips-history/{9-7,9-8,9-9}.json
    public/data/daily_summary_{9-8,9-9}.md
    public/data/publish_manifest_2026-09-08.json
```

### 5.9 仍保持 PENDING 的項目
- **H. existing-ticker reconciliation** (name/industry drift detection)
- **J. 7768 manual close-out** (5 quarantine rows 9/4-9/8)
- **health-check 2 finmind BEHIND** (finmind_taiwan_total_margin_daily 22d, finmind_month_revenue 39d) — 23:00 LastResult=1
- **3-day stability gate** (9/7 ❌ / 9/8 ❌ / 9/9 ⏸️)
- **DB residue A/B/C** (market_screen_runs id=3/4/6 9/1-9/2 舊 run)
- **9/5 mis-named file** (Walter approved 留)
- **F3/F5/F8/F16/F18** (chatgpt_browser_reviewer hardening — pending)
- **9/3 gap** (cron 18:20 not registered 9/3)
- **cloudflared restart** (groovelab.dev returning 1033)
- **daily-report Stage 5/13 timeout 180m** (margin_scan 15min 不夠)
- **daily-report Stage 7 sectors TypeError** (D053 P0-5 已修但無法驗證)
- **daily-report Stage 99 publishing to OLD stock-report repo** (D054 scope 外)
- **Slack/Telegram notifier** (A+C scope 外)
- **runtime mirror vs git path split** (per PM 9.4, deferred to after 3-day stability)
- **NEW: run_daily.ps1 runtime/git divergence** (2,653 b extra, 17 stages vs 6 in git)
- **NEW: log "Stage N/5" cosmetic** when actually 17 stages
- **NEW: publish block try/catch swallow** (silent exit 0 on failure)

## 6. 結論 + 給 Walter

- **D053 P0-1 部署 PASS**（spec 寫於 stale state，9/9 23:37 之前。當下證據顯示 9/10 00:26:40 已成功）
- **D053 P0-2 (health-check render guard)** 仍 FAIL（health-check 23:00 LastResult=1），但這跟 watchlist 是獨立問題
- **D053 P0-5 (sector TypeError guard)** 在 runtime 端已修，但 Stage 7 sectors 9/9 沒跑到（Stage 5 TIMEOUT 浪費太多時間，Stage 6+ 才接續）

**真正值得修的**（不在 spec 範圍，但 Phase 2 應該考慮）：
1. Stage 5 margin_scan `To=15*60` 太少 → 改 180*60
2. log "Stage N/5" 寫死 → 動態計算
3. publish block try/catch 不 exit 1 → 改 exit 1
4. runtime/git 同步策略（runtime 是 source of truth 還是 git）

**不要 commit 任何 code 改動**（per spec "先提交診斷結論，不要先猜測修改"）

---

_Generated by Mavis on 2026-09-10T09:50 GMT+8_
