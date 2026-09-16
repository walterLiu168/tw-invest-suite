# D056 deployment acceptance — 2026-09-16

Status: In progress. Source tests and partial real executions do not prove final publication.

## Scope and authorization

Walter authorized necessary feature fixes, source pushes, publication and Scheduler updates. Preserve all unrelated changes, especially the AI-Telegram working tree. Core scope: the entire ticker site, 24-pick watchlist, patterns, publication, final reports and their upstream data prerequisites. Experimental opt-in stages remain outside the default pipeline contract.

## Verified evidence

- Primary source commit dc5c60a pushed to origin/main.
- Native PowerShell 5.1 revealed Hashtable Measure-Object does not find To. Replaced with explicit budget accumulation; actual native acceptance/rejection tests pass.
- 108 primary tests passed after date, missing-value, health and publication-retry changes.
- Real isolated 2330 HTML: C:\Users\icemo\Projects\tw-report-identity-94chw_m3\2330.html; 83,811 bytes, actual data date 2026-09-16.
- Deep-dive preserves unavailable values, real zero returns, supplied market cap, calendar-day price returns and volume in lots. Report history and DB basic queries use the frozen date; header labels the actual OHLCV date.
- Final publisher verifies both dashboard.md and daily_summary_{data_date}.md; identical Git content is retryable and failures preserve run identity.
- Weekly manual normal downloader DB_VERIFY: expected=1949 complete=1949 missing=0. Independent SQL: 2026-09-16 daily rows=1949, positive shares=1949.
- RSS full normal writer: 71 raw, 10 derived, zero errors. Independent SQL raw total=187393, latest created_at=2026-09-16 11:41:10 UTC (19:41:10 Taipei).
- AI-Telegram selective commit 836edc4 pushed to existing experiment/minerva-validation-calibrated-20260625 branch. Only two owned source hunks and scoped PLAN/BUGS/CHANGELOG entries were staged; staged-source self-check passed. Other local changes remain untouched.
- Real nightly-health task last execution 2026-09-16 19:43:43, LastTaskResult=0. Expanded 22:30–02:00 triggers installed earlier.
- Existing published ticker UI: all 18 tabs switch, no JavaScript errors. Fresh release UI still requires validation.

## Explicitly stopped validation

Run 1a159eaa1bf44ca78a28a7804b0d3aa8 was intentionally terminated to fix confirmed report-content defects. Owner 32296, wrapper 31560 and child 8356 are gone. It did not certify completion. Production HTML was partially overwritten and must be fully regenerated before publication.

## Next gates

1. Commit/push owned primary changes, synchronize all managed runtime sources and verify SHA equality.
2. Apply reviewed existing-task registrar: health ordinary script, UTF-8 upstream actions, Weekly weekday 21:10, wake/catch-up and one failed-task retry. Trial S4U with actual Scheduler executions; preserve original XML for rollback.
3. Verify actual Weekly/RSS task result and data landing in the updated context.
4. Start a new default full daily-report Scheduler run. Observe exact UUID, process handles, stage heartbeats and artifacts; never restart solely because observation timed out.
5. Certify every required stage, entire render universe, committed 24 picks, dates and hashes.
6. Execute actual scheduled publisher and postflight; independently verify GitHub Pages and GrooveLab, selected pages, manifest, final reports and UI.
7. Audit remaining schedule dependencies and data warnings before claiming completion.
