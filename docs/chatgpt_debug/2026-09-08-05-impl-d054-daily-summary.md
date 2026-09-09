# 2026-09-08-05: D054 daily_summary.py 實作

> Submitted: 2026-09-08 by Mavis (per PM 9.2 P0 publish manifest + 9.3 auto result summary)
> Status: 3/6 P0 fixes done in this batch
> Scope: closed-loop self-reporting
> No production push yet (local commit only, Walter 批准才 push)

## 範圍

D054 實作「每日閉環報告」— PM 9.2 P0 publish manifest + 9.3 自動結果摘要。

兩件事合在一個 cron 觸發：
1. **Manifest**：每次跑完整 postflight 後，生成 `daily_summary_YYYY-MM-DD.md`，包含 data_date、run_id、source commit、24 picks + bucket 分布、9 cron LastResult、artifacts SHA、DB integrity
2. **Remote verify**：fetch GitHub Pages watchlist.html / analyze.html / analyze/2330.html，確認 24 picks + 內嵌日期 = data_date

整合方式：postflight_daily.py (00:05) 跑完後呼叫 `daily_summary.write_summary(summary)`，不開新 cron。

## 修改清單

### 新檔案

**`scripts/daily_summary.py`** (13.5KB, 363 lines)
- `get_git_head()`: `git rev-parse HEAD` 拿 source commit SHA
- `get_latest_picks(data_date)`: SQL 拿 run_id、picks_count、bucket 分布、24 個 tickers
- `get_integrity_counts(data_date)`: SQL 拿 total rows、company NULL、quarantine open count
- `collect_artifacts(data_date)`: 掃描 `~/.claude/.../reports/market-screen-YYYY-MM-DD.{md,html}` + `deep-dive-prompts-YYYY-MM-DD.md` + `watchlist-full-YYYY-MM-DD.html`，算 SHA-256
- `remote_verify(data_date, expected_picks_count)`: urllib 抓 GitHub Pages 3 個 URL，驗證 date_in_body + rows>=20
- `render_summary_md(...)`: 渲染 markdown（DB integrity / picks / cron / checks / artifacts / remote / footer）
- `write_summary(postflight_summary)`: 寫 `~/.claude/.../reports/daily_summary_YYYY-MM-DD.md` + 複製到 `public/data/daily_summary_YYYY-MM-DD.md`（給 GitHub Pages）+ echo one-liner to stdout
- `if __name__ == "__main__"`: standalone test mode，讀最新 postflight log 跑

### 修改檔案

**`scripts/postflight_daily.py`** (+10 lines, integration only)
```python
# D054: write daily_summary_YYYY-MM-DD.md (manifest + remote verify)
try:
    from daily_summary import write_summary
    md_path = write_summary(summary)
    if md_path:
        print(f"[postflight] daily_summary written: {md_path}")
except Exception as e:
    # Don't fail postflight on summary write errors
    print(f"[postflight] WARN: daily_summary write failed: {e}")
```

放在 `log_file.write_text` 之後、`return` 之前。寫失敗不影響 postflight 的 exit code（postflight 還是看 9 cron + 5 check）。

## 驗證（9/9 10:34 手動跑 postflight_daily.py）

**輸出**：
```
[postflight] execution_date = 2026-09-08  data_date = 2026-09-08
[postflight] daily_summary written: C:\Users\icemo\.claude\skills\tw-invest-suite\reports\daily_summary_2026-09-08.md
```

**生成的 daily_summary_2026-09-08.md 摘要**（3.3KB）：
- **Status**: ❌ FAIL
- **DB**: 1955 rows, NULL=1 (7768), quarantine=5 (1 distinct)
- **24 picks**: run_id=11, buckets: <100=6, 100-300=6, 300-1000=6, >1000=6
- **9 crons**: health-check ✗ (LastResult=1), 其他 8 個 ✓
- **Artifacts**: 4 個檔 + SHA-256 (短 16 char)
- **Remote verify**:
  - watchlist.html: ✗ (`date_in_body=False, rows=24` — 證明 D053 還沒生效)
  - analyze.html: ✓
  - analyze/2330.html: ✓ (ticker report reachable, has_2026=True)

**重點發現**：watchlist remote verify 失敗（date_in_body=False）確認 GitHub Pages 上 watchlist.html 仍是 9/7 19:11 人工版，D053 P0-3 還沒在 cron 自動跑時生效。預期 9/9 22:25 daily-report 跑完後才會變綠。

## 設計決策

| 決策 | 理由 |
|---|---|
| 新檔案 daily_summary.py，不併入 postflight_daily.py | 關注點分離：postflight 專注 checks，daily_summary 專注 manifest。standalone test 模式方便 debug |
| 整合在 postflight 內，不開新 cron | PM 9.3「不是再新增 cron」 |
| 寫兩份（reports/ + public/data/）| reports/ 是唯讀人類 archive，public/data/ 讓 GitHub Pages 也能看 daily summary |
| 寫失敗不 fail postflight | daily_summary 失敗不該讓 postflight 整個失敗（PM 9.2 P0「失敗會主動報告」的反例）|
| 預期 picks_count=24 才標 ✓ | 容忍 20+（因為 watchlist.html 進場日排序可能少幾個 row） |
| 遠端 verify 容忍網路錯誤 | urllib 例外只記 ✗ + note，不 throw |

## 預期下次 cron 跑（9/10 00:05 postflight）

會自動：
1. 跑 postflight_daily.py（9 cron + 5 check）
2. 讀 postflight summary
3. daily_summary.write_summary(summary)：
   - SQL 查 9/9 picks (run_id=12)
   - 算 artifacts SHA
   - urllib 抓 GitHub Pages
4. 寫 `daily_summary_2026-09-09.md`（reports/ + public/data/）
5. echo `[daily_summary] 2026-09-09 ??? | run_id=12 picks=24 null=1 q=5 | md=daily_summary_2026-09-09.md`

## 待 Walter 批准

- [ ] 批准 commit 進 git
- [ ] 批准 push 到 origin/main
- [ ] 9/10 早上看 `daily_summary_2026-09-09.md` 確認 D053 P0-3 真的讓 watchlist remote verify 變 ✓
- [ ] 決定要不要把 daily_summary 改用 Telegram/email 通知（per PM 9.2 last item）

## Status

| Item | Status | Notes |
|---|---|---|
| daily_summary.py design | ✅ done | manifest + remote verify, A+C scope |
| postflight_daily.py integration | ✅ done | try/except, 不 fail postflight |
| Standalone test 9/8 | ✅ done | 3.3KB md, watchlist remote verify ✗ (預期) |
| Runtime mirror | ✅ done | daily_summary.py + postflight_daily.py 都 copy |
| Commit (local) | ⏸️ pending | 等 Walter 看本 MD |
| Push origin | ⏸️ pending | 等 Walter 批准 |
| 9/10 00:05 真實跑 | ⏸️ | 第一次整合測試 |
