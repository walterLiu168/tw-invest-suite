# Both existing stock-report sites must verify before this Scheduler action succeeds.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$runtime = 'C:\Users\icemo\.claude\skills\tw-invest-suite\scripts'
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $runtime 'publish_ghpages_daily.ps1')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& C:\Python314\python.exe -X utf8 (Join-Path $PSScriptRoot 'sync_groove_release.py')
exit $LASTEXITCODE
