# marker_watchdog_daily.ps1 — D056 P2
# Runs at 23:55 daily (5 min before publish 00:30).
# If completion marker from run_daily.ps1 is missing/stale, regenerate from latest DB.

$ErrorActionPreference = "Continue"
Set-Location "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts"

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = "_debug\marker_watchdog_${ts}.log"

function Log-Msg {
    param([string]$msg)
    $ts2 = Get-Date -Format "HH:mm:ss"
    $line = "[$ts2] $msg"
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

Log-Msg "=== marker_watchdog_daily.ps1 start ==="

python _debug\marker_watchdog.py 2>&1 | ForEach-Object { Log-Msg $_ }

$exitCode = $LASTEXITCODE
Log-Msg "=== marker_watchdog_daily.ps1 done (exit $exitCode) ==="
exit $exitCode
