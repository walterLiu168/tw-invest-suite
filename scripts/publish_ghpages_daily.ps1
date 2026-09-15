# The only scheduled publisher. Wait for the actual nightly, then certify and publish.
[CmdletBinding()]
param([switch]$PrepareOnly, [int]$WaitMinutes = 130)
$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
Set-Location 'C:\Users\icemo\Projects\tw-invest-suite\scripts'
$deadline = (Get-Date).AddMinutes($WaitMinutes)
while ((Get-ScheduledTask -TaskName 'tw-invest-suite-daily-report').State -eq 'Running') {
    if ((Get-Date) -ge $deadline) { Write-Error 'Nightly still running at publish deadline'; exit 1 }
    Start-Sleep -Seconds 15
}
& C:\Python314\python.exe pipeline_state.py verify
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
$log = Join-Path $PSScriptRoot "_debug\publish_ghpages_$ts.log"
$flag = if ($PrepareOnly) { '--prepare-only' } else { '--publish' }
& C:\Python314\python.exe publish_ghpages.py $flag 2>&1 | Tee-Object -FilePath $log
$rc = $LASTEXITCODE
Add-Content -LiteralPath $log -Value "publish_ghpages_daily.ps1 done (exit $rc)" -Encoding UTF8
exit $rc
