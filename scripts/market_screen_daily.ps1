# market_screen_daily.ps1 — D052g
# Run the daily market screen: close prior picks, generate new picks,
# write market_screen_runs + market_screen_picks rows.
# Schedule: daily 18:00 (after OHLCV lands, before daily-report at 22:25).
# Per D052g finding: market_screen has not been run automatically since
# 8/12. Without this cron, the watchlist HTML and picks aging logic
# never update. 3 market_screen_runs rows exist (8/12, 8/31, 9/1) — all
# from manual / backfill triggers.
$ErrorActionPreference = "Continue"
$env:PYTHONIOENCODING = "utf-8"
Set-Location "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts"

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = "_debug\market_screen_${ts}.log"

function Log-Msg {
    param([string]$msg)
    $ts2 = Get-Date -Format "HH:mm:ss"
    $line = "[$ts2] $msg"
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

Log-Msg "=== market_screen_daily.ps1 start ==="
Log-Msg "Running run_market_screen.py ..."
python run_market_screen.py 2>&1 | ForEach-Object { Log-Msg $_ }

Log-Msg "=== market_screen_daily.ps1 done (exit $LASTEXITCODE) ==="
exit $LASTEXITCODE
