# 2026-09-10 D053-fixup Phase 1b — runtime/git divergence 純讀追查

**Status**:
- Original Stage 6 allegation: **closed as invalid premise** (D053 P0-1 已成功)
- Runtime/git divergence: **investigated — mixed, not unidirectional**
- Daily automatic remote publishing: **pending** (D054 fixup deploy 還需 watchlist public/ mtime ≥ 9/9 才算 canonical)
- Stable gate: **not started**

## 1. runtime-only 功能（live production 但 git 沒收到）

### 1.1 `run_daily.ps1` Stages 7-17（git 只有 Stages 1-6 + Stage 99 publish）

git log for `run_daily.ps1`:
```
4f340be D053: P0 batch1 - watchlist dual-write + sector TypeError + health-check render guard
fbf1896 D023 run_daily: 6 tw-specific stages (OpenAlice distributed 15:55-21:45)
c7eb061 D022 run_daily: integrate OpenAlice 7 phases + news + rss + missing-data (16 stages total)
61b06b4 D021 run_daily: add FinMind TaiwanStockMarginMaintenance stage 7 (D020 integration)
62c76cc Add 7-dim margin rebound scanner + multi-dim watchlist tab
506414f Add render_full_watchlist to daily pipeline (stage 7) + fix daily_commentary 120d label
0ba9aa2 Initial commit: tw-invest-suite v1.0
```

**`fbf1896` (D023) 之後 `4f340be` (D053) 之前**那段時間，**runtime run_daily.ps1 被手動加了 11 個 stages，但 git 從未收到**。證據：
- 8/24 起 daily-run log 就有 18 stage markers（17 stages + 1 stage 99）
- 8/24 是 D027 (chip_rank) 跟 D029 (fetch_tw_industry) 第一次 commit 到 git
- 但 run_daily.ps1 git 一直停在 D023 的 6 stages
- 推測 ~8/20-8/23 有人手動改 runtime run_daily.ps1 加 Stages 7-17，後續 nightly 都用 runtime

| Stage # | 名稱 | 指令 | timeout | 來源 |
|---|---|---|---|---|
| 7 | sectors | `C:\Users\icemo\Projects\tw-invest-suite\src\sector_aggregate.py` | 5min | git path |
| 8 | og_image | `C:\Users\icemo\Projects\tw-invest-suite\src\generate_og.py` | 2min | git path (conditional) |
| 9 | chips | `C:\Users\icemo\Projects\tw-invest-suite\src\chip_rank.py` | 5min | git path |
| 10 | chips_advanced | `C:\Users\icemo\Projects\tw-invest-suite\src\chip_advanced.py` | 10min | git path |
| 11 | render_chips_advanced | `C:\Users\icemo\Projects\tw-invest-suite\src\render_chips_advanced.py` | 60s | git path |
| 12 | chips_history | `C:\Users\icemo\Projects\tw-invest-suite\src\chip_history.py` | 5min | git path |
| 13 | build_ticker_meta | `C:\Users\icemo\Projects\tw-invest-suite\src\build_ticker_meta.py` | 30s | git path |
| 14 | chip_push | `C:\Users\icemo\Projects\tw-invest-suite\src\chip_push.py` | 30s | git path |
| 15 | tw_industry | `C:\Users\icemo\Projects\tw-invest-suite\src\fetch_tw_industry.py` | 30s | git path |
| 16 | concept_stocks | `C:\Users\icemo\Projects\tw-invest-suite\src\concept_stocks.py` | 10s | git path |
| 17 | render_concepts | `C:\Users\icemo\Projects\tw-invest-suite\src\render_concepts.py` | 30s | git path |

來源：runtime `run_daily.ps1:299-344`（git 沒這 11 個 stage definitions）

### 1.2 `render_full_watchlist.py` None/<=0 處理（runtime 已修但 git 沒收到）

| 項目 | RT | GIT |
|---|---|---|
| size | 90,235 b | 89,301 b |
| lines | 1,924 | 1,909 |
| unique-to-RT | **24 lines** | - |
| unique-to-GIT | - | **11 lines** |

**runtime 版的保護邏輯**（24 lines 差異）：
```python
# collect all values for y scale (排除 None 與 <=0 的假性缺值)
if v is not None and isinstance(v, (int, float)) and v > 0:
    all_vals.append(v)
# plot each series (None 與 <=0 一律跳過，避免假性暴跌到 0)
if isinstance(v, (int, float)) and v <= 0: continue
# dots (last valid point only)
last = [v for v in vals if v[1] is not None and (not isinstance(v[1], (int, float)) or v[1] > 0)]
# 把 None / 0 / 負值 視為缺值 (DB 偶有 NULL), 不會畫成掉到 0 的假性暴跌
closes.append(None) if v is None or ... else closes.append(float(v))
# MA5/13/27/54 — 跳過 None 視窗, 視窗內有效值 < 一半才標 None
if len(valid) >= max(2, n // 2): out[i] = sum(valid) / len(valid)
# 取最後一個有效收盤價（避免 closes[-1] 是 None）
```

**git 版缺這些保護**，會用 `closes[-1]` 當最後點（可能是 None）— 9/8 之前 nightly 跑 git 版的話會畫出假性暴跌到 0。

來源：runtime +934 b 是手動加的，假設 commit 在 8/24-9/8 之間某個時間點。

## 2. git-only 功能（live production 沒用 git 新版）

### 2.1 `sync_legacy_tables.py` D052h-fixup 重寫（git 有但 runtime 沒收到）

| 項目 | RT | GIT |
|---|---|---|
| size | **7,433 b** | 6,972 b |
| lines | **166** | 194 |
| 用途 | D046 原始版（無 runtime import, 無 monkey-patch） | **D052h-fixup** (self-contained, 跳過 close market_screen_picks) |

**runtime 是 D046 舊版**（2026-08-20 ~166 lines），**git HEAD 是 D052h-fixup**（2026-09-08 194 lines）。

D052h-fixup 包含：
- Self-contained（不 import runtime）
- 跳過 close market_screen_picks（這是 market_screen_runner 的工作）
- 9/8 commit `3b7c3f9` 改的

**23:30 sync-legacy cron 跑的是 runtime D046 舊版**，沒拿到 D052h-fixup 的 bug 修復。

來源：runtime sync 在 D052h-fixup commit 後沒回傳 runtime mirror。

## 3. Pure CRLF（無實質差異）

| 檔案 | RT | GIT | LF-normalize |
|---|---|---|---|
| publish_manifest.py | 11,202 b | 11,202 b | **SAME** |
| daily_summary.py | 17,665 b | 17,665 b | **SAME** |
| publish_ghpages_daily.ps1 | 1,619 b | 1,619 b | **SAME** |

→ D054 部署的 3 個新檔，runtime vs git **純 CRLF 議題**，內容 identical。Spec 排除 hardlink/CRLF normalize，不動。

## 4. Runtime mirror 缺失的檔案

| 檔案 | GIT | RUNTIME | 影響 |
|---|---|---|---|
| `tests/test_publish_manifest.py` | Y | **N** | 從 git 跑 D054 unit test 仍 OK；postflight 走 runtime 不依賴 tests |
| `scripts/db_status.py` | N | N | (false positive — 兩個都沒有，但 runtime run_daily.ps1:120 用 `_debug\db_status.py`) |
| `scripts/company_refresh.py` | Y (4,137 b) | **N** | 23:25 company-refresh cron 必須用 git path 或 sync 到 runtime |
| `scripts/market_screen_runner.py` | Y (24,876 b) | **N** | 18:20 market-screen cron 必須用 git path |

→ **23:25 company-refresh + 18:20 market-screen 兩個 cron 必須從 git 路徑跑**，不是 runtime（runtime 沒這兩份）。

## 5. semantic differences（line by line）

### 5.1 run_daily.ps1（runtime +2,653 b, +52 lines）

runtime `run_daily.ps1:273-344` 有完整 17 stages 定義，git 只有 6 stages（line 273-297）。差異：
- 11 個新 stage 定義（sectors / og_image conditional / chips / chips_advanced / render_chips_advanced / chips_history / build_ticker_meta / chip_push / tw_industry / concept_stocks / render_concepts）
- 每個 stage 有 timeout 設定
- og_image 是 conditional（if C:\Groove-Lab\watchlist.html exists, add stage else log skip）
- log line 158 寫死 `[Stage $Number/5]` — 17 stages 都會 log 為 "Stage N/5"
- 沒改 D053 dual-write 邏輯

### 5.2 render_full_watchlist.py（runtime +934 b, +15 lines）

runtime 處理 `None` / `0` / `負值` 假性缺值，git 版不處理。**bug fix not committed**。

### 5.3 sync_legacy_tables.py（runtime -461 b, -28 lines）

runtime 是 D046 原始版（更早），git 是 D052h-fixup 重寫版。**git 是 source of truth**，runtime 沒收到 D052h-fixup 改動。

## 6. 每項差異的來源及可信度

| 差異 | 來源 | 可信度 |
|---|---|---|
| run_daily.ps1 +Stages 7-17 | 手動 runtime edit, ~8/20-8/23，**未 commit** | high（runtime 持續 17 stages 跑了 2+ 週 nightly） |
| render_full_watchlist.py +None handling | 手動 runtime edit, 8/24-9/8 之間，**未 commit** | high（24 lines 是真實差異） |
| sync_legacy_tables.py runtime 落後 D052h-fixup | runtime mirror 沒回傳 9/8 commit，**runtime 是 D046 舊版** | high（166 vs 194 lines 是 D046 → D052h-fixup 演進痕跡） |
| 3 個 D054 檔 CRLF | runtime vs git 跨平台 newline，無實質差異 | high（LF normalize 後 SAME） |

## 7. 建議 canonical 版本（per 檔案，不是 unidirectional）

| 檔案 | Canonical | 理由 |
|---|---|---|
| run_daily.ps1 | **runtime** | runtime 跑 2+ 週 nightly 都成功，git 已 stale |
| render_full_watchlist.py | **runtime** | runtime 有 None/<=0 處理，是 bug fix |
| sync_legacy_tables.py | **git HEAD (D052h-fixup)** | git 是新版，runtime 是 D046 舊版，runtime 應升級到 git |
| publish_manifest.py | **git == runtime** | 純 CRLF，無實質差異 |
| daily_summary.py | **git == runtime** | 純 CRLF |
| publish_ghpages_daily.ps1 | **git == runtime** | 純 CRLF |

→ 沒有 unidirectional「runtime 是新版」或「git 是新版」。**每個檔案要單獨評估**。

## 8. 若以 runtime 回收到 git（runtime → git 方向）

風險：**低**（git 拉高 → runtime 一致）
- `run_daily.ps1`: git 收到 Stages 7-17 = 正確（runtime 是 production）
- `render_full_watchlist.py`: git 收到 None 處理 = 正確（runtime 是 production）
- `sync_legacy_tables.py`: 沒動作（runtime 仍舊 D046）
- `publish_manifest.py` / `daily_summary.py` / `publish_ghpages_daily.ps1`: 沒實質 diff

**單一 commit 可以解決 run_daily.ps1 + render_full_watchlist.py 兩個 runtime 領先的差異**。

## 9. 若以 git 覆蓋 runtime（git → runtime 方向）

風險：**高**（runtime 失去 2+ 週 nightly 驗證的行為）
- `run_daily.ps1`: runtime 失去 Stages 7-17，nightly 變 6 stages，chip/concept/og/sector/industry/margin 全部不跑
- `render_full_watchlist.py`: runtime 失去 None 處理，下次 daily-report 會畫假性暴跌
- `sync_legacy_tables.py`: runtime 升級到 D052h-fixup（這次是 upgrade, 但需要重新驗證 nightly 跑得起來）

→ **不建議 git 覆蓋 runtime**。

## 10. 建議後續最小 Phase 2 scope

**2 個 commits**（per spec, scoped, no `git add -A`）：

### Commit 1: `D055 runtime/git sync — capture Stages 7-17 + render_full_watchlist None handling`
- 範圍：`scripts/run_daily.ps1`（runtime → git）
- 範圍：`scripts/render_full_watchlist.py`（runtime → git）
- 風險：低（runtime 領先，git 拉高）
- 驗證：after merge, `git log` 顯示 commit，`diff --stat` 確認 scoped，runtime SHA 與新 git SHA 一致

### Commit 2: `D055b runtime sync — promote sync_legacy_tables to D052h-fixup`
- 範圍：`scripts/sync_legacy_tables.py`（git → runtime）
- 風險：中（git 是新版，runtime 需重新驗證）
- 驗證：runtime 23:30 sync-legacy cron 跑得起來；sync 結果與 D052h-fixup 預期一致

**兩個 commit 都先做一個 D054-fixup-style 驗收文件**（含 unit-test, runtime mirror SHA 對照, scoped diff 清單），等 Walter 批准再 push。

## 11. 23:50 canonical publish / 00:05 postflight 時序

- 9/9 23:50 publish LastResult=1（fail）— manifest not built, daily-report 還在跑
- 9/10 00:05 postflight LastResult=1（fail）— canonical_fails=2，daily-report 還沒完成
- 9/10 00:31:14 daily-report 完整完成（exit 0）
- 9/10 00:32:14 Stage 99 publish 完整完成

→ 23:50 publish 跟 00:05 postflight 都在 daily-report 完成**之前**觸發，這是排程衝突。**這是獨立於 D053-fixup 的排程問題**，建議移到 daily-report 完成後（例如 01:00 publish、01:30 postflight）。但這不在 Phase 1b scope，**保留 PENDING**。

## 12. 仍 PENDING 項目

從 D053-fixup Phase 1 + Phase 1b 累計：

- **H. existing-ticker reconciliation** (name/industry drift detection)
- **J. 7768 manual close-out** (5 quarantine rows 9/4-9/8)
- **health-check 2 finmind BEHIND** (finmind_taiwan_total_margin_daily 22d, finmind_month_revenue 39d) — 23:00 LastResult=1
- **3-day stability gate** (9/7 ❌ / 9/8 ❌ / 9/9 ⏸️) — 9/9 ⏸️ 因為 daily-report 太慢影響 23:50/00:05
- **DB residue A/B/C** (market_screen_runs id=3/4/6 9/1-9/2 舊 run)
- **9/5 mis-named file** (Walter approved 留)
- **F3/F5/F8/F16/F18** (chatgpt_browser_reviewer hardening)
- **9/3 gap** (cron 18:20 not registered 9/3)
- **cloudflared restart** (groovelab.dev returning 1033)
- **daily-report Stage 5 margin_scan To=15min 太少** (9/9 真實 TIMEOUT)
- **daily-report Stage 13 build_ticker_meta To=30s 太少** (9/9 真實 TIMEOUT)
- **daily-report Stage 7 sectors TypeError guard** (D053 P0-5 已修但無法驗證 — 9/9 sectors OK 但因 9/9 是 timeout 走完的，非完整測試)
- **daily-report Stage 99 publishing to OLD stock-report repo** (D054 scope 外)
- **Slack/Telegram notifier** (A+C scope 外)
- **runtime mirror vs git path split** (per PM 9.4) — Phase 1b 顯示這個問題比預期嚴重
- **NEW: run_daily.ps1 11 stages 未 commit** (Phase 1b 確認，2+ 週 nightly 用 runtime)
- **NEW: render_full_watchlist.py None handling 未 commit** (Phase 1b 確認)
- **NEW: sync_legacy_tables.py runtime 落後 D052h-fixup** (Phase 1b 確認)
- **NEW: 23:50 publish / 00:05 postflight 排程衝突** (daily-report 跑完才觸發)

## 13. status wording（per spec）

- Original Stage 6 allegation: **closed as invalid premise**
- Runtime/git divergence: **investigated, 2 commits proposed, awaiting Walter approval**
- Daily automatic remote publishing: **pending D055 sync + 排程重排**
- Stable gate: **not started**（9/9 仍是 ⏸️，要等 9/10 完整 nightly 才能算 day 1）

---

_Generated by Mavis on 2026-09-10T10:35 GMT+8_
_Phase 1b 完成：runtime/git 追查，無 code 改動，無 commit_
