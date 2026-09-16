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

## Scheduler configuration applied

The first legitimate RunAs attempt was cancelled. Walter authorized retry with "continue"; the second UAC invocation completed at 20:14:58, process 29212, exit 0. All six existing-task changes were applied, including wake, ordinary health action, UTF-8, Weekly weekday 21:10, S4U and scoped retry settings. XML backups and transcript are under scripts/_debug/scheduler_backup_20260916.

After application, actual S4U Weekly execution at 20:17:17 completed with LastTaskResult=0. RSS and health-check executions in the updated context are being observed. The current daily-report instance began before the principal change and does not prove a new S4U execution context.

## Live full validation and site recovery

- Primary commits 44a153f and bd81e3b are pushed to origin/main. All 30 managed source hashes matched repo/runtime before the current run. Full suite: 118 tests passed; final pattern lookback adjustment additionally passed the 10 semantic tests and compilation.
- Actual daily-report UUID 83217e7ab18343adbe50968f625e251d, data_date=2026-09-16, run_id=17, picks=24. Owner 30508 / wrapper 25784 / renderer 26076. Assemble 1973/1973 in 202s; rendering 600/1973, failures=0 at the latest observation. No managed-source edits while this run is live.
- GrooveLab 1033 was reproduced in the browser. The configured named connector and existing origin were absent; ordinary hidden processes restored the existing config and server (connector 21416, origin 21172). The separate existing Cloudflared Windows service was preserved.
- Browser now opens https://groovelab.dev/watchlist.html and correctly displays the previous 2026-09-15 watchlist. Fresh release validation remains pending.
- Prepared ordinary groove_service_watch.ps1 and register_groove_service.ps1 for boot and process recovery. Native PowerShell parser and actual healthy -Once probe passed. Startup task installation and owned-process recovery acceptance remain pending.

## Subsequent acceptance

- Updated-context S4U Weekly, RSS and health-check all completed at 20:17:17 with LastTaskResult=0.
- GrooveLab Site Recovery installed via normal UAC, registrar 3008 exit 0; startup trigger with one-minute delay, S4U Limited, no execution cap. Live supervisor 19344 began 20:19:19. Exact creation identities of the manually started origin/connector were verified before their controlled stop. The supervisor recreated origin 26956 and connector 2828 at 20:20:10; both health probes passed at 20:20:40. This proves actual process recovery, not only task registration.
- TWSE official May 6 notice confirms 7768 頌勝科技, listing May 7, 半導體業: https://www.twse.com.tw/staticFiles/news/news/tsecnews/8a8216d69dbea9fd019dfc9546a8010d.pdf. The reviewed resolve_7768_official.py preview found 13 matching open events and 42 blank company rows. Transactional application inserted the canonical metadata, resolved all 13 without deleting records, and filled the 42 blank rows. Before/applied audit JSON is under scripts/_debug/7768-official-resolution. A repeated preview found 0 open / 0 missing company rows.
- The normal company-refresh Scheduler execution completed with result 0 and repaired 1948 additional latest-date company rows. The latest daily count remains 1949.
- Canonical source registry lists margin maintenance and stock margin in the daily lane. The seven old domain table aliases have no registry entries; their stale snapshots remain unregistered advisory data and are not proof of canonical freshness.
- Broader inventory found remaining enabled upstream/dependency tasks required an interactive logon and lacked wake settings. Prepared register_pipeline_dependencies.ps1 to preserve enabled/disabled state and triggers while applying S4U/wake to enabled existing analytical/data tasks. Disabled old aliases remain disabled. Python entrypoints receive UTF-8; company/metadata/screen/postflight/sync wrappers now use Python314 explicitly. The yfinance task receives an ordinary versioned cache-refresh entrypoint that fails on error or incomplete results. Native parsing and Python compilation passed. Registrar application and actual updated-context executions remain pending.
- Dependency registrar applied via UAC at 20:26:22, process 27940 exit 0; all 23 enabled existing tasks now have S4U/wake. Actual updated-context company-refresh, metadata-backfill, valuation cache and stock-news task executions at 20:27:27 completed with result 0. Valuation cache coverage: 1974 yfinance-source results, fallback=0, error=0; this source label includes valid cache hits and does not prove 1974 new network calls.
- Prepared sync_groove_release.py and publish_verified_sites.ps1 to verify canonical publication first, copy only certified stock paths, preserve the music application's index/configuration/data, then verify Groove remote SHA for both final reports and all selected pages. Four tests passed: exact copy/retry, pre-write source mismatch, path escape and protection of the music root. The publisher action update and actual fresh dual-site execution remain pending.

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

## Final source hardening before a new S4U acceptance run

- UUID 83217e7ab18343adbe50968f625e251d rendered 1973/1973 with zero failures and a terminal exit-0 receipt at 20:35:21. Its parent did not advance to Stage 3 after the renderer exited. The exact owner was stopped, and the attempt was marked failed; it has no completion certificate and must not be published.
- The root cause of that parent stall is unresolved. A native PowerShell 5.1 short probe of the original stage wait completed normally in 12.8 seconds. Fresh process lookup with creation-identity checks and file-first logging now harden lifecycle observation and remove ordinary console progress writes. A native probe of the new stage wait passed in 12.6 seconds. A full run in the updated S4U context remains necessary.
- Full primary suite: 131 tests passed. Maintenance tests reject provider errors, empty responses, wrong run identity, nonzero API errors and stale/future receipts. A regression test verifies completion acquires its state mutex before reading the run. A one-session canonical maintenance lag is allowed and displayed with its actual source date; it is not represented as same-day data.
- Managed provenance now covers 43 runtime scripts plus two repository maintenance modules (45 hashes), synchronized with a dated runtime backup and confirmed equal. The render ticker universe is frozen at begin and checked again at completion and marker verification. The next actual default full run remains pending.
- RSS dependencies have seven passing focused tests and actual updated-context RSS result 0 at 20:41:41. Reviewed active parser/writer and task-owned tracking prefixes were committed and pushed as 0b4adde on the existing AI-Telegram branch, with unrelated user changes preserved.
- Independent latest-date SQL: 2026-09-16 daily rows=1949, missing company=0; 7768 quarantine total=13, open=0. Actual S4U market-screen task at 20:58:58 returned 0 through its existing complete-run idempotency path (run_id=17, picks=24); this does not claim a new screening computation. The frozen metadata render universe is now 1974.
- The final publisher action update UAC was cancelled. The user choice to retry is pending; the installed publisher currently performs canonical publication. The two-site wrapper and mirror are prepared and tested but are not yet the installed action.

## S4U process identity acceptance

The actual default S4U attempt 89f4a2f3e9db451386d14859af59e83a began at 20:59:16, owner 15472, and successfully advanced from maintenance to render. Interactive monitoring could see the process through CIM but OpenProcess and Get-Process.StartTime were denied. This confirmed a false dead-owner result in the monitor. The attempt was stopped early; Scheduler stopped only its parent, leaving wrapper 23676 and renderer 29208. A normal UAC cleanup verified the same UUID and exact wrapper creation identity before terminating that owned tree; cleanup exit 0. The attempt is failed and un-certified.

Process identity now falls back to bounded CIM only on access denied, preserving creation identity and rejecting PID reuse. Unknown CIM failures propagate rather than being labeled dead. The original handle and CIM timestamps may differ by one microsecond from conversion; comparisons allow two microseconds. Four focused identity tests passed, including actual native/CIM identity comparison; the full suite before orphan cleanup changes passed 135 tests.

The stage wrapper now monitors its exact parent creation identity and terminates its child tree if Scheduler stops that parent. A real child/grandchild owner-termination acceptance test passed; all five focused identity/orphan tests passed in 16.6 seconds before the next source freeze and full S4U run.

## Current acceptance after source commit ddfc9fb

- Final full primary suite passed 136 tests in 53.5 seconds. All 45 managed hashes match; primary source ddfc9fb is pushed.
- Actual S4U default full UUID 8b3c60f2d38b45919de84f1e5aeff0e9 began 21:04:45, owner 32944 / creation 21:04:44.449974. Maintenance exit 0; parent advanced into render. Assemble 1974/1974 in 174 seconds; render 400/1974, zero failures at this observation. Managed source remains frozen. This is still running, not certified.
- Interactive nightly-health now reports this S4U owner healthy within its stage budget. All 23 enabled analytical/data tasks meet S4U/wake/catch-up; configuration snapshot is under scripts/_debug/scheduler_final_configuration.json.
- Normal 21:10 Weekly trigger completed with result 0. The 21:00 RSS trigger failed with an uncaptured cause; later read-only fetch succeeded. The 21:11:11 retry completed with result 0. New non-secret outcome receipt records 81 queries, fetched 1101, raw inserted 16, derived inserted 4, duplicates 193, skipped 0, missing projected links 3, errors 0. Receipt code is pushed as AI-Telegram b3df3a9; full source URLs remain in raw storage.
- Concise takeover instructions and remaining publication gates are in HANDOFF-2026-09-16-D056-remaining.md. The final dual-site action UAC choice remains pending.
