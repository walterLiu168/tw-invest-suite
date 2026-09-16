# tw-invest-suite daily report — fully autonomous batch
# Scheduled via Windows Task Scheduler: daily 22:25
# Runs without any agent interaction.
#
# Required: maintenance (weekday full mode), render, patterns, patterns_html, watchlist.
# Optional: margin_scan. Advanced stages require -IncludeAdvancedStages.
# Outputs are certified by pipeline_state.py; only the scheduled publisher pushes.
# Default stage budgets total at most 200 minutes (render budget: 90 minutes).
# -Mode render runs the rendering chain without maintenance; -Mode publish uses
# the same completion gate as the scheduled publisher.

[CmdletBinding()]
param(
    [ValidateSet('full','render','publish')]
    [string]$Mode = 'full',
    [switch]$Force,
    [switch]$SkipYfinance,
    [switch]$SkipFinmind,
    [switch]$IncludeAdvancedStages,
    [ValidateRange(1,120)]
    [int]$TimeoutMin = 90
)

$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
Set-Location "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts"

$today = Get-Date -Format "yyyyMMdd"
$logFile = "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug\daily_run_${today}.log"
$statusFile = "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug\daily_status.json"
$cacheDir = "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_cache"
$outputDir = "C:\Groove-Lab\analyze"
New-Item -ItemType Directory -Force -Path (Split-Path $logFile) | Out-Null
trap {
    $failureReason = [string]$_
    Write-Host "FATAL: $failureReason"
    try { Add-Content -LiteralPath $logFile -Value "[$(Get-Date -Format 'HH:mm:ss')] FATAL: $failureReason" -Encoding UTF8 } catch {}
    if ($env:TW_NIGHTLY_ID) { & C:\Python314\python.exe pipeline_state.py fail }
    exit 1
}


. (Join-Path $PSScriptRoot 'process_lifecycle.ps1')

function Log-Msg {
    param([string]$msg)
    $ts = Get-Date -Format "HH:mm:ss"
    $line = "[$ts] $msg"
    Add-Content -Path $logFile -Value $line -Encoding UTF8
    Write-Verbose $line
}


function Write-Status {
    # Write a JSON status file for external monitoring
    param(
        [string]$Stage,
        [string]$State,    # running | done | failed | skipped
        [int]$Pct = 0
    )
    $obj = @{
        date      = $today
        mode      = $Mode
        stage     = $Stage
        state     = $State
        pct       = $Pct
        updated   = (Get-Date -Format "yyyy-MM-dd HH:mm:ss")
        pid       = $PID
        log       = $logFile
    }
    $obj | ConvertTo-Json | Set-Content -Path $statusFile -Encoding UTF8
}


function Test-Health {
    Log-Msg "[health] Checking prerequisites..."
    $issues = @()

    # 1. DB
    try {
        $conn = New-Object System.Data.Odbc.OdbcConnection
        # Use Python for DB check since pymysql is the standard
        $r = C:\Python314\python.exe -X utf8 -c "import pymysql; c=pymysql.connect(host='localhost',user='root',password='1234',database='tw_elec',connect_timeout=5); c.close(); print('OK')" 2>&1
        if ($LASTEXITCODE -ne 0) { $issues += "DB connect failed: $r" }
    } catch { $issues += "DB check exception: $_" }

    # 2. Cache dir
    if (-not (Test-Path $cacheDir)) {
        New-Item -ItemType Directory -Path $cacheDir -Force | Out-Null
        Log-Msg "  cache dir created: $cacheDir"
    }

    # 3. Output dir
    if (-not (Test-Path $outputDir)) {
        New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
        Log-Msg "  output dir created: $outputDir"
    }

    # 4. Python
    $pyVer = C:\Python314\python.exe --version 2>&1
    Log-Msg "  Python: $pyVer"

    # 5. Disk space
    $drive = (Get-Item $outputDir).PSDrive
    $freeGB = [math]::Round((Get-PSDrive $drive).Free / 1GB, 1)
    Log-Msg "  Disk free on $drive`: $freeGB GB"
    if ($freeGB -lt 1) { $issues += "Low disk: $freeGB GB" }

    if ($issues.Count -gt 0) {
        Log-Msg "[health] ISSUES:"
        $issues | ForEach-Object { Log-Msg "  - $_" }
        return $false
    }
    Log-Msg "[health] OK"
    return $true
}





function Is-TradingDay {
    # Returns $true if today is a trading day (Mon-Fri, no holiday check)
    $dow = (Get-Date).DayOfWeek.value__  # 0=Sun, 1=Mon, ..., 6=Sat
    return ($dow -ge 1 -and $dow -le 5)
}


function Is-Weekend {
    $dow = (Get-Date).DayOfWeek.value__
    return ($dow -eq 0 -or $dow -eq 6)
}


function Get-CacheFreshness {
    # Returns: 'fresh' | 'stale' | 'empty'
    param([string]$Path)
    if (-not (Test-Path $Path)) { return 'empty' }
    $age = (Get-Date) - (Get-Item $Path).LastWriteTime
    if ($age.TotalHours -lt 24) { return 'fresh' }
    return 'stale'
}


function Run-Stage {
    # D056 P0-1: rewritten to eliminate pipe-buffer deadlock (file-based redirect)
    # D056 P1+ (9/15): PowerShell's $p.ExitCode is unreliable (returns $null) when
    #   stdout/stderr are redirected to files (verified bug across cmd.exe/python.exe
    #   wrappers). The fix: use a Python wrapper (run_stage.py) that captures exit
    #   code via subprocess.wait() (which IS reliable), then writes it to a sidecar
    #   file. PowerShell reads the sidecar file to get the real exit code.
    #
    # D056 P0-2: -Optional switch marks a stage as non-blocking; failure logs
    #   "DEGRADED" and returns $false so the result remains honest.
    param(
        [int]$Number,
        [string]$Name,
        [string]$Cmd,
        [int]$TimeoutSec = ($TimeoutMin * 60),
        [switch]$Optional
    )
    $optTag = if ($Optional) { ' [OPTIONAL/DEGRADED]' } else { '' }
    Log-Msg ""
    Log-Msg "[Stage $Number] $Name (timeout ${TimeoutSec}s)$optTag..."
    Write-Status -Stage $Name -State 'running' -Pct 0

    # Per-stage log files (the stage script's stdout/stderr go here).
    $stageLogDir = "_debug\stage_logs"
    if (-not (Test-Path $stageLogDir)) { New-Item -ItemType Directory -Path $stageLogDir -Force | Out-Null }
    $stageLogBase = Join-Path $stageLogDir ("{0}_{1}_stage{2}_{3}" -f $today, $env:TW_NIGHTLY_ID, $Number, $Name)
    $stageLogPath = "$stageLogBase.log"
    $stageErrPath = "$stageLogBase.err"
    $stageExitCodePath = "$stageLogBase.exit"
    if (Test-Path $stageLogPath) { Remove-Item $stageLogPath -Force }
    if (Test-Path $stageErrPath) { Remove-Item $stageErrPath -Force }
    if (Test-Path $stageExitCodePath) { Remove-Item $stageExitCodePath -Force }

    # D056 P1+: use Python wrapper run_stage.py for reliable exit code capture.
    # Wrapper: subprocess.Popen(wait=timeout) + writes exit code to sidecar file.
    # This avoids PowerShell's Start-Process ExitCode bug (returns $null when
    # stdout/stderr redirected to file).
    $wrapperScript = "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\run_stage.py"
    $wrapperArgs = @(
        $wrapperScript
        "--label", "stage$Number`_$Name"
        "--out", $stageLogPath
        "--err", $stageErrPath
        "--exit-code-file", $stageExitCodePath
        "--timeout", "$TimeoutSec"
        "--workdir", "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts"
    )
    # Append the original script + args. The Cmd string already includes the
    # script path and args. We pass them as a single string then split inside the
    # wrapper (handles quoted paths with spaces).
    $wrapperArgs += $Cmd

    $p = Start-Process -FilePath "C:\Python314\python.exe" -ArgumentList $wrapperArgs -NoNewWindow -PassThru `
        -RedirectStandardOutput "$stageLogBase.wrapper.log" -RedirectStandardError "$stageLogBase.wrapper.err"

    $wrapperCreatedTicks = $p.StartTime.ToUniversalTime().Ticks
    if (-not (Wait-OwnedProcess $p.Id $wrapperCreatedTicks (($TimeoutSec + 30) * 1000))) {
        Log-Msg "[Stage $Number] TIMEOUT — killing process tree (wrapper + stage)"
        # PowerShell 5.1 has no Process.Kill(bool). Never use an unbounded wait.
        & taskkill.exe /F /T /PID $p.Id 1>"$stageLogBase.kill.log" 2>"$stageLogBase.kill.err"
        if (-not (Wait-OwnedProcess $p.Id $wrapperCreatedTicks 5000)) { throw "Stage process tree could not be stopped" }
    }

    # D056 P1+: read exit code from sidecar file (PowerShell's $p.ExitCode is
    # unreliable when stdout is redirected; verified bug on this PowerShell 5.1).
    $exitCode = 1  # default to failure if sidecar missing/invalid
    if (Test-Path $stageExitCodePath) {
        $exitCodeText = (Get-Content $stageExitCodePath -Raw).Trim()
        if ($exitCodeText -match '^-?\d+$') {
            $exitCode = [int]$exitCodeText
        }
    } else {
        Log-Msg "  WARN: sidecar exit code file missing — assuming exit=1"
    }

    # Stream captured stdout/stderr to the daily log.
    if ((Test-Path $stageLogPath) -and (Get-Item $stageLogPath).Length -gt 0) {
        Get-Content $stageLogPath -Encoding UTF8 | ForEach-Object { if ($_ -match '\S') { Log-Msg "  $_" } }
    }
    if ((Test-Path $stageErrPath) -and (Get-Item $stageErrPath).Length -gt 0) {
        Get-Content $stageErrPath -Encoding UTF8 | ForEach-Object { if ($_ -match '\S') { Log-Msg "  [err] $_" } }
    }

    $p.Dispose()

    if ($exitCode -eq 0) {
        Log-Msg "[Stage $Number] OK (exit 0)"
        Write-Status -Stage $Name -State 'done' -Pct 100
        return $true
    } else {
        # P0-2: optional stages are DEGRADED, not FAILED — don't block downstream.
        if ($Optional) {
            Log-Msg "[Stage $Number] DEGRADED (exit $exitCode) — optional, continuing"
            Write-Status -Stage $Name -State 'degraded' -Pct 0
            return $false
        }
        Log-Msg "[Stage $Number] FAILED (exit $exitCode)"
        Write-Status -Stage $Name -State 'failed' -Pct 0
        return $false
    }
}


# === Main ===
Log-Msg "============================================================"
Log-Msg "=== tw-invest-suite daily report ==="
Log-Msg "Mode: $Mode  Force: $Force  SkipYfinance: $SkipYfinance  SkipFinmind: $SkipFinmind  Timeout: ${TimeoutMin}m"
$dow = (Get-Date).DayOfWeek
Log-Msg "Day: $dow  (Mon=Trading, Sat/Sun=Weekend)"
Log-Msg "============================================================"

$mutex = New-Object System.Threading.Mutex($false, 'Local\TwInvestSuiteDaily')
try { $acquired = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $acquired = $true }
if (-not $acquired) { Log-Msg 'FATAL: another daily run is active'; exit 1 }
if ($Mode -ne 'publish') {
    $env:TW_OWNER_PID = [string]$PID
    & C:\Python314\python.exe pipeline_state.py begin --mode $Mode
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $run = Get-Content '_debug\pipeline_run.json' -Raw -Encoding UTF8 | ConvertFrom-Json
    $env:TW_NIGHTLY_ID = $run.nightly_id
    $env:TW_DATA_DATE = $run.data_date
}

# Health check
if (-not (Test-Health)) {
    Log-Msg "Health check failed — aborting"
    Write-Status -Stage 'health' -State 'failed' -Pct 0
    & C:\Python314\python.exe pipeline_state.py fail
    exit 1
}

# The date-scoped preflight already verified DB coverage and exact picks.
# Avoid the legacy unbounded debug script (full-table counts and API probes).
Log-Msg "[db] data_date=$($run.data_date) run_id=$($run.run_id) tickers=$($run.ohlcv_tickers) active_picks=$($run.picks_count)"

# Weekend auto-skip download stages (unless -Force or explicit -Skip flags override)
$weekend = Is-Weekend
if ($weekend -and -not $Force) {
    Log-Msg "[weekend] Today is $dow — auto-skipping all data download stages"
    Log-Msg "          (only render + patterns + publish will run)"
    if (-not $SkipYfinance) { $SkipYfinance = $true }
    if (-not $SkipFinmind) { $SkipFinmind = $true }
    # news stage: skip too on weekend (DB news table will be used as fallback in render)
}

$startTime = Get-Date

# Publish mode uses the same verified release gate as the scheduled publisher.
if ($Mode -eq 'publish') {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'publish_ghpages_daily.ps1')
    exit $LASTEXITCODE
}

# === Full mode ===
# OpenAlice paths
$OA_ROOT = "D:\CODEX\AI-Telegram"
$OA_PY = "C:\Users\icemo\AppData\Local\Programs\Python\Python310\python.exe"
$OA_PHD = Join-Path $OA_ROOT "automation\openalice_phased_download.cmd"
$OA_NEWS = Join-Path $OA_ROOT "scripts\stock_news_auto_refresh.py"
$OA_RSS = Join-Path $OA_ROOT "news-digest\app\rss_to_db.py"
$OA_MISSING = Join-Path $OA_ROOT "strategy_lab\missing_data_downloader.py"

# Test that OpenAlice paths exist
foreach ($p in @($OA_PHD, $OA_NEWS, $OA_RSS, $OA_MISSING)) {
    if (-not (Test-Path $p)) {
        Log-Msg "  [!] OpenAlice path missing: $p"
    }
}

$stages = @()

# === tw-invest-suite 22:25 batch (D023) ===
# OpenAlice downloads 已分散到 15:55-21:45 排程跑（7 phases 各自時間觸發）
# 22:25 這班只跑 tw-invest-suite specific stages（不再重跑 OpenAlice）

# Stage 1: FinMind TaiwanStockMarginMaintenance (per-stock 維持率, D020)
$maintScript = "C:\Users\icemo\Projects\tw-invest-suite\src\margin_rebound\finmind_maint.py"
if ($Mode -eq 'full' -and $run.trading_session -and -not $SkipFinmind) {
    $stages += @{ N=1; Name='finmind_maint'; Cmd=$maintScript; To=10*60 }
}

# Stage 2: Render (1,962 tickers)
$stages += @{ N=2; Name='render'; Cmd='render_only.py --no-yfinance --no-news'; To=$TimeoutMin*60 }

# Stage 3: Pattern + build HTML
$stages += @{ N=3; Name='patterns'; Cmd='pattern_classifier.py'; To=30*60 }
$stages += @{ N=4; Name='patterns_html'; Cmd='build_patterns_html.py'; To=10*60 }

# Stage 5: Margin rebound scan (7-dim scoring, all maint<130% candidates)
# D056 P0-2: Optional/DEGRADED — if scan hangs or fails, watchlist (Stage 6) MUST still run.
$scanDate = $env:TW_DATA_DATE
$scanOut = Join-Path $PSScriptRoot "outputs\margin_rebound\$scanDate.json"
$scanScript = "C:\Users\icemo\Projects\tw-invest-suite\src\margin_rebound\scan.py"
$stages += @{ N=5; Name='margin_scan'; Cmd="$scanScript --threshold 0 --out `"$scanOut`""; To=30*60; Optional=$true }

# Stage 6: Full watchlist render
# Supplemental fetches have per-worker and overall deadlines; all picks remain.
$stages += @{ N=6; Name='watchlist'; Cmd='render_full_watchlist.py'; To=30*60 }

# Stage 7-17 REMOVED in D056-A (砍掉 D027/D029 advanced stages)
# 過去每天跑 25 分鐘，但 GitHub Pages 用不到。手動觸發 `-IncludeAdvancedStages` 加回來。
if ($IncludeAdvancedStages) {
    Log-Msg "[advanced] re-enabling D027/D029 stages 7-17"
$secScript = "C:\Users\icemo\Projects\tw-invest-suite\src\sector_aggregate.py"
$stages += @{ N=7; Name='sectors'; Cmd="$secScript"; To=5*60 }
$ogScript = "C:\Users\icemo\Projects\tw-invest-suite\src\generate_og.py"
$watchlistHtml = "C:\Groove-Lab\watchlist.html"
$ogOut = "C:\Users\icemo\Projects\tw-invest-suite\public\data\og.png"
if (Test-Path $watchlistHtml) {
    $stages += @{ N=8; Name='og_image'; Cmd="$ogScript `"$watchlistHtml`" `"$ogOut`""; To=2*60 }
}
$chipScript = "C:\Users\icemo\Projects\tw-invest-suite\src\chip_rank.py"
$stages += @{ N=9; Name='chips'; Cmd="$chipScript"; To=5*60 }
$chipAdvScript = "C:\Users\icemo\Projects\tw-invest-suite\src\chip_advanced.py"
$stages += @{ N=10; Name='chips_advanced'; Cmd="$chipAdvScript"; To=10*60 }
$chipsAdvHtml = "C:\Users\icemo\Projects\tw-invest-suite\src\render_chips_advanced.py"
$stages += @{ N=11; Name='render_chips_advanced'; Cmd="$chipsAdvHtml"; To=60 }
$chipHist = "C:\Users\icemo\Projects\tw-invest-suite\src\chip_history.py"
$stages += @{ N=12; Name='chips_history'; Cmd="$chipHist"; To=5*60 }
$buildMeta = "C:\Users\icemo\Projects\tw-invest-suite\src\build_ticker_meta.py"
$stages += @{ N=13; Name='build_ticker_meta'; Cmd="$buildMeta"; To=30 }
$chipPush = "C:\Users\icemo\Projects\tw-invest-suite\src\chip_push.py"
$stages += @{ N=14; Name='chip_push'; Cmd="$chipPush"; To=30 }
$twIndustry = "C:\Users\icemo\Projects\tw-invest-suite\src\fetch_tw_industry.py"
$conceptStocks = "C:\Users\icemo\Projects\tw-invest-suite\src\concept_stocks.py"
$renderConcepts = "C:\Users\icemo\Projects\tw-invest-suite\src\render_concepts.py"
$stages += @{ N=15; Name='tw_industry'; Cmd="$twIndustry"; To=30 }
$stages += @{ N=16; Name='concept_stocks'; Cmd="$conceptStocks"; To=10 }
$stages += @{ N=17; Name='render_concepts'; Cmd="$renderConcepts"; To=30 }
}

# Leave five minutes for preflight/certification under the four-hour task cap.
$stageBudgetSec = 0
foreach ($stage in $stages) { $stageBudgetSec += [int]$stage['To'] }
if ($stageBudgetSec -gt 235*60) { throw "Stage budgets exceed Scheduler cap: $stageBudgetSec seconds" }

# Run stages
$stageResults = @()
foreach ($s in $stages) {
    $opt = [switch]$s.Optional
    $ok = Run-Stage -Number $s.N -Name $s.Name -Cmd $s.Cmd -TimeoutSec $s.To -Optional:$opt
    $stageResults += @{ N=$s.N; Name=$s.Name; Ok=$ok; Optional=[bool]$s.Optional }
    if (-not $ok) {
        Log-Msg "[!] Stage $($s.Name) failed — continuing to next stage"
    }
}

# Certify the exact data run, required stages and publish artifacts together.
$stagesPath = Join-Path $PSScriptRoot "_debug\stages_$($env:TW_NIGHTLY_ID).json"
ConvertTo-Json -InputObject @($stageResults) -Depth 5 | Set-Content -LiteralPath $stagesPath -Encoding UTF8
# D056-2 hardening: capture complete() stderr/stdout to file so the FATAL reason
# is logged (previously `& python ...` dropped stderr, leaving only "FATAL: nightly
# not certified" without which cert check failed).
$completeLogPath = Join-Path $PSScriptRoot "_debug\complete_$($env:TW_NIGHTLY_ID).log"
$completeErrPath = Join-Path $PSScriptRoot "_debug\complete_$($env:TW_NIGHTLY_ID).err"
$certExitPath = Join-Path $PSScriptRoot "_debug\complete_$($env:TW_NIGHTLY_ID).exit"
$certArgs = @('C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\run_stage.py',
    '--label', 'cert', '--out', $completeLogPath, '--err', $completeErrPath,
    '--exit-code-file', $certExitPath, '--timeout', '180', '--workdir', $PSScriptRoot,
    'pipeline_state.py', 'complete', '--stages', $stagesPath)
$certProcess = Start-Process -FilePath 'C:\Python314\python.exe' -ArgumentList $certArgs -NoNewWindow -PassThru `
    -RedirectStandardOutput "$completeLogPath.wrapper" -RedirectStandardError "$completeErrPath.wrapper"
$certCreatedTicks = $certProcess.StartTime.ToUniversalTime().Ticks
if (-not (Wait-OwnedProcess $certProcess.Id $certCreatedTicks 210000)) {
    & taskkill.exe /F /T /PID $certProcess.Id 1>"$completeLogPath.kill" 2>"$completeErrPath.kill"
    throw 'Certification exceeded three-minute deadline'
}
$certProcess.Dispose()
$completionExit = 1
if (Test-Path -LiteralPath $certExitPath) {
    $certExitText = (Get-Content -LiteralPath $certExitPath -Raw).Trim()
    if ($certExitText -match '^-?\d+$') { $completionExit = [int]$certExitText }
}
if ($completionExit -ne 0) {
    Write-Status -Stage 'complete' -State 'failed' -Pct 0
    # Surface the actual reason — without this the cert failure is invisible.
    $certReason = 'unknown'
    if (Test-Path -LiteralPath $completeErrPath) {
        $errText = (Get-Content -LiteralPath $completeErrPath -Raw -Encoding UTF8).Trim()
        if ($errText) { $certReason = $errText }
    } elseif (Test-Path -LiteralPath $completeLogPath) {
        $outText = (Get-Content -LiteralPath $completeLogPath -Raw -Encoding UTF8).Trim()
        if ($outText) { $certReason = $outText }
    }
    Log-Msg "FATAL: nightly not certified; publication is blocked"
    Log-Msg "  reason: $certReason"
    Log-Msg "  detail: $completeErrPath"
    exit $completionExit
}
# Certification is the final required operation. Reporting cannot undo it.
try {
    Log-Msg 'Artifacts certified. Scheduled publish consumes this run after completion.'
    Write-Status -Stage 'complete' -State 'done' -Pct 100
} catch { Write-Host "WARNING: certification succeeded; final reporting failed: $_" }
exit 0
