# nightly_health_daily.ps1 — D056-2 hardening
# Cron-driven stuck-nightly detector. Runs at 00:30, 02:30, 04:00, 06:00
# (configured by tw-invest-suite-nightly-health Scheduler task).
#
# If pipeline_run.json shows a nightly that is too old / orphan / stuck,
# this kills the PID and force-fails the state so the next cron can run.
# Does NOT auto-publish (per D056-2 spec: publish needs Walter's authorization).
$ErrorActionPreference = "Continue"
$env:PYTHONIOENCODING = "utf-8"
Set-Location "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts"

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$LogDir = "_debug"
$LogFile = Join-Path $LogDir ("nightly_health_" + $ts + ".log")

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

function Log-Msg { param([string]$msg); $ts2 = Get-Date -Format "HH:mm:ss"; $line = "[$ts2] $msg"; Write-Host $line; Add-Content -Path $LogFile -Value $line -Encoding UTF8 }

Log-Msg "=== nightly_health_daily.ps1 start ==="
Log-Msg "Mode: --kill (auto-recover stuck nightlies)"

# --kill flag: when stuck, kill PID + force-fail state.
# Without --kill, the watchdog is advisory only (cron-friendly exit codes).
& C:\Python314\python.exe _debug\nightly_health.py --kill --json 2>&1 | ForEach-Object { Log-Msg $_ }

$rc = $LASTEXITCODE
Log-Msg "=== nightly_health_daily.ps1 done (exit $rc) ==="
exit $rc