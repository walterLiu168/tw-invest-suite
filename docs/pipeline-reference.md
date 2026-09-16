# Daily pipeline reference — D056-2 hardening

Updated: 2026-09-16. Runtime and repository copies of scheduled files must have identical SHA-256.

## Source boundaries

- Repository: `C:\Users\icemo\Projects\tw-invest-suite`
- Scheduler runtime: `C:\Users\icemo\.claude\skills\tw-invest-suite\scripts`
- Render output: `C:\Groove-Lab\analyze`
- Published files: a fresh staging directory, populated from the completion marker's exact artifact paths and SHA-256 values.
- Daily report, completion, watchdog, publication and postflight helpers are ordinary versioned `scripts/*.py` files. The independent health-check Scheduler action still points to its legacy runtime `_debug/check_openalice_health.py`; do not confuse that diagnostic with daily completion evidence.

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
| watchlist | 10 min | Yes |

`-Mode render` skips maintenance and still runs the complete rendering chain.
`-IncludeAdvancedStages` restores stages 7–17 in both full and render modes. These are opt-in, including the pre-existing push stage.
`-Mode publish` uses the same certified publisher as the scheduled job.

The default worst-case stage budget is 180 minutes. Scheduler daily-report has a four-hour limit; publication has a separate wait budget.

## Completion contract

`pipeline_state.py begin` writes `pipeline_run.json` before preflight. A new attempt immediately invalidates an older successful marker for publishing. The data date comes from DB, and must agree with the independently expected trading session. It is frozen for the run.

`pipeline_state.py complete --stages ...` requires:

1. All required stages succeeded; optional failures are recorded accurately.
2. The same screen run and exactly 24 active picks, with three long and three short in each of four price buckets.
3. At least 1,900 current OHLCV tickers.
4. A receipt for the entire metadata render universe; no renderer exception may be hidden. Non-selected stocks with unavailable/stale quotes remain in the site with an explicit warning; selected picks may not have stale quotes.
5. Patterns for this nightly and data date, and watchlist HTML containing the exact committed pick identities.
6. Runtime/repo source hashes unchanged during execution.
7. All published core artifacts have recorded SHA-256 values.

It atomically writes `last_completed.json` (version `D056-2`) only after these checks. Failed or interrupted runs cannot reuse a previous marker.

## Publication

`publish_ghpages.py` defaults to local preparation; `--publish` is the scheduled mode. `publish_ghpages_daily.ps1 -PrepareOnly` performs the full gate and staging without pushing.

The publisher overlays certified artifacts onto a fresh staging directory, verifies every staged artifact hash, and uses a fast-forward Git push to `gh-pages`. Its local Git configuration and `info/attributes` preserve the certified bytes, including CRLF, regardless of Windows autocrlf defaults. No force push is needed. It verifies the remote manifest, watchlist, patterns, JSON and all selected ticker pages by byte hashes. Only then is the publication receipt marked verified.

The same job runs final postflight and publishes the morning dashboard in a second bounded status commit. Dashboard bytes are checked remotely too. The status report is not part of the immutable analytical-artifact manifest, avoiding a self-referential hash.

Source commits stay local until Walter approves `git push origin main`. Do not run an ad-hoc `--publish` as part of a local repair without publication authorization.

## Reports and evidence

- `_debug/pipeline_run.json`: current attempt, status, owner PID and source hashes.
- `_debug/last_completed.json`: certified analytical artifacts and data/run identities.
- `analyze/render_receipt.json`: expected/rendered universe, exact files, failures and stale-data warnings.
- `_debug/prepared_release.json`: local staging path and identity.
- `_debug/publication_result.json`: publication commit and verified remote paths.
- `_debug/postflight_latest.json`: current local/final checks, phase and warnings.
- `public/data/dashboard.md`: current operational status; no green without this nightly's certified completion and remote publication evidence.

`chips`, `sectors` and `concepts` are opt-in/manual pages. Their HTTP availability is not evidence of daily freshness.

## Verification

```powershell
C:\Python314\python.exe -B -m unittest discover -s tests -p test_daily_pipeline.py -v
powershell.exe -NoProfile -File scripts\publish_ghpages_daily.ps1 -PrepareOnly
```

Tests cover PowerShell 5.1 argument boundaries, whitespace, child errors, timeouts, old/failed/watchdog markers, altered artifacts, exact pick identity with optional margin cards, calendar closures, and false-green status. Publication checks include an actual local HTTP server serving a stale selected page, actual Git staging under Windows autocrlf, prepare-only behavior, and remote verification failure.

## Known data issues

FinMind weekly, Weekly Shareholding 1330, cloudflared, and ticker 7768 classification remain separately visible. No schema migration or quarantine row deletion is part of this hardening.

The 2026 session calendar is sourced from [TWSE's official holiday schedule](https://www.twse.com.tw/holidaySchedule/holidaySchedule?response=html). Unscheduled closures need an explicit update. Unknown calendar years fail closed and must be reviewed before use.
