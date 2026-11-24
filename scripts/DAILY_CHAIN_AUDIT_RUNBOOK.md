# Daily Chain Audit Runbook

## Purpose

`daily_chain_audit.py` is the unattended, read-only release audit for the
tw-invest-suite and AI-Telegram chain. It does not require ChatGPT and does
not run the production pipeline. The target date is the previous landed
session selected by `market_calendar.py`; a current session whose provider has
not landed is reported as `WAITING_FOR_LANDED_SESSION`.

## Files

- `daily_chain_audit.py`: audit and JSON/Markdown receipts.
- `run_daily_chain_audit.cmd`: Task Scheduler launcher, with daily log files.
- `register_daily_chain_audit.ps1`: creates or replaces
  `tw-invest-suite-daily-chain-audit` at Asia/Taipei 06:30 using S4U,
  `WakeToRun`, `StartWhenAvailable`, `IgnoreNew`, and a two-hour limit.
- `daily_chain_audit_config.json`: non-secret paths, URLs and task names.
- `C:\Groove-Lab\automation\audit\latest.json` and `latest.md`: latest receipt.

## Install / verify

Run PowerShell as the account that owns the release:

```powershell
Set-Location C:\Users\icemo\Projects\tw-invest-suite\scripts
& .\register_daily_chain_audit.ps1
Get-ScheduledTask -TaskName tw-invest-suite-daily-chain-audit
```

The task is safe to run manually. Use `--dry-run` only as a label for an
operator invocation; the audit itself is always read-only.

## Exit codes

`0` healthy, waiting for a not-yet-landed session, recovered, or complete;
`10` degraded evidence; `20` failed evidence; `30` internal audit error.
The BAT preserves the Python exit code.

## Evidence checked

The receipt records official calendar/DB dates, D056-3 marker and publication
identity, postflight, manifest files and hashes (including the 50-report
minimum), DB price/chips coverage, AI canonical gate and four dated reports,
chips message ID and dedupe ledger, remote manifests, Scheduler XML settings,
and `powercfg /waketimers` output. Scheduler configuration and actual wake
events are intentionally reported separately. A mismatch is noted; the audit
never resends Telegram messages or modifies existing tasks.

## Troubleshooting

1. `WAITING_FOR_LANDED_SESSION`: wait for the provider and next scheduled run.
2. `DEGRADED`: read `latest.md`, then inspect the named receipt or task. Fix
   the upstream owner and let the normal pipeline recover; do not edit the
   audit receipt by hand.
3. `DB read-only check unavailable`: verify the protected `TW_DB_PASSWORD`
   environment is available to the scheduled account. No credentials are
   stored in this repository.
4. `powercfg` unavailable: this is separate from Task Scheduler settings and
   may require an elevated read-only check.

## Source/runtime release rule

Keep the source copy in `C:\Users\icemo\Projects\tw-invest-suite\scripts`
and the runtime copy in
`C:\Users\icemo\.claude\skills\tw-invest-suite\scripts` byte-identical.
After updates, compare SHA-256 for the Python, CMD, PS1 and JSON files before
registering the task.
