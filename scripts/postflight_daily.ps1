# postflight_daily.ps1 — D052h K
# Daily 00:05 postflight: verify all 8 tw-invest-suite-* tasks ran today
# and data integrity invariants hold.
$ErrorActionPreference = "Continue"
$env:PYTHONIOENCODING = "utf-8"
$Runner = "C:\Users\icemo\Projects\tw-invest-suite\scripts\postflight_daily.py"
$LogDir = "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug"
$LogFile = Join-Path $LogDir ("postflight_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")

if (-not (Test-Path $Runner)) {
    Write-Error "FATAL: postflight_daily.py not found at $Runner"
    exit 1
}
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Log-Msg {
    param([string]$msg)
    $ts2 = Get-Date -Format "HH:mm:ss"
    $line = "[$ts2] $msg"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

Log-Msg "=== postflight_daily.ps1 start ==="
try {
    & C:\Python314\python.exe -X utf8 $Runner 2>&1 | ForEach-Object { Log-Msg $_ }
    if ($LASTEXITCODE -ne 0) { throw "postflight_daily.py exit $LASTEXITCODE" }
    Log-Msg "=== postflight_daily.ps1 OK ==="
} catch {
    Log-Msg "=== postflight_daily.ps1 FAILED: $_ ==="
    exit 1
}
exit 0
