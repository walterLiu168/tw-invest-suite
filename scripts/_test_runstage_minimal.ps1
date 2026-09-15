# Minimal Run-Stage test — embed Run-Stage + helpers via copy-paste from run_daily.ps1
$ErrorActionPreference = "Continue"
Set-Location "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts"

# === Inlined Log-Msg and Write-Status (extracted from run_daily.ps1) ===
$today = "20260915"
$logFile = "_debug\test_runstage.log"
function Log-Msg {
    param([string]$msg)
    $ts = Get-Date -Format "HH:mm:ss"
    $line = "[$ts] $msg"
    Write-Host $line
    Add-Content -Path $logFile -Value $line -Encoding UTF8
}
$statusFile = "_debug\test_status.json"
function Write-Status {
    param([string]$Stage, [string]$State, [int]$Pct = 0)
    # No-op for test
}

# === Inlined Run-Stage (D056 P1+ with Python wrapper) ===
function Run-Stage {
    param([int]$Number, [string]$Name, [string]$Cmd, [int]$TimeoutSec = 1800, [switch]$Optional)
    $optTag = if ($Optional) { " [OPTIONAL/DEGRADED]" } else { "" }
    Log-Msg "[Stage $Number] $Name (timeout ${TimeoutSec}s)$optTag"
    $stageLogDir = "_debug\stage_logs"
    if (-not (Test-Path $stageLogDir)) { New-Item -ItemType Directory -Path $stageLogDir -Force | Out-Null }
    $stageLogBase = Join-Path $stageLogDir ("{0}_stage{1}_{2}" -f $today, $Number, $Name)
    $stageLogPath = "$stageLogBase.log"
    $stageErrPath = "$stageLogBase.err"
    $stageExitCodePath = "$stageLogBase.exit"
    if (Test-Path $stageLogPath) { Remove-Item $stageLogPath -Force }
    if (Test-Path $stageErrPath) { Remove-Item $stageErrPath -Force }
    if (Test-Path $stageExitCodePath) { Remove-Item $stageExitCodePath -Force }

    $wrapperScript = "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug\run_stage.py"
    $wrapperArgs = @(
        $wrapperScript,
        "--label", "stage$Number`_$Name",
        "--out", $stageLogPath,
        "--err", $stageErrPath,
        "--exit-code-file", $stageExitCodePath,
        "--timeout", "$TimeoutSec",
        "--workdir", "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts"
    )
    $wrapperArgs += $Cmd

    $p = Start-Process -FilePath "C:\Python314\python.exe" -ArgumentList $wrapperArgs -NoNewWindow -PassThru
    $deadline = (Get-Date).AddSeconds($TimeoutSec + 30)
    while (-not $p.HasExited -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }

    if (-not $p.HasExited) {
        Log-Msg "[Stage $Number] TIMEOUT — killing wrapper + tree"
        try { $p.Kill($true) } catch {}
        Start-Sleep -Milliseconds 500
        try { Get-CimInstance Win32_Process -Filter "ParentProcessId=$($p.Id)" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue } catch {}
        Start-Sleep -Milliseconds 500
        try { $p.WaitForExit() 2>$null | Out-Null } catch {}
    }

    $exitCode = 1
    if (Test-Path $stageExitCodePath) {
        $exitCodeText = (Get-Content $stageExitCodePath -Raw).Trim()
        if ($exitCodeText -match "^-?\d+$") { $exitCode = [int]$exitCodeText }
    }
    $p.Dispose()

    if ($exitCode -eq 0) {
        Log-Msg "[Stage $Number] OK (sidecar=$exitCode)"
        return $true
    } elseif ($Optional) {
        Log-Msg "[Stage $Number] DEGRADED (sidecar=$exitCode) — optional"
        return $true
    } else {
        Log-Msg "[Stage $Number] FAILED (sidecar=$exitCode)"
        return $false
    }
}

# === Test 1: success ===
Set-Content -Path "_debug\test_success.py" -Value @"
import sys
print('stage output')
sys.exit(0)
"@ -Encoding UTF8
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$ok1 = Run-Stage -Number 1 -Name "TEST_success" -Cmd "_debug\test_success.py" -TimeoutSec 30
$sw.Stop()
"TEST_1 success: ok=$ok1 duration=$([int]$sw.Elapsed.TotalSeconds)s sidecar=$(Get-Content '_debug\stage_logs\20260915_stage1_TEST_success.exit' -Raw).Trim()"

# === Test 2: fail with exit 7 ===
Set-Content -Path "_debug\test_fail.py" -Value @"
import sys
sys.exit(7)
"@ -Encoding UTF8
$sw2 = [System.Diagnostics.Stopwatch]::StartNew()
$ok2 = Run-Stage -Number 2 -Name "TEST_fail" -Cmd "_debug\test_fail.py" -TimeoutSec 30
$sw2.Stop()
"TEST_2 fail: ok=$ok2 duration=$([int]$sw2.Elapsed.TotalSeconds)s sidecar=$(Get-Content '_debug\stage_logs\20260915_stage2_TEST_fail.exit' -Raw).Trim()"

# === Test 3: timeout (sleeps 999s, timeout 5s) ===
Set-Content -Path "_debug\test_sleep.py" -Value @"
import time
time.sleep(999)
"@ -Encoding UTF8
$sw3 = [System.Diagnostics.Stopwatch]::StartNew()
$ok3 = Run-Stage -Number 3 -Name "TEST_timeout" -Cmd "_debug\test_sleep.py" -TimeoutSec 5
$sw3.Stop()
"TEST_3 timeout: ok=$ok3 duration=$([int]$sw3.Elapsed.TotalSeconds)s sidecar=$(Get-Content '_debug\stage_logs\20260915_stage3_TEST_timeout.exit' -Raw).Trim()"

# === Test 4: optional failure → DEGRADED (returns $true) ===
Set-Content -Path "_debug\test_optional.py" -Value @"
import sys
sys.exit(99)
"@ -Encoding UTF8
$sw4 = [System.Diagnostics.Stopwatch]::StartNew()
$ok4 = Run-Stage -Number 4 -Name "TEST_optional" -Cmd "_debug\test_optional.py" -TimeoutSec 30 -Optional
$sw4.Stop()
"TEST_4 optional: ok=$ok4 duration=$([int]$sw4.Elapsed.TotalSeconds)s sidecar=$(Get-Content '_debug\stage_logs\20260915_stage4_TEST_optional.exit' -Raw).Trim()"

"" + "PASS=" + (((($ok1 -and -not $ok2 -and -not $ok3 -and $ok4) -as [bool])).ToString())
