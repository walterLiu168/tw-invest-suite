# company_refresh_daily.ps1 — D052f + D052h-fixup4
# Refresh daily_data2_full.company from industry_type for last 7 days.
# Schedule: Task Scheduler daily 23:25 (before sync-legacy at 23:30 so the
# refreshed company flows into daily_data, daily_data2, chip_daily via
# sync_legacy_tables).
#
# D052h-fixup4: $Script now points to the git-repo path
# (C:\Users\icemo\Projects\tw-invest-suite\scripts\company_refresh.py).
# The previous runtime-path reference was broken — the file does NOT
# exist at C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\, so
# any cron fire would fail with FileNotFoundError. Test-Path fail-fast
# is added so a missing or relocated script aborts with a clear message
# before python is invoked.
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
$Script = "C:\Users\icemo\Projects\tw-invest-suite\scripts\company_refresh.py"
$LogDir = "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug"
$LogFile = Join-Path $LogDir ("company_refresh_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

# D052h-fixup4: fail-fast on missing script
if (-not (Test-Path $Script)) {
    Write-Error "[company-refresh-daily] FATAL: company_refresh.py not found at $Script"
    exit 1
}

Write-Output "=== company_refresh_daily $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
Write-Output "  Script: $Script"
try {
    & python $Script --days=7 2>&1 | Tee-Object -FilePath $LogFile
    if ($LASTEXITCODE -ne 0) { throw "exit $LASTEXITCODE" }
    Write-Output "=== company_refresh_daily OK ==="
} catch {
    Write-Error "company_refresh_daily FAILED: $_"
    exit 1
}
