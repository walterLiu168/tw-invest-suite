# company_refresh_daily.ps1 — D052f
# Refresh daily_data2_full.company from industry_type for last 7 days.
# Schedule: Task Scheduler daily 23:25 (before sync-legacy at 23:30 so the
# refreshed company flows into daily_data, daily_data2, chip_daily via
# sync_legacy_tables).
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
$Script = "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\company_refresh.py"
$LogDir = "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug"
$LogFile = Join-Path $LogDir ("company_refresh_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Write-Output "=== company_refresh_daily $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
try {
    & python $Script --days=7 2>&1 | Tee-Object -FilePath $LogFile
    if ($LASTEXITCODE -ne 0) { throw "exit $LASTEXITCODE" }
    Write-Output "=== company_refresh_daily OK ==="
} catch {
    Write-Error "company_refresh_daily FAILED: $_"
    exit 1
}
