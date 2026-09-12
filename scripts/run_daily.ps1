# tw-invest-suite daily report — fully autonomous batch
# Scheduled via Windows Task Scheduler: daily 22:25
# Runs without any agent interaction.
#
# Pipeline (5 stages, each is cache-aware & timeout-bounded):
#   1. yfinance batch  (1,962 tickers, cache TTL 1d, ~30-50 min)
#   2. FinMind PE/Div/Fin/Month  (1,962 × 4, ~2-3 hours, 1.05s/call rate-limit)
#   3. FinMind news  (1,962 tickers, ~22 min, 4h cache)
#   4. Render  (1,962 HTML, ~30-50 min, cache-only, new tabbed UI)
#   5. Pattern classifier  (8 patterns + 240d backtest, ~10 min)
#   + Publish  (push to groovelab + GitHub Pages)
#
# Total: ~3-4 hours overnight. Finishes ~02:00.
#
# Flags:
#   -Mode <full|render|publish>   default: full
#   -Force                        skip cache freshness checks (full re-fetch)
#   -SkipYfinance                 skip Stage 1 (DB+FinMind only, fast ~3 hours)
#   -SkipFinmind                  skip Stage 2 (DB+yfinance only)
#   -TimeoutMin <N>               per-stage timeout in minutes (default 180)

[CmdletBinding()]
param(
    [ValidateSet('full','render','publish')]
    [string]$Mode = 'full',
    [switch]$Force,
    [switch]$SkipYfinance,
    [switch]$SkipFinmind,
    [int]$TimeoutMin = 180
)

$ErrorActionPreference = "Continue"
Set-Location "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts"

$today = Get-Date -Format "yyyyMMdd"
$logFile = "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug\daily_run_${today}.log"
$statusFile = "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug\daily_status.json"
$cacheDir = "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_cache"
$outputDir = "C:\Groove-Lab\analyze"


function Log-Msg {
    param([string]$msg)
    $ts = Get-Date -Format "HH:mm:ss"
    $line = "[$ts] $msg"
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
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
        $r = python -c "import pymysql; c=pymysql.connect(host='localhost',user='root',password='1234',database='tw_elec',connect_timeout=5); c.close(); print('OK')" 2>&1
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
    $pyVer = python --version 2>&1
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


function Get-DbStatus {
    # Always check DB first — show latest data dates before doing anything
    Log-Msg ""
    Log-Msg "[db] Checking latest data in MySQL..."
    $r = python _debug\db_status.py 2>&1
    $r | ForEach-Object { Log-Msg "  $_" }
    Log-Msg ""
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
    # D056 P0-1: rewritten to eliminate pipe-buffer deadlock
    #   - Use Start-Process with -RedirectStandardOutput/-RedirectStandardError
    #     pointing to FILES (not pipes). Files have no 4KB pipe buffer limit.
    #   - Poll HasExited (instead of WaitForExit) so we don't block on
    #     async stream readers.
    #   - Kill PROCESS TREE on timeout (margin_scan may spawn workers via LLM calls).
    #   - Each stage's stdout/stderr saved to _debug/stage_logs/{date}_stage{N}_{name}.{log,err}
    # D056 P0-2: -Optional switch marks a stage as non-blocking; failure logs
    #   "DEGRADED" and returns $true so the loop continues.
    param(
        [int]$Number,
        [string]$Name,
        [string]$Cmd,
        [int]$TimeoutSec = ($TimeoutMin * 60),
        [switch]$Optional
    )
    $optTag = if ($Optional) { ' [OPTIONAL/DEGRADED]' } else { '' }
    Log-Msg ""
    Log-Msg "[Stage $Number] $Name (timeout ${TimeoutMin}m)$optTag..."
    Write-Status -Stage $Name -State 'running' -Pct 0

    # File-based redirect — no 4KB pipe buffer limit, no deadlock possible.
    $stageLogDir = "_debug\stage_logs"
    if (-not (Test-Path $stageLogDir)) { New-Item -ItemType Directory -Path $stageLogDir -Force | Out-Null }
    $stageLogBase = Join-Path $stageLogDir ("{0}_stage{1}_{2}" -f $today, $Number, $Name)
    $stageLogPath = "$stageLogBase.log"
    $stageErrPath = "$stageLogBase.err"
    if (Test-Path $stageLogPath) { Remove-Item $stageLogPath -Force }
    if (Test-Path $stageErrPath) { Remove-Item $stageErrPath -Force }

    # Start-Process with -RedirectStandardOutput/-RedirectStandardError to FILES.
    $p = Start-Process -FilePath "python" -ArgumentList $Cmd -NoNewWindow -PassThru `
        -RedirectStandardOutput $stageLogPath -RedirectStandardError $stageErrPath `
        -WorkingDirectory "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts"

    # Poll HasExited instead of WaitForExit (avoids any hang on stream readers).
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while (-not $p.HasExited -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 500
    }

    if (-not $p.HasExited) {
        Log-Msg "[Stage $Number] TIMEOUT after ${TimeoutMin}m — killing process tree"
        # P0-1: Kill($true) kills the entire process tree (children + grandchildren).
        try { $p.Kill($true) } catch {}
        Start-Sleep -Milliseconds 500
        # Belt-and-suspenders: also kill any orphan children by ParentProcessId.
        try {
            Get-CimInstance Win32_Process -Filter "ParentProcessId=$($p.Id)" -ErrorAction SilentlyContinue |
                Stop-Process -Force -ErrorAction SilentlyContinue
        } catch {}
        Start-Sleep -Milliseconds 500
    }

    # Stream captured stdout/stderr to the daily log.
    if ((Test-Path $stageLogPath) -and (Get-Item $stageLogPath).Length -gt 0) {
        Get-Content $stageLogPath | ForEach-Object { if ($_ -match '\S') { Log-Msg "  $_" } }
    }
    if ((Test-Path $stageErrPath) -and (Get-Item $stageErrPath).Length -gt 0) {
        Get-Content $stageErrPath | ForEach-Object { if ($_ -match '\S') { Log-Msg "  [err] $_" } }
    }

    if ($p.ExitCode -eq 0) {
        Log-Msg "[Stage $Number] OK (exit 0)"
        Write-Status -Stage $Name -State 'done' -Pct 100
        $p.Dispose()
        return $true
    } else {
        # P0-2: optional stages are DEGRADED, not FAILED — don't block downstream.
        if ($Optional) {
            Log-Msg "[Stage $Number] DEGRADED (exit $($p.ExitCode)) — optional, continuing"
            Write-Status -Stage $Name -State 'degraded' -Pct 0
            $p.Dispose()
            return $true
        }
        Log-Msg "[Stage $Number] FAILED (exit $($p.ExitCode))"
        Write-Status -Stage $Name -State 'failed' -Pct 0
        $p.Dispose()
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

# Health check
if (-not (Test-Health)) {
    Log-Msg "Health check failed — aborting"
    Write-Status -Stage 'health' -State 'failed' -Pct 0
    exit 1
}

# Always show DB status (the user wants us to check DB first)
Get-DbStatus

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

# === Publish-only mode ===
if ($Mode -eq 'publish') {
    Log-Msg "[publish] Pushing to GitHub Pages..."
    if (Test-Path "C:\Groove-Lab\watchlist.html") {
        Copy-Item "C:\Groove-Lab\watchlist.html" "C:\Groove-Lab\analyze\watchlist.html" -Force
    }
    Run-Stage -Number 1 -Name "publish" -Cmd "publish_analyze_ghpages.py" -TimeoutSec 600
    $dur = (Get-Date) - $startTime
    Log-Msg "=== Publish-only done in $([int]$dur.TotalMinutes)m ==="
    exit 0
}

# === Render-only mode ===
if ($Mode -eq 'render') {
    Run-Stage -Number 1 -Name "render" -Cmd "render_only.py --no-yfinance --no-news" -TimeoutSec ($TimeoutMin * 60)
    Run-Stage -Number 2 -Name "patterns" -Cmd "pattern_classifier.py" -TimeoutSec ($TimeoutMin * 60)
    Run-Stage -Number 3 -Name "patterns_html" -Cmd "build_patterns_html.py" -TimeoutSec 300
    if (Test-Path "C:\Groove-Lab\watchlist.html") {
        Copy-Item "C:\Groove-Lab\watchlist.html" "C:\Groove-Lab\analyze\watchlist.html" -Force
    }
    Run-Stage -Number 4 -Name "publish" -Cmd "publish_analyze_ghpages.py" -TimeoutSec 600
    $dur = (Get-Date) - $startTime
    Log-Msg "=== Render-only done in $([int]$dur.TotalMinutes)m ==="
    exit 0
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
$stages += @{ N=1; Name='finmind_maint'; Cmd=$maintScript; To=10*60 }

# Stage 2: Render (1,962 tickers)
$stages += @{ N=2; Name='render'; Cmd='render_only.py --no-yfinance --no-news'; To=$TimeoutMin*60 }

# Stage 3: Pattern + build HTML
$stages += @{ N=3; Name='patterns'; Cmd='pattern_classifier.py'; To=30*60 }
$stages += @{ N=4; Name='patterns_html'; Cmd='build_patterns_html.py'; To=10*60 }

# Stage 5: Margin rebound scan (7-dim scoring, all maint<130% candidates)
# D056 P0-2: Optional/DEGRADED — if scan hangs or fails, watchlist (Stage 6) MUST still run.
$today = Get-Date -Format 'yyyy-MM-dd'
$scanOut = Join-Path $PSScriptRoot "outputs\margin_rebound\$today.json"
$scanScript = "C:\Users\icemo\Projects\tw-invest-suite\src\margin_rebound\scan.py"
$stages += @{ N=5; Name='margin_scan'; Cmd="$scanScript --threshold 0 --out `"$scanOut`""; To=30*60; Optional=$true }

# Stage 6: Full watchlist render
$stages += @{ N=6; Name='watchlist'; Cmd='render_full_watchlist.py'; To=10*60 }

# Stage 7: Sector aggregate (D027) — 1,962 檔依 yfinance industry 加總
# 需 1 次 FinMind call 抓 5 日法人（每天單獨 call，共 5 次）+ 本地 cache
$secScript = "C:\Users\icemo\Projects\tw-invest-suite\src\sector_aggregate.py"
$stages += @{ N=7; Name='sectors'; Cmd="$secScript"; To=5*60 }

# Stage 8: Daily OG image (D027) — parse watchlist.html 產 1200x630 PNG
$ogScript = "C:\Users\icemo\Projects\tw-invest-suite\src\generate_og.py"
$watchlistHtml = "C:\Groove-Lab\watchlist.html"
$ogOut = "C:\Users\icemo\Projects\tw-invest-suite\public\data\og.png"
if (Test-Path $watchlistHtml) {
    $stages += @{ N=8; Name='og_image'; Cmd="$ogScript `"$watchlistHtml`" `"$ogOut`""; To=2*60 }
} else {
    Log-Msg "  [!] watchlist.html not found, skipping OG image generation"
}

# Stage 9: 籌碼排行 (D027 P1) — 抓 10 日法人 + 全市場收盤價
$chipScript = "C:\Users\icemo\Projects\tw-invest-suite\src\chip_rank.py"
$stages += @{ N=9; Name='chips'; Cmd="$chipScript"; To=5*60 }

# Stage 10: 籌碼進階 (D027 P2) — 抓 20 日 OHLCV + 法人，產 VWAP/力道/雷達
$chipAdvScript = "C:\Users\icemo\Projects\tw-invest-suite\src\chip_advanced.py"
$stages += @{ N=10; Name='chips_advanced'; Cmd="$chipAdvScript"; To=10*60 }

# Stage 11: 渲染籌碼進階 HTML (D027 P2)
$chipsAdvHtml = "C:\Users\icemo\Projects\tw-invest-suite\src\render_chips_advanced.py"
$stages += @{ N=11; Name='render_chips_advanced'; Cmd="$chipsAdvHtml"; To=60 }

# Stage 12: 籌碼歷史備份 (D027 P3.1) — 抓近 30 日全市場
$chipHist = "C:\Users\icemo\Projects\tw-invest-suite\src\chip_history.py"
$stages += @{ N=12; Name='chips_history'; Cmd="$chipHist"; To=5*60 }

# Stage 13: ticker meta 重建 (P3.1) — chips-history.html / monitor.html 需要
$buildMeta = "C:\Users\icemo\Projects\tw-invest-suite\src\build_ticker_meta.py"
$stages += @{ N=13; Name='build_ticker_meta'; Cmd="$buildMeta"; To=30 }

# Stage 14: 籌碼異動 Telegram 推播 (D027 P3.3) — 需 TELEGRAM_BOT_TOKEN/CHAT_ID
$chipPush = "C:\Users\icemo\Projects\tw-invest-suite\src\chip_push.py"
$stages += @{ N=14; Name='chip_push'; Cmd="$chipPush"; To=30 }

# Stage 15: TWSE 官方分類 + 概念股清單 (D029)
$twIndustry = "C:\Users\icemo\Projects\tw-invest-suite\src\fetch_tw_industry.py"
$conceptStocks = "C:\Users\icemo\Projects\tw-invest-suite\src\concept_stocks.py"
$renderConcepts = "C:\Users\icemo\Projects\tw-invest-suite\src\render_concepts.py"
$stages += @{ N=15; Name='tw_industry'; Cmd="$twIndustry"; To=30 }
$stages += @{ N=16; Name='concept_stocks'; Cmd="$conceptStocks"; To=10 }
$stages += @{ N=17; Name='render_concepts'; Cmd="$renderConcepts"; To=30 }

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

# D056 P0-3: write completion marker for publish_ghpages_daily.ps1 to consume.
# Marker tells publish the actual data_date (NOT Get-Date which would be wrong at 00:30 next day).
# If any REQUIRED stage failed, do NOT write marker — publish will exit 1 and refuse to push stale data.
$requiredFailed = @($stageResults | Where-Object { -not $_.Optional -and -not $_.Ok })
$optionalDegraded = @($stageResults | Where-Object { $_.Optional -and -not $_.Ok })
if ($requiredFailed.Count -eq 0) {
    Log-Msg ""
    Log-Msg "[marker] Writing completion marker (data_date=$today)..."
    $markerArgs = "--date $today --status ok --degraded $optionalDegraded.Count"
    try {
        python _debug\write_completion_marker.py $markerArgs.Split(' ') 2>&1 | ForEach-Object { Log-Msg "  $_" }
    } catch {
        Log-Msg "[marker] WARN: completion marker write failed: $_"
    }
} else {
    Log-Msg ""
    Log-Msg "[marker] SKIP completion marker — $($requiredFailed.Count) required stage(s) failed: $($requiredFailed.Name -join ', ')"
    Log-Msg "        publish_ghpages_daily.ps1 will exit 1 (no marker = no push)"
}

# Publish to groovelab + GitHub Pages
# D053: PM 9.2 P0 - copy watchlist.html to public/ for 23:50 tw-invest-suite publish
Log-Msg ""
Log-Msg "[publish] Copying watchlist + pushing to GitHub Pages..."
try {
    if (Test-Path "C:\Groove-Lab\watchlist.html") {
        Copy-Item "C:\Groove-Lab\watchlist.html" "C:\Groove-Lab\analyze\watchlist.html" -Force
        # D053: also copy to public/ so 23:50 tw-invest-suite-publish picks up the new date
        $publicWatchlist = "C:\Users\icemo\Projects\tw-invest-suite\public\watchlist.html"
        $publicDir = Split-Path $publicWatchlist -Parent
        if (-not (Test-Path $publicDir)) { New-Item -ItemType Directory -Path $publicDir -Force | Out-Null }
        Copy-Item "C:\Groove-Lab\watchlist.html" $publicWatchlist -Force
        Log-Msg "  D053: copied to public/watchlist.html (for 23:50 publish)"
    }
    Run-Stage -Number 99 -Name "publish" -Cmd "publish_analyze_ghpages.py" -TimeoutSec 600
} catch {
    Log-Msg "publish ERR: $_"
}

# Final stats
$files = @(Get-ChildItem $outputDir -Filter "*.html" -ErrorAction SilentlyContinue)
$count = $files.Count
$totalMB = if ($files.Count -gt 0) { [math]::Round(($files | Measure-Object Length -Sum).Sum / 1MB, 1) } else { 0 }
$cacheFiles = @(Get-ChildItem $cacheDir -Filter "*.json" -ErrorAction SilentlyContinue)
$cacheCount = $cacheFiles.Count
$cacheMB = if ($cacheFiles.Count -gt 0) { [math]::Round(($cacheFiles | Measure-Object Length -Sum).Sum / 1MB, 1) } else { 0 }

$dur = Get-Date - $startTime
Log-Msg ""
Log-Msg "============================================================"
Log-Msg "=== Done. Files: $count ($totalMB MB), Cache: $cacheCount ($cacheMB MB) ==="
Log-Msg "=== Elapsed: $([int]$dur.TotalMinutes)m$([int]$dur.Seconds)s ==="
Log-Msg "============================================================"

# Write final status
Write-Status -Stage 'complete' -State 'done' -Pct 100
