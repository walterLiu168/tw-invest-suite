# yfinance_daily.ps1 — wrapper for Task Scheduler 22:30
# Runs yfinance_daily.py for all 1962 tickers.
# Timeout 90 min (yfinance takes 30-50 min for full batch).
# On DEAD yfinance (20+ consecutive failures), exits with code 2 for monitoring.

$ErrorActionPreference = "Continue"
Set-Location "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts"

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = "_debug\yfinance_${ts}.log"

function Log-Msg {
    param([string]$msg)
    $ts2 = Get-Date -Format "HH:mm:ss"
    $line = "[$ts2] $msg"
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

Log-Msg "=== yfinance_daily.ps1 start ==="
Log-Msg "Running yfinance_daily.py ..."

python yfinance_daily.py 2>&1 | ForEach-Object { Log-Msg $_ }

$exitCode = $LASTEXITCODE
Log-Msg "=== yfinance_daily.ps1 done (exit $exitCode) ==="
Log-Msg "  exit=0 → OK,  exit=2 → yfinance DEAD,  exit=1 → error"
exit $exitCode
