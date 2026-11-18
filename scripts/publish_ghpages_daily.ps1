# The only scheduled publisher. Wait for the actual nightly, then certify and publish.
# WaitMinutes budget covers the typical 21:30 → about 23:02 nightly duration
# plus a safety margin. The 22:50 publisher normally waits about 12 minutes;
# a 130-minute budget gives it an absolute 01:00 deadline. Set to 10 only for manual one-off debugging
# when you know the chain is already finished.
#
# It also waits for the two producers that run after the nightly (company-refresh
# at 23:25 and sync-legacy at 23:30), because the postflight's company_null check
# reads the company names they fill in. Publishing before they run failed that
# check, which skipped the Groove-Lab sync and the Telegram push and left the live
# site one session behind until the after-midnight catch-up ran.
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

# Wait for the producers that run after the nightly. The postflight's
# company_null check needs daily_data2_full.company to be filled for the
# target date, and that is the company-refresh task at 23:25.
$nightlyInfo = Get-ScheduledTask -TaskName 'tw-invest-suite-daily-report' | Get-ScheduledTaskInfo
if ($nightlyInfo.LastRunTime.Date -eq (Get-Date).Date) {
    foreach ($producer in @('tw-invest-suite-company-refresh', 'tw-invest-suite-sync-legacy')) {
        $producerDone = $false
        while ((Get-Date) -lt $deadline) {
            $producerTask = Get-ScheduledTask -TaskName $producer -ErrorAction SilentlyContinue
            if ($producerTask) {
                $producerInfo = $producerTask | Get-ScheduledTaskInfo -ErrorAction SilentlyContinue
                if ($producerInfo -and $producerInfo.LastRunTime.Date -eq (Get-Date).Date) {
                    $producerDone = $true
                    break
                }
            }
            Start-Sleep -Seconds 20
        }
        if (-not $producerDone) { Write-Warning "$producer did not run today; the postflight may fail" }
    }
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
