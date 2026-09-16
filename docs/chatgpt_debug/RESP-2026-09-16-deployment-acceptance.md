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

## Additional semantic hardening

- Fixed percentage/fraction mismatch: long_drawdown now requires ret_240d < -30%, rather than -0.3%. Current and historical classification reuse the same predicates and calendar-day horizons.
- Missing moving averages cannot confirm up/down trends. The margin candidate's minimum volume is 100 lots (100000 stored shares).
- Fixed forward-horizon off-by-one and excluded returns beyond the frozen data date. Real read-only 2330 verification: entry 2026-06-01, twentieth following observation 2026-06-30, return 2.3354564756%; a cutoff one observation earlier excludes the unfinished return.
- Fixed watchlist market-cap divisor (1e8 per 億), volume labels, margin chart units and ticker margin-change units. Missing returns/backtest statistics are no longer fabricated as zero.
- Corrected three-day foreign buying to require all three daily flows positive. The nonannualized mean/std ratio is labelled accurately rather than Sharpe.
- Tabbed ticker history now provides 240 trading observations. Four Windows process workers retain the same output/failure contract and do not make parallel API requests.
- Isolated worker acceptance: C:\Users\icemo\Projects\tw-worker-acceptance-e_33rkw1, four real cached tickers; serial 10.4s / parallel 4.7s, generated content equal after generation-time normalization.
- 10 semantic/worker tests pass. Full suite after these additions is being rerun.

## Scheduler configuration limitation

The legitimate RunAs elevation attempt returned 操作被使用者取消. `register_verified_pipeline.ps1` has not run; health action, Weekly timing, UTF-8 actions, S4U, wake and retry changes remain pending. Do not claim they were applied or silently bypass elevation. Existing nightly-health trigger expansion remains installed.

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
