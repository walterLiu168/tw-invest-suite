# D056 — Nightly + Publish Hardening (P0)

**Date**: 2026-09-12  
**Status**: 6 P0 done, 6 VERIFY done, all 13 PASS  
**Branch**: local-only (awaiting Walter's `git push origin main`)

---

## 觸發事件（9/11 22:25 nightly → 9/12 follow-up）

- daily-report Stage 5 (`margin_scan`) 跑了 14h+ 卡死，9/11 nightly 後段全部跳過
- 9/12 00:05 postflight：canonical_fails=2（manifest + watchlist 還沒 push）
- 9/12 00:30 publish：manifest build FAIL — `no market_screen_runs for 2026-09-12`（用 Get-Date 抓到 9/12 但 daily-report 還沒跑 9/12）
- health-check 9/11 23:00：3 個 fail 沒分 RUNNING vs STUCK，把 `267009 還在跑` 誤判成 fail

---

## P0 議題 → 解法

### P0-1 Run-Stage redirected-pipe deadlock
**Root cause**: 舊 Run-Stage 用 `ProcessStartInfo.RedirectStandardOutput = true`（pipe）。當 child 寫超過 4KB 到 pipe buffer 就 block 住，但 parent 在 `WaitForExit(timeout)` 等 I/O 完成 → 雙方 deadlock。180m timeout 後 parent kill child，但 log 已經寫不出任何東西（stage 5 卡死 14h+ 就是這個）。

**Fix**: 改用 `Start-Process -RedirectStandardOutput/-RedirectStandardError <file_path>` 直接寫到檔案，沒有 pipe buffer。polling `$p.HasExited`（不用 `WaitForExit(timeout)`）避免 async reader hang。timeout 時 `Kill($true)` 砍 process tree。

### P0-2 margin_scan optional / degraded
Stage 5 改 `Optional=$true` + timeout 30min（從 180min）。失敗時記 "DEGRADED" + return `$true`，loop 繼續到 Stage 6+。`margin_scan` 會 hang 的問題不再阻塞 watchlist。

### P0-3 + P0-4 publish data_date 從 completion marker 傳入
- `daily-report` 跑完 stages 後，call `python _debug\write_completion_marker.py --date YYYY-MM-DD --status ok` 寫 `_debug/last_completed.json`
- marker 含 `data_date`, `run_id`, `picks_count`, `bucket_counts`, `git_head`, `completed_at`, `status`, `degraded_stages`
- 若 **任何 required stage 失敗就不寫 marker**，publish 就 exit 1
- `publish_ghpages_daily.ps1` 開頭 **read marker**，如果 marker 缺 / 壞 / status≠ok 就 `exit 1`（**不再用 Get-Date / AddDays(-1) 猜日期**）

### P0-5 health-check 267009 RUNNING vs STUCK
對於 `result == 267009`：
- `now - last_run < 5min` → 視為 RUNNING，不算 fail（daily-report 22:25 在 23:00 還在跑是正常的）
- `now - last_run ≥ 5min` → 視為 STUCK，fail
- 加進 `failures.append` 條件排除 `status.startswith("RUNNING")`

### P0-6 publish/remote verify 失敗必須 non-zero
- `publish_ghpages.py` 已 exit 1 on git push fail（line 25-26）
- `publish_manifest.py` 加 post-write re-verify：寫完再讀 + `verify_manifest_against_local`，錯就 exit 3/4
- `daily_summary.py` 已 exit 1 on canonical_failures
- `publish_ghpages_daily.ps1` 加 marker check，缺/壞/degraded 就 exit 1

---

## VERIFY 結果（13/13 PASS）

```
=== Summary ===
  PASS: 13
  FAIL: 0
ALL VERIFICATIONS PASSED
```

| VERIFY | 結果 |
|---|---|
| VERIFY-1 high-volume stdout child (100KB flood) | elapsed=0s, stdout=102600 bytes, stderr='DONE' |
| VERIFY-2 silent timeout child | elapsed=11s, killed via Kill(true) |
| VERIFY-2b no orphan python processes | (after force-kill) |
| VERIFY-3 cross-midnight data_date | marker=2026-09-11 ≠ Get-Date=2026-09-12 |
| VERIFY-4a missing marker → exit 1 | rc=1 |
| VERIFY-4b corrupted marker → exit 1 | rc=1 |
| VERIFY-4c status=degraded → exit 1 | rc=1 |
| VERIFY-5 DB 24 picks in 4 buckets | run_id=14, 4 buckets, total=24 |
| VERIFY-6 5 files SHA match (runtime == git) | run_daily.ps1, publish_ghpages_daily.ps1, publish_manifest.py, check_openalice_health.py, write_completion_marker.py |

---

## 改動的 files (6 + 1 report)

| File | Type | Lines |
|---|---|---|
| `scripts/run_daily.ps1` | modified | Run-Stage rewritten (file-based redirect, HasExited polling, Kill($true)); Stage 5 = Optional/$true; new completion marker write call after stages |
| `scripts/publish_ghpages_daily.ps1` | rewritten | Read completion marker, exit 1 if missing/corrupted/degraded |
| `scripts/publish_manifest.py` | modified | Post-write re-verify |
| `scripts/_debug/check_openalice_health.py` | modified | 267009 RUNNING vs STUCK logic (P0-5 from T4 era) |
| `scripts/_debug/write_completion_marker.py` | new | Writes `_debug/last_completed.json` with 24/4-bucket guard |
| `scripts/_debug/verify_d056.ps1` | new | 13 verifications |

---

## 待 follow-up（不在 P0 範圍，per Walter's "保持 PENDING"）

- 9/11 nightly 不得算 Stable Day 1（stage 5 卡死）
- Weekly Shareholding 1330 真失敗（exit code 2）
- 7768 quarantine（7 rows）
- FinMind BEHIND（`finmind_taiwan_total_margin_daily` 結構性 weekly cadence）
- cloudflared 1033
- production remote publish recovery（手動 gh-pages push bypass D054）

---

## Cron schedule 不變

```
22:25  daily-report     (D055 17 stages, D056 P0-1/P0-2 hardened)
23:00  health-check     (D056 P0-5 RUNNING vs STUCK)
23:25  company-refresh
23:30  sync-legacy
00:05  postflight
00:30  publish          (D056 P0-3/P0-4 reads marker)
```

Next cron: 9/12 22:25 daily-report（first run with P0-1/P0-2 hardened）.
