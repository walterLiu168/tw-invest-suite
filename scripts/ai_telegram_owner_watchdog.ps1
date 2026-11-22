# Keep the AI-Telegram daily pipeline owner alive.
#
# The pipeline runs as a "forever owner": one long-lived cmd.exe loop that keeps
# executing run_pipeline_scheduled.py, which in turn fires the time-scheduled
# stages (18:00 finmind download, 22:00 margin, 22:32 review, ...).  The task
# uses MultipleInstances=IgnoreNew, so once an instance is registered the
# scheduler refuses every later trigger with 0x800710E0.
#
# That is only safe while the owner process is actually alive.  When the owner
# died (2026-11-21 23:07) the scheduler kept the task in the Running state
# forever: every trigger was refused, nothing ran for days, and the only way
# out was a manual Stop-ScheduledTask.
#
# This watchdog does that automatically: a Running task with no owner process
# is a stale instance - clear it, then start a fresh owner.  Restart storms are
# bounded by a cooldown, and a pause marker file stops the restarts.
param(
    [int]$CooldownMinutes = 30
)

$ErrorActionPreference = 'SilentlyContinue'
$OutDir = Join-Path $PSScriptRoot '_debug'
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$Log = Join-Path $OutDir 'ai_telegram_owner_watchdog.log'
$StateFile = Join-Path $OutDir 'ai_telegram_owner_watchdog.state.json'
$PauseMarker = Join-Path $OutDir 'ai_telegram_owner_pause.marker'
$TaskName = 'AI-Telegram Scheduled Pipeline'
$OwnerRoot = 'D:\CODEX\AI-Telegram'
$Heartbeat = Join-Path $OwnerRoot '.codex-work-state\owner_heartbeat.txt'
# A stage can legitimately run for a long time, so the heartbeat alone is not
# enough: the pipeline python process is the second, immediate liveness signal.
$HeartbeatMaxAgeMinutes = 45

function Log([string]$Message) {
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message"
    Add-Content -LiteralPath $Log -Value $line -Encoding UTF8
    Write-Output $line
}

function Test-OwnerAlive {
    if (Test-Path $Heartbeat) {
        $age = (Get-Date) - (Get-Item $Heartbeat).LastWriteTime
        if ($age.TotalMinutes -lt $HeartbeatMaxAgeMinutes) { return $true }
    }
    $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'run_pipeline_scheduled' }
    return @($procs).Count -gt 0
}

if (Test-Path $PauseMarker) {
    Log 'paused (marker present) - not touching the owner task'
    exit 0
}

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if (-not $task) {
    Log "task '$TaskName' not found - nothing to watch"
    exit 0
}

$alive = Test-OwnerAlive
$state = $task.State

if ($state -eq 'Running' -and -not $alive) {
    # Stale instance: the scheduler still thinks the owner is running.
    Log "stale instance detected (task=Running, owner process absent) - clearing it"
    Stop-ScheduledTask -TaskName $TaskName
    Start-Sleep -Seconds 2
    $state = (Get-ScheduledTask -TaskName $TaskName).State
}

if (-not $alive) {
    $last = $null
    if (Test-Path $StateFile) {
        try { $last = Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json } catch { $last = $null }
    }
    $elapsed = if ($last -and $last.restart_at) {
        (New-TimeSpan -Start ([datetime]$last.restart_at) -End (Get-Date)).TotalMinutes
    } else { [double]::MaxValue }
    if ($elapsed -ge $CooldownMinutes) {
        Log "owner process absent and task=$state - starting a fresh owner"
        Start-ScheduledTask -TaskName $TaskName
        @{ restart_at = (Get-Date).ToString('o'); task = $TaskName } |
            ConvertTo-Json | Set-Content -LiteralPath $StateFile -Encoding UTF8
        Start-Sleep -Seconds 5
        Log ("owner alive after restart: " + (Test-OwnerAlive))
    } else {
        Log ("owner absent but restarted $([int]$elapsed) min ago - inside cooldown, skipping")
    }
} else {
    Log "owner alive, task=$state - nothing to do"
}
exit 0
