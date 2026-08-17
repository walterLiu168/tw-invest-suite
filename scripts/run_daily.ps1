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
    # Run a python stage with timeout
    param(
        [int]$Number,
        [string]$Name,
        [string]$Cmd,
        [int]$TimeoutSec = ($TimeoutMin * 60)
    )
    Log-Msg ""
    Log-Msg "[Stage $Number/5] $Name (timeout ${TimeoutMin}m)..."
    Write-Status -Stage $Name -State 'running' -Pct 0

    $pinfo = New-Object System.Diagnostics.ProcessStartInfo
    $pinfo.FileName = "python"
    $pinfo.Arguments = $Cmd
    $pinfo.WorkingDirectory = "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts"
    $pinfo.UseShellExecute = $false
    $pinfo.RedirectStandardOutput = $true
    $pinfo.RedirectStandardError = $true
    $pinfo.CreateNoWindow = $true

    $p = New-Object System.Diagnostics.Process
    $p.StartInfo = $pinfo
    $started = $p.Start()
    $exited = $p.WaitForExit($TimeoutSec * 1000)

    if (-not $exited) {
        Log-Msg "[Stage $Number] TIMEOUT after ${TimeoutMin}m — killing"
        try { $p.Kill() } catch {}
        Write-Status -Stage $Name -State 'failed' -Pct 0
        return $false
    }

    $stdout = $p.StandardOutput.ReadToEnd()
    $stderr = $p.StandardError.ReadToEnd()
    $stdout.Split("`n") | Where-Object { $_ -match '\S' } | ForEach-Object { Log-Msg "  $_" }
    if ($stderr) {
        $stderr.Split("`n") | Where-Object { $_ -match '\S' } | ForEach-Object { Log-Msg "  [err] $_" }
    }

    if ($p.ExitCode -eq 0) {
        Log-Msg "[Stage $Number] OK (exit 0)"
        Write-Status -Stage $Name -State 'done' -Pct 100
        return $true
    } else {
        Log-Msg "[Stage $Number] FAILED (exit $($p.ExitCode))"
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
$stages = @()

# Stage 1: yfinance — skip if cache fresh (1d TTL)
if (-not $SkipYfinance) {
    if (-not $Force) {
        # Sample check 5 tickers
        $sample = python -c "
import sys
sys.path.insert(0, r'C:\Users\icemo\.claude\skills\tw-invest-suite\scripts')
import cache_manager as cm
import json, glob
files = sorted(glob.glob(r'C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_cache\*.json'))[:5]
stale = sum(1 for f in files if cm.needs_refresh(f.split('\\\\')[-1].replace('.json',''), 'yfinance'))
print(f'{stale}/{len(files)} stale')
" 2>&1
        Log-Msg "[Stage 1/5] yfinance cache check: $sample"
        if ($sample -match '0/5 stale') {
            Log-Msg "[Stage 1/5] SKIPPED — cache fresh (sampled 5 tickers)"
            Write-Status -Stage 'yfinance' -State 'skipped' -Pct 100
        } else {
            $stages += @{ N=1; Name='yfinance'; Cmd='batch_yfinance_only.py'; To=240*60 }
        }
    } else {
        $stages += @{ N=1; Name='yfinance'; Cmd='batch_yfinance_only.py'; To=240*60 }
    }
} else {
    Log-Msg "[Stage 1/5] SKIPPED — -SkipYfinance flag"
    Write-Status -Stage 'yfinance' -State 'skipped' -Pct 100
}

# Stage 2: FinMind PE/Div/Fin/Month — skip if cache fresh
if (-not $SkipFinmind) {
    if (-not $Force) {
        $sample = python -c "
import sys
sys.path.insert(0, r'C:\Users\icemo\.claude\skills\tw-invest-suite\scripts')
import cache_manager as cm
import json, glob
files = sorted(glob.glob(r'C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_cache\*.json'))[:5]
total_stale = 0
for f in files:
    t = f.split('\\\\')[-1].replace('.json','')
    for k in ['finmind_pe','finmind_div','finmind_fin','finmind_month']:
        if cm.needs_refresh(t, k):
            total_stale += 1
print(f'{total_stale}/20 entries stale (5 tickers × 4 datasets)')
" 2>&1
        Log-Msg "[Stage 2/5] FinMind cache check: $sample"
        if ($sample -match '0/20 entries stale') {
            Log-Msg "[Stage 2/5] SKIPPED — cache fresh"
            Write-Status -Stage 'finmind' -State 'skipped' -Pct 100
        } else {
            $stages += @{ N=2; Name='finmind'; Cmd='batch_finmind_only.py'; To=$TimeoutMin*60 }
        }
    } else {
        $stages += @{ N=2; Name='finmind'; Cmd='batch_finmind_only.py'; To=$TimeoutMin*60 }
    }
} else {
    Log-Msg "[Stage 2/5] SKIPPED — -SkipFinmind flag"
    Write-Status -Stage 'finmind' -State 'skipped' -Pct 100
}

# Stage 3: FinMind news — skip on weekend (DB stock_news will be used as fallback in render)
if ($weekend -and -not $Force) {
    Log-Msg "[Stage 3/5] SKIPPED — weekend (DB stock_news will be used as fallback)"
    Write-Status -Stage 'finmind_news' -State 'skipped' -Pct 100
} else {
    $stages += @{ N=3; Name='finmind_news'; Cmd='batch_finmind_news.py'; To=60*60 }
}

# Stage 4: Render
$stages += @{ N=4; Name='render'; Cmd='render_only.py --no-yfinance --no-news'; To=$TimeoutMin*60 }

# Stage 5: Pattern + build HTML
$stages += @{ N=5; Name='patterns'; Cmd='pattern_classifier.py'; To=30*60 }
$stages += @{ N=6; Name='patterns_html'; Cmd='build_patterns_html.py'; To=10*60 }

# Stage 7: Margin rebound scan (7-dim scoring, top 10 candidates)
$today = Get-Date -Format 'yyyy-MM-dd'
$scanOut = Join-Path $PSScriptRoot "outputs\margin_rebound\$today.json"
$scanScript = "C:\Users\icemo\Projects\tw-invest-suite\src\margin_rebound\scan.py"
$stages += @{ N=7; Name='margin_scan'; Cmd="$scanScript --threshold 30 --top 10 --out `"$scanOut`""; To=15*60 }

# Stage 8: Full watchlist render (24 picks + 潛在反彈 tab from scan JSON)
$stages += @{ N=8; Name='watchlist'; Cmd='render_full_watchlist.py'; To=10*60 }

# Run stages
foreach ($s in $stages) {
    $ok = Run-Stage -Number $s.N -Name $s.Name -Cmd $s.Cmd -TimeoutSec $s.To
    if (-not $ok) {
        Log-Msg "[!] Stage $($s.Name) failed — continuing to next stage"
    }
}

# Publish to groovelab + GitHub Pages
Log-Msg ""
Log-Msg "[publish] Copying watchlist + pushing to GitHub Pages..."
try {
    if (Test-Path "C:\Groove-Lab\watchlist.html") {
        Copy-Item "C:\Groove-Lab\watchlist.html" "C:\Groove-Lab\analyze\watchlist.html" -Force
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
