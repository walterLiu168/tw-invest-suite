# publish_ghpages_daily.ps1 — D047 daily 23:50 cron
# Push tw-invest-suite public/ to gh-pages branch (GitHub Pages).
# Run AFTER daily run 22:25 finishes (Stage 99 publish_analyze_ghpages.py goes to old stock-report repo;
# this one goes to tw-invest-suite).

$ErrorActionPreference = "Continue"
Set-Location "C:\Users\icemo\Projects\tw-invest-suite\scripts"

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$logFile = "_debug\publish_ghpages_${ts}.log"

function Log-Msg {
    param([string]$msg)
    $ts2 = Get-Date -Format "HH:mm:ss"
    $line = "[$ts2] $msg"
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}

Log-Msg "=== publish_ghpages_daily.ps1 start ==="
Log-Msg "Running publish_ghpages.py (tw-invest-suite repo)..."

python publish_ghpages.py 2>&1 | ForEach-Object { Log-Msg $_ }

$exitCode = $LASTEXITCODE
Log-Msg "=== publish_ghpages_daily.ps1 done (exit $exitCode) ==="
exit $exitCode
