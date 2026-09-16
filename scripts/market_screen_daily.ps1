# market_screen_daily.ps1 — D052g / D052h
# Daily 18:00 cron: run market screen, write market_screen_runs +
# market_screen_picks, generate reports.
# Schedule: daily 18:00 (after OHLCV 17:35+17:55, before daily-report 22:25).
# Uses git repo's market_screen_runner.py which:
#   - skips on weekends
#   - verifies data_date from daily_data2_full
#   - validates 24 picks + 4 buckets + both long/short
#   - persists to market_screen_runs + market_screen_picks (idempotent on data_date)
#   - closes older active picks only after new run succeeds
#   - generates MD + HTML + deep-dive prompt reports
$ErrorActionPreference = "Continue"
$env:PYTHONIOENCODING = "utf-8"
$RunnerScript = "C:\Users\icemo\Projects\tw-invest-suite\scripts\market_screen_runner.py"
$LogDir = "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug"
$LogFile = Join-Path $LogDir ("market_screen_" + (Get-Date -Format "yyyyMMdd_HHmmss") + ".log")

# Preflight: verify runner script + log dir all exist
if (-not (Test-Path $RunnerScript)) {
    Write-Error "FATAL: market_screen_runner.py not found at $RunnerScript"
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

Log-Msg "=== market_screen_daily.ps1 start ==="
Log-Msg "  Runner script: $RunnerScript"
Log-Msg "  Log file: $LogFile"

try {
    & C:\Python314\python.exe -X utf8 $RunnerScript 2>&1 | ForEach-Object { Log-Msg $_ }
    if ($LASTEXITCODE -ne 0) { throw "market_screen_runner.py exit $LASTEXITCODE" }
    Log-Msg "=== market_screen_daily.ps1 OK ==="
} catch {
    Log-Msg "=== market_screen_daily.ps1 FAILED: $_ ==="
    exit 1
}
exit 0
