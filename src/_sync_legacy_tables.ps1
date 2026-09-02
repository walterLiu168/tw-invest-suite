# sync_legacy_tables.ps1 — wrapper for Task Scheduler 23:30
# Runs sync_legacy_tables.py against the latest daily_data2_full date.
# Logs to C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug\

$ErrorActionPreference = "Continue"
Set-Location "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts"

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = "_debug\sync_legacy_${ts}.log"

function Log-Msg {
    param([string]$msg)
    $ts2 = Get-Date -Format "HH:mm:ss"
    $line = "[$ts2] $msg"
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

Log-Msg "=== sync_legacy_tables.ps1 start ==="
Log-Msg "Running sync_legacy_tables.py ..."

python sync_legacy_tables.py 2>&1 | ForEach-Object { Log-Msg $_ }

Log-Msg "=== sync_legacy_tables.ps1 done (exit $LASTEXITCODE) ==="
exit $LASTEXITCODE
