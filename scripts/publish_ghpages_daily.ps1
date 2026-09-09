# publish_ghpages_daily.ps1 — D047 daily 23:50 cron
# Push tw-invest-suite public/ to gh-pages branch (GitHub Pages).
# Run AFTER daily run 22:25 finishes (Stage 99 publish_analyze_ghpages.py goes to old stock-report repo;
# this one goes to tw-invest-suite).

# D054-fixup: build publish_manifest BEFORE push so manifest + artifacts go in same commit
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

# D054-fixup: build publish_manifest.json for today (data_date)
$dataDate = Get-Date -Format "yyyy-MM-dd"
$manifestPath = "C:\Users\icemo\Projects\tw-invest-suite\public\data\publish_manifest_${dataDate}.json"
Log-Msg "D054-fixup: building publish_manifest for $dataDate at $manifestPath"
python publish_manifest.py --date $dataDate --write-to $manifestPath 2>&1 | ForEach-Object { Log-Msg $_ }
$manifestExit = $LASTEXITCODE
if ($manifestExit -ne 0) {
    Log-Msg "FATAL: publish_manifest.py exit $manifestExit — aborting publish (canonical manifest required before push)"
    exit $manifestExit
}

Log-Msg "Running publish_ghpages.py (tw-invest-suite repo)..."
python publish_ghpages.py 2>&1 | ForEach-Object { Log-Msg $_ }

$exitCode = $LASTEXITCODE
Log-Msg "=== publish_ghpages_daily.ps1 done (exit $exitCode) ==="
exit $exitCode
