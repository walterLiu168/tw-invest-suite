# Physical sleep / wake proof for the scheduled tasks.
#
# Background (measured 2026-11-20): this machine has never resumed from sleep.
# powercfg /lastwake reports 0 wake records, the last Kernel-Power "entering
# sleep" is 2026-07-25 22:23 and it ended in a hard reboot, and the box has
# been up since 2026-09-12 07:52 (69 days).  The capability IS configured -
# RTCWAKE (allow wake timers) is 0x1 Enabled, HYBRIDSLEEP is enabled and S3 is
# available - it simply never fires, because STANDBYIDLE (idle sleep timeout)
# is 0 (never sleep on idle).
#
# So the proof has to be a controlled suspend.  Two tasks:
#   arm  - waits for an idle window, records the pre-suspend state, then
#          suspends the box (S3) after detaching
#   wake - must be armed with WakeToRun so the RTC alarm fires and the box
#          comes back; it records what actually woke it
#
# Usage:
#   powershell -File scripts\sleep_wake_proof.ps1 -Mode arm
#   powershell -File scripts\sleep_wake_proof.ps1 -Mode wake
param(
    [ValidateSet('arm', 'wake', 'status')] [string]$Mode = 'status'
)

$ErrorActionPreference = 'Stop'
$OutDir = Join-Path $PSScriptRoot '_debug'
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$Stamp = Join-Path $OutDir 'sleep_wake_proof.json'
$ArmMarker = Join-Path $OutDir 'sleep_wake_proof.armed'

function Write-Receipt($payload) {
    $payload | ConvertTo-Json -Depth 6 | Set-Content -Path $Stamp -Encoding UTF8
    Write-Output ("sleep_wake_proof -> " + $Stamp)
}

function Get-PowerEvents {
    $rows = @()
    try {
        $events = Get-WinEvent -FilterHashtable @{ LogName = 'System';
            ProviderName = 'Microsoft-Windows-Kernel-Power' } -MaxEvents 80 -ErrorAction Stop
        foreach ($e in $events) {
            if ($e.Id -in 42, 1, 107, 41) {
                $rows += [pscustomobject]@{ id = [int]$e.Id
                    when = $e.TimeCreated.ToString('o')
                    message = (($e.Message -replace "`r`n", ' ') -replace '\s+', ' ') }
            }
        }
    } catch { }
    return $rows
}

function Get-BootTime {
    try { return (Get-CimInstance Win32_OperatingSystem).LastBootUpTime.ToString('o') }
    catch { return '' }
}

function Test-Idle {
    $busy = @()
    $procs = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -match 'run_daily|daily_certification_catchup|publish_verified|publish_ghpages|train_daily2|stock_chip_features' }
    if ($procs) { $busy += 'process: ' + (($procs | Select-Object -First 3).ProcessId -join ',') }
    foreach ($name in @('tw-invest-suite-daily-report', 'tw-invest-suite-finmind-download')) {
        $t = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        if ($t -and $t.State -eq 'Running') { $busy += "task:$name" }
    }
    return $busy
}

if ($Mode -eq 'status') {
    Write-Output ('boot time      : ' + (Get-BootTime))
    Write-Output ('arm marker     : ' + (Test-Path $ArmMarker))
    Write-Output ('receipt        : ' + (Test-Path $Stamp))
    Write-Output ('busy now       : ' + ((Test-Idle) -join '; '))
    Write-Output '--- power events (42 sleep / 1 resume / 107 hibernate-resume / 41 unclean) ---'
    Get-PowerEvents | Select-Object -First 8 | ForEach-Object { Write-Output ("  " + $_) }
    exit 0
}

if ($Mode -eq 'arm') {
    if (-not (Test-Path $ArmMarker)) {
        Write-Output 'not armed (marker missing) - nothing to do'
        exit 2
    }
    $deadline = (Get-Date).AddMinutes(45)
    while ((Get-Date) -lt $deadline) {
        $busy = Test-Idle
        if (-not $busy) { break }
        Write-Output ("busy, waiting: " + ($busy -join '; '))
        Start-Sleep -Seconds 60
    }
    $busy = Test-Idle
    if ($busy) {
        Write-Receipt @{ mode = 'arm'; status = 'skipped_busy'; busy = $busy
            at = (Get-Date).ToString('o') }
        exit 3
    }
    $pre = @{
        mode = 'arm'; status = 'armed'; at = (Get-Date).ToString('o')
        boot_time = (Get-BootTime)
        suspend_at = (Get-Date).AddSeconds(20).ToString('o')
        power_events_before = (Get-PowerEvents)
    }
    Write-Receipt $pre
    # Detach, then suspend the box.  SetSuspendState needs SeShutdownPrivilege,
    # which a Limited (unelevated) token does not have, so the primary path is
    # the shell's own power command broadcast - the same request the Start
    # menu's Sleep sends - which needs no elevation as long as the task runs
    # in the interactive session (registered with LogonType Interactive).
    Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', @'
$ErrorActionPreference = 'SilentlyContinue'
Add-Type -Namespace Win32 -Name P -MemberDefinition @"
[DllImport("user32.dll", SetLastError=true)]
public static extern IntPtr SendMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);
"@
Start-Sleep -Seconds 5
[Win32.P]::SendMessage([IntPtr]0xffff, 0x0112, [IntPtr]0xF170, [IntPtr]2)
Start-Sleep -Seconds 5
Start-Process -FilePath 'rundll32.exe' -ArgumentList 'powrprof.dll,SetSuspendState','0','1','0' | Out-Null
'@) | Out-Null
    Start-Sleep -Seconds 20
    exit 0
}

# Mode = wake
$events = Get-PowerEvents
$pre = @{}
if (Test-Path $Stamp) {
    try { $pre = Get-Content $Stamp -Raw | ConvertFrom-Json } catch { $pre = @{} }
}
$suspendAt = $null
if ($pre -and $pre.PSObject.Properties.Name -contains 'suspend_at') { $suspendAt = [datetime]$pre.suspend_at }
$after = @($events | Where-Object { $suspendAt -and ([datetime]$_.when) -gt $suspendAt })
$resumed = @($after | Where-Object { $_.id -in 1, 107 }).Count -gt 0
$unclean = @($after | Where-Object { $_.id -eq 41 }).Count -gt 0
$boot = Get-BootTime
$receipt = @{
    mode = 'wake'
    status = $(if ($resumed) { 'woke_from_sleep' } elseif ($unclean) { 'rebooted_unclean' } else { 'ran_without_sleep_event' })
    at = (Get-Date).ToString('o')
    suspend_at = $(if ($suspendAt) { $suspendAt.ToString('o') } else { '' })
    boot_time_after = $boot
    boot_time_before = $(if ($pre -and $pre.PSObject.Properties.Name -contains 'boot_time') { $pre.boot_time } else { '' })
    boot_time_unchanged = ($boot -eq $(if ($pre -and $pre.PSObject.Properties.Name -contains 'boot_time') { $pre.boot_time } else { '' }))
    resumed_by_scheduler = $resumed
    unclean_reboot = $unclean
    power_events_after = $after
    lastwake = (& powercfg /lastwake 2>&1 | Out-String).Trim()
}
Write-Receipt $receipt
Remove-Item -Path $ArmMarker -ErrorAction SilentlyContinue
exit 0
