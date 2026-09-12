# publish_ghpages_daily.ps1 — D047 daily 00:30 cron
# Push tw-invest-suite public/ to gh-pages branch (GitHub Pages).
# Run AFTER daily run 22:25 finishes (Stage 99 publish_analyze_ghpages.py goes to old stock-report repo;
# this one goes to tw-invest-suite).
#
# D056 P0-3 + P0-4: data_date comes from _debug/last_completed.json (the completion
# marker written by run_daily.ps1 when all REQUIRED stages succeeded). NEVER use
# Get-Date / AddDays(-1) to guess — at 00:30 next day, that gives the wrong date.

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

# D056 P0-3/P0-4: read data_date from completion marker (NEVER guess).
$markerPath = "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug\last_completed.json"
if (-not (Test-Path $markerPath)) {
    Log-Msg "FATAL: completion marker not found: $markerPath"
    Log-Msg "       (run_daily.ps1 didn't complete — required stage(s) failed)"
    exit 1
}
$marker = Get-Content -Path $markerPath -Raw -Encoding UTF8 | ConvertFrom-Json
$dataDate = $marker.data_date
if (-not $dataDate) {
    Log-Msg "FATAL: marker has no data_date: $markerPath"
    exit 1
}
Log-Msg "D056 P0-3: data_date from marker = $dataDate  (run_id=$($marker.run_id) status=$($marker.status))"

# D056: if marker status != ok, refuse to push
if ($marker.status -ne "ok") {
    Log-Msg "FATAL: marker.status=$($marker.status), not 'ok' — refusing to push"
    exit 1
}

# D054-fixup: build publish_manifest.json for data_date (now from marker, not Get-Date)
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
