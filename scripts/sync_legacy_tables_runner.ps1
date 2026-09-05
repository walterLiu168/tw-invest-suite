# sync_legacy_tables_runner.ps1 — D052h
# Wraps git repo's sync_legacy_tables.py (which patches runtime version
# to skip close-picks SQL).
# Schedule: daily 23:30 (before publish at 23:50).
$ErrorActionPreference = "Continue"
$env:PYTHONIOENCODING = "utf-8"
$RunnerScript = "C:\Users\icemo\Projects\tw-invest-suite\scripts\sync_legacy_tables.py"
$LogDir = "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug"
$LogFile = Join-Path $LogDir ("sync_legacy_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")

if (-not (Test-Path $RunnerScript)) {
    Write-Error "FATAL: sync_legacy_tables.py not found at $RunnerScript"
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

Log-Msg "=== sync_legacy_tables_runner.ps1 start ==="
Log-Msg "  Runner: $RunnerScript"
Log-Msg "  Log: $LogFile"

try {
    & python $RunnerScript 2>&1 | ForEach-Object { Log-Msg $_ }
    if ($LASTEXITCODE -ne 0) { throw "exit $LASTEXITCODE" }
    Log-Msg "=== sync_legacy_tables_runner.ps1 OK ==="
} catch {
    Log-Msg "=== sync_legacy_tables_runner.ps1 FAILED: $_ ==="
    exit 1
}
exit 0
