# Daily pipeline reference — D056-2 hardening

Updated: 2026-09-16. Runtime and repository copies of scheduled files must have identical SHA-256.

## Source boundaries

- Repository: `C:\Users\icemo\Projects\tw-invest-suite`
- Scheduler runtime: `C:\Users\icemo\.claude\skills\tw-invest-suite\scripts`
- Render output: `C:\Groove-Lab\analyze`
- Published files: a fresh staging directory, populated from the completion marker's exact artifact paths and SHA-256 values.
- Daily report, completion, watchdog, publication and postflight helpers are ordinary versioned `scripts/*.py` files. The health-check replacement is also versioned; its action update is prepared in `register_verified_pipeline.ps1` and awaits Windows elevation. Diagnostics do not certify completion.

## Schedule and dependency

| Time | Task | Behavior |
|---|---|---|
| 18:10 | metadata-backfill | Existing metadata maintenance |
| 18:20 | market-screen | Commit 24 picks; verified TWSE session calendar |
| 22:25 | daily-report | Begin run identity, render and certify artifacts; no Git push |
| 22:30 | yfinance | Existing independent cache refresh |
| 23:00 | health-check | Existing source-health diagnostics; failures remain visible |
| 23:25 | company-refresh | Existing company metadata refresh |
| 23:30 | sync-legacy | Existing legacy sync |
| 23:55 | marker-watchdog | Check current completion; report a live process as pending; NEVER create a success marker from picks |
| 22:30–02:00 every 30 min; 02:30 / 04:00 / 06:00 | nightly-health | Check exact owner creation identity, stage heartbeat deadlines and between-stage gaps; guarded recovery kills the owner tree, never auto-publishes |
| 00:05 | postflight | Local/pre-publication checks and dashboard; remote verification is not claimed yet |
| 00:30 | publish | Wait up to 130 minutes for daily-report, verify marker, prepare immutable site, publish, verify remote hashes, run postflight, publish final dashboard |

## Nightly stages

| Stage | Default timeout | Required |
|---|---:|---|
| finmind_maint | 10 min | Yes on trading-session full runs |
| render | 90 min | Yes |
| patterns | 30 min | Yes |
| patterns_html | 10 min | Yes |
| margin_scan | 30 min | No; retain nonzero result as degraded |
| watchlist | 30 min | Yes; supplemental fetches are serial, bounded to 45s per ticker and 360s overall |
| all_reports | 30 min | Yes; sectors, chips, advanced chips, concepts, 30 session history, metadata and OG |

`-Mode render` skips maintenance and still runs the complete rendering chain.
`-IncludeAdvancedStages` remains accepted for older callers. All reports now run by default in both full and render modes. Telegram sends only after both sites and final postflight verify.
`-Mode publish` uses the same certified publisher as the scheduled job.

The default worst-case stage budget is 230 minutes. Configurations exceeding 235 minutes are rejected, reserving five minutes under the four-hour Scheduler cap. Publication has a separate wait budget.

## Completion contract

`pipeline_state.py begin` writes `pipeline_run.json` before preflight. A new attempt immediately invalidates an older successful marker for publishing. The data date comes from DB, and must agree with the independently expected trading session. It is frozen for the run.

`pipeline_state.py complete --stages ...` requires:

1. All required stages succeeded; optional failures are recorded accurately.
2. The same screen run and exactly 24 active picks, with three long and three short in each of four price buckets.
3. At least 1,900 current OHLCV tickers.
4. A receipt for the entire metadata render universe; no renderer exception may be hidden. Non-selected stocks with unavailable/stale quotes remain in the site with an explicit warning; selected picks may not have stale quotes.
5. Patterns for this nightly and data date, and watchlist HTML containing the exact committed pick identities.
6. Runtime/repo source hashes unchanged during execution.
7. All published artifacts have recorded SHA-256 values.
8. The all-report receipt matches UUID/date, the metadata universe, canonical current rows, 30 history dates and the exact 42 advanced artifacts.

It atomically writes `last_completed.json` (version `D056-3`) only after these checks. Failed or interrupted runs cannot reuse a previous marker.

Certification is terminal. `fail_run` cannot change the same certified attempt from ok to failed; an older marker cannot protect a newer failed attempt. A Windows state mutex serializes begin, completion and watchdog recovery. Post-certification reporting errors are warnings and cannot invalidate analytical success.

`run_stage.py` writes a heartbeat every 15 seconds and records stage start, deadline and completion. Both the wrapper and child streams go directly to files. The watchdog permits valid stages beyond 90 minutes total, detects a five-minute gap after a completed stage, and never kills a run merely because an old log is quiet. Process creation identity prevents acting on a reused owner PID.

`nightly_health.py` is versioned under scripts; the scheduled wrapper no longer depends on an ignored `_debug` helper. The 22:30–02:00 trigger expansion and wake/S4U deployment were applied on 2026-09-16. Enabled analytical/data dependency tasks also received S4U/wake, preserving disabled old aliases. Actual updated-context checks are recorded in the deployment acceptance document.

## Publication

`publish_ghpages.py` defaults to local preparation; `--publish` is the scheduled mode. `publish_ghpages_daily.ps1 -PrepareOnly` performs the full gate and staging without pushing.

The publisher overlays certified artifacts onto a fresh staging directory, verifies every staged artifact hash, and uses a fast-forward Git push to `gh-pages`. Its local Git configuration and `info/attributes` preserve the certified bytes, including CRLF, regardless of Windows autocrlf defaults. No force push is needed. It verifies the remote manifest, watchlist, patterns, JSON and all selected ticker pages by byte hashes. Only then is the publication receipt marked verified.

The same job runs final postflight and publishes the morning dashboard and daily summary in a second bounded status commit. Both reports are checked remotely even on an identical-content retry. Receipts retain the analytical and final status commit identities. The status reports are not part of the immutable analytical-artifact manifest, avoiding self-referential hashes.

Walter authorized source pushes, publication and necessary Scheduler updates on 2026-09-16, and authorized the final UAC retry with Sep17 `continue`. Current deployment evidence and remaining gates are recorded in `docs/chatgpt_debug/RESP-2026-09-16-deployment-acceptance.md`. The installed `publish_verified_sites.ps1` verifies canonical publication and postflight before `sync_groove_release.py` copies certified stock paths and verifies Groove remote hashes. It preserves the music application's root index and configuration. Sep17 legitimate UAC deployment returned 0; the live Scheduler action points to this wrapper with S4U and wake enabled. Actual end-to-end publication still requires a fresh certified full run.

Managed provenance covers 43 runtime scripts and 14 repository report/maintenance modules. The render universe is frozen at begin and compared with both the current metadata universe and exact artifact identities at completion. Native stage waits use fresh process lookup and creation identity; ordinary logging writes to the file before optional verbose output.

Cross-logon S4U monitoring falls back to bounded CIM when OpenProcess is denied. It compares process creation identity and rejects PID reuse; CIM errors remain unknown. Each stage wrapper also monitors its exact parent and kills its child tree within its heartbeat interval if Scheduler stops that parent, preventing orphan writers.

Margin maintenance requests use the frozen nightly date. The dated fetch receipt must match this nightly, contain provider rows and report no API errors. Its source may lag by one official trading session; reports display the actual source date and an explicit lag warning. Older or future source dates fail certification.

## Report data semantics

- Rendering uses four independent processes, preserving per-ticker failures and the same receipt contract. DB/cache assembly remains serial; this does not parallelize FinMind calls.
- Ticker history uses the frozen upper date and displays the actual OHLCV data date; tabbed backtests receive up to 240 trading rows.
- Volume and institutional flows are stored in shares and displayed in lots (1000 shares). Margin/short balances are already stored in lots and are not divided again.
- Screener/pattern 60/120/240/500-day returns use calendar-day cutoffs; pattern 20-day returns use trading observations. The watchlist labels its 20-day excess return separately from raw calendar-day price returns.
- Historical pattern signals reuse the current predicate and return horizons. Forward 20/60-day returns require the full holding period within the frozen date. Pattern backtest sampling covers up to 240 trading sessions; its current-cohort/200-ticker scope is explicit. Historical valuation and margin-cost backtests remain unavailable where point-in-time inputs are absent.
- Missing valuation/return/backtest inputs display as unavailable, preserving real zero returns. Sample win rates alone do not prove statistical significance.

## Reports and evidence

- `_debug/pipeline_run.json`: current attempt, status, owner PID and source hashes.
- `_debug/last_completed.json`: certified analytical artifacts and data/run identities.
- `analyze/render_receipt.json`: expected/rendered universe, exact files, failures and stale-data warnings.
- `_debug/prepared_release.json`: local staging path and identity.
- `_debug/publication_result.json`: publication commit and verified remote paths.
- `_debug/postflight_latest.json`: current local/final checks, phase and warnings.
- `_debug/stage_logs/*_<nightly_id>_stage*.heartbeat.json`: active stage deadlines and exit evidence; unrelated old attempts are ignored.
- `public/data/dashboard.md`: current operational status; no green without this nightly's certified completion and remote publication evidence.

`chips`, `sectors` and `concepts` are opt-in/manual pages. Their HTTP availability is not evidence of daily freshness.

## Verification

```powershell
C:\Python314\python.exe -B -m unittest discover -s tests -p test_daily_pipeline.py -v
powershell.exe -NoProfile -File scripts\publish_ghpages_daily.ps1 -PrepareOnly
```

Tests cover PowerShell 5.1 argument boundaries, whitespace, child errors, timeouts, old/failed/watchdog markers, altered artifacts, exact pick identity with optional margin cards, calendar closures, and false-green status. Publication checks include an actual local HTTP server serving a stale selected page, actual Git staging under Windows autocrlf, prepare-only behavior, and remote verification failure.

Final hardening tests (`tests/test_final_hardening.py`) inject reporting failures after certification, a hung supplemental worker, noisy consecutive native stages, child/grandchild timeouts, owner PID reuse and watchdog recovery. They execute the actual PowerShell Scheduler query. Historical manifest tests no longer delete their own module during import.

## Diagnostic retention

Keep current run/marker/publication receipts and all referenced evidence. Retain stage logs for 30 days locally; archive older logs for 90 days before an operator-approved deletion. Never clean logs as part of detection/recovery or while their owner is active. No automatic cleanup or new cleanup cron is installed; old runs are filtered by nightly_id, so retention is independent of health classification.

## Known data issues

Weekly shares passed same-day DB coverage 1949/1949 and actual S4U execution; the legacy task name remains while its weekday trigger is 21:10. Groove boot recovery was installed and proved by controlled owned-process recovery. Ticker 7768 metadata was resolved against the official TWSE listing notice, retaining all 13 quarantine records. Canonical maintenance dates and unregistered legacy domain snapshots remain separately visible. No schema migration or quarantine row deletion is part of this hardening.

The 2026 session calendar is sourced from [TWSE's official holiday schedule](https://www.twse.com.tw/holidaySchedule/holidaySchedule?response=html). Unscheduled closures need an explicit update. Unknown calendar years fail closed and must be reviewed before use.

## All-report automation and Telegram (2026-09-17)

The required `src/all_reports.py` stage reads one canonical `daily_data2_full` snapshot for 30 trading sessions and `industry_type` for the full metadata universe. Existing report builders reuse this input instead of independently fetching empty/error-prone API windows. Dealer data is combined net, without invented gross buys/sells or proprietary/hedging splits. Complete 20-session positive closing prices are required for the advanced proxy; omitted ticker counts are recorded. The proxy is positive net-flow weighted closing price, not actual institutional transaction VWAP or holding cost.

Both sites verify all advanced HTML, JSON, history, OG and dated market reports by SHA. The publisher then invokes `src/chip_push.py`, loading the existing backend AI-Telegram shared/local/environment config. User explicitly authorized the existing bot/chat send on Sep17. A delivery ledger keyed by data date and chat hash prevents duplicate successful daily sends. API `ok`, a message ID and matching response chat are required. Missing credentials fail rather than silently skip. An uncertain response blocks automatic re-send and requires receipt review, because Telegram does not provide an idempotency key.

Physical wake from sleep/reboot remains distinct from enabled WakeToRun/S4U settings; acceptance must state which evidence was actually obtained.
