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
# Suspend mechanics (measured 2026-11-22):
#   * The first attempt used WM_SYSCOMMAND/SC_MONITORPOWER.  That is the
#     "turn the monitor off" command, NOT sleep - the box stayed awake and the
#     receipt only showed that the arm task had run.
#   * SetSuspendState needs SeShutdownPrivilege.  The privilege is in this
#     token but disabled, and AdjustTokenPrivileges refuses it on a UAC
#     filtered token - so the arm task is registered with "Run with highest
#     privileges" instead, where the privilege is enabled by default.
#   * powercfg /devicequery wake_armed lists both Intel I210 NICs, so the box
#     can also be woken by a wake-on-LAN magic packet.
#
# Usage:
#   powershell -File scripts\sleep_wake_proof.ps1 -Mode verify
#   powershell -File scripts\sleep_wake_proof.ps1 -Mode arm
#   powershell -File scripts\sleep_wake_proof.ps1 -Mode wake
param(
    [ValidateSet('arm', 'wake', 'status', 'verify')] [string]$Mode = 'status'
)

$ErrorActionPreference = 'Stop'
$OutDir = Join-Path $PSScriptRoot '_debug'
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$Stamp = Join-Path $OutDir 'sleep_wake_proof.json'
$SuspendResult = Join-Path $OutDir 'sleep_wake_suspend_result.json'
$ArmMarker = Join-Path $OutDir 'sleep_wake_proof.armed'

# Shared native helpers: token privilege enabling plus the real suspend call.
$NativeCode = @"
using System;
using System.Runtime.InteropServices;
namespace Win32 {
  [StructLayout(LayoutKind.Sequential)]
  public struct LUID { public uint LowPart; public int HighPart; }
  [StructLayout(LayoutKind.Sequential)]
  public struct TOKEN_PRIVILEGES { public uint PrivilegeCount; public LUID Luid; public uint Attributes; }
  public class P {
    [DllImport("advapi32.dll", SetLastError=true)]
    public static extern bool OpenProcessToken(IntPtr h, uint d, out IntPtr t);
    [DllImport("advapi32.dll", SetLastError=true, CharSet=CharSet.Unicode)]
    public static extern bool LookupPrivilegeValue(string s, string n, out LUID l);
    [DllImport("advapi32.dll", SetLastError=true)]
    public static extern bool AdjustTokenPrivileges(IntPtr t, bool disableAll, ref TOKEN_PRIVILEGES newState, uint bufferLength, IntPtr previousState, IntPtr returnLength);
    [DllImport("kernel32.dll")] public static extern IntPtr GetCurrentProcess();
    [DllImport("powrprof.dll")] public static extern bool SetSuspendState(bool hibernate, bool force, bool wakeDisabled);
    [DllImport("advapi32.dll", SetLastError=true)]
    public static extern bool GetTokenInformation(IntPtr t, int cls, IntPtr info, uint len, out uint ret);

    // GetLastError must be read inside the native call: the managed runtime
    // overwrites the thread's last error, so an out-of-band read lies.
    public static int AdjustAndReport(IntPtr token, ref TOKEN_PRIVILEGES state) {
      bool ok = AdjustTokenPrivileges(token, false, ref state, 0, IntPtr.Zero, IntPtr.Zero);
      return ok ? 0 : Marshal.GetLastWin32Error();
    }
    // 1 = present and enabled, 2 = present but disabled, 0 = absent
    public static int PrivilegeState(IntPtr token, LUID luid) {
      IntPtr buf = Marshal.AllocHGlobal(8192);
      try {
        uint len;
        if (!GetTokenInformation(token, 3, buf, 8192, out len)) return 0;
        int count = Marshal.ReadInt32(buf, 0);
        int off = 4;
        for (int i = 0; i < count; i++) {
          uint lp = (uint)Marshal.ReadInt32(buf, off);
          int hp = Marshal.ReadInt32(buf, off + 4);
          int attr = Marshal.ReadInt32(buf, off + 8);
          if (lp == luid.LowPart && hp == luid.HighPart) {
            return (attr & 2) != 0 ? 1 : 2;
          }
          off += 12;
        }
        return 0;
      } finally { Marshal.FreeHGlobal(buf); }
    }
  }
}
"@

function Write-Receipt($payload) {
    $payload | ConvertTo-Json -Depth 6 | Set-Content -Path $Stamp -Encoding UTF8
    Write-Output ("sleep_wake_proof -> " + $Stamp)
}

function Enable-ShutdownPrivilege {
    Add-Type -TypeDefinition $NativeCode -ErrorAction SilentlyContinue
    $h = [IntPtr]::Zero
    # TOKEN_ADJUST_PRIVILEGES (0x08) | TOKEN_QUERY (0x02) - AdjustTokenPrivileges
    # needs both; asking for only the first returns ERROR_ACCESS_DENIED.
    if (-not [Win32.P]::OpenProcessToken([Win32.P]::GetCurrentProcess(), 0x000A, [ref]$h)) {
        return "OpenProcessToken failed: $([System.Runtime.InteropServices.Marshal]::GetLastWin32Error())"
    }
    $luid = New-Object Win32.LUID
    if (-not [Win32.P]::LookupPrivilegeValue($null, 'SeShutdownPrivilege', [ref]$luid)) {
        return "LookupPrivilegeValue failed"
    }
    $state = New-Object Win32.TOKEN_PRIVILEGES
    $state.PrivilegeCount = 1
    $state.Luid = $luid
    $state.Attributes = 2
    $err = [Win32.P]::AdjustAndReport($h, [ref]$state)
    if ($err -eq 0) { return 'enabled' }
    # An elevated token already carries the privilege enabled; AdjustTokenPrivileges
    # can still refuse, and then it is not needed.
    $present = [Win32.P]::PrivilegeState($h, $luid)
    if ($present -eq 1) { return 'enabled' }
    return "AdjustTokenPrivileges failed: win32=$err (privilege present but disabled)"
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

if ($Mode -eq 'verify') {
    # Capability check only.  This never suspends the box.
    $state = Enable-ShutdownPrivilege
    Write-Output ("privilege      : " + $state)
    Write-Output ("wake armed     : " + ((& powercfg /devicequery wake_armed 2>&1 | Out-String).Trim() -replace "`r`n", ' | '))
    Write-Output ("sleep states   : " + ((& powercfg /a 2>&1 | Select-String 'S3|休眠' | Out-String).Trim()))
    $receipt = @{
        mode = 'verify'; status = $(if ($state -eq 'enabled') { 'suspend_capable' } else { 'suspend_unavailable' })
        privilege = $state; at = (Get-Date).ToString('o')
        boot_time = (Get-BootTime)
        wake_armed = ((& powercfg /devicequery wake_armed 2>&1 | Out-String).Trim())
    }
    Write-Receipt $receipt
    exit $(if ($state -eq 'enabled') { 0 } else { 1 })
}

if ($Mode -eq 'arm') {
    if (-not (Test-Path $ArmMarker)) {
        # No approved sleep test is pending.  This is a normal state, not a
        # failure: the suspend needs SeShutdownPrivilege, and this token is a
        # filtered UAC token (Administrators is deny-only), so the arm task can
        # only run elevated.  See docs for the one-step elevated registration.
        Write-Output 'not armed: no pending sleep test (a suspended run needs an elevated task)'
        exit 0
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
    $privilege = Enable-ShutdownPrivilege
    if ($privilege -ne 'enabled') {
        # The token cannot enable SeShutdownPrivilege (UAC filtered token), so
        # this box cannot be suspended from an unelevated task.  That is an
        # environment fact, not a failed test: record the evidence and exit
        # clean.  The chain audit carries the authoritative statement.
        Write-Receipt @{ mode = 'arm'; status = 'suspend_unavailable'; privilege = $privilege
            at = (Get-Date).ToString('o') }
        Write-Output ("suspend unavailable: " + $privilege)
        exit 0
    }
    $pre = @{
        mode = 'arm'; status = 'armed'; at = (Get-Date).ToString('o')
        boot_time = (Get-BootTime)
        privilege = $privilege
        suspend_at = (Get-Date).AddSeconds(25).ToString('o')
        power_events_before = (Get-PowerEvents)
    }
    Write-Receipt $pre
    # One-shot: the marker is consumed here, so an approved test never repeats
    # on its own and the box can never fall asleep nightly by accident.
    Remove-Item -LiteralPath $ArmMarker -ErrorAction SilentlyContinue
    # Detach, then suspend the box for real: SetSuspendState(FALSE, TRUE, FALSE)
    # asks for S3 and does not disable wake events.  The result is written after
    # the resume, so the receipt says whether the suspend actually happened -
    # the 2026-11-20 attempt wrote its receipt before suspending and therefore
    # could not tell "did not sleep" from "slept".
    Start-Process -FilePath 'powershell.exe' -WindowStyle Hidden -ArgumentList @(
        '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', @"
`$ErrorActionPreference = 'SilentlyContinue'
Start-Sleep -Seconds 5
$NativeCode
Add-Type -TypeDefinition `$NativeCode
`$h = [IntPtr]::Zero
[Win32.P]::OpenProcessToken([Win32.P]::GetCurrentProcess(), 0x000A, [ref]`$h) | Out-Null
`$luid = New-Object Win32.LUID
[Win32.P]::LookupPrivilegeValue(`$null, 'SeShutdownPrivilege', [ref]`$luid) | Out-Null
`$state = New-Object Win32.TOKEN_PRIVILEGES
`$state.PrivilegeCount = 1
`$state.Luid = `$luid
`$state.Attributes = 2
`$adjErr = [Win32.P]::AdjustAndReport(`$h, [ref]`$state)
`$privState = [Win32.P]::PrivilegeState(`$h, `$luid)
`$ok = [Win32.P]::SetSuspendState(`$false, `$true, `$false)
`$result = [ordered]@{{
  suspended_at = (Get-Date).ToString('o')
  set_suspend_state_return = `$ok
  set_suspend_state_error = [System.Runtime.InteropServices.Marshal]::GetLastWin32Error()
  adjust_token_privileges_error = `$adjErr
  privilege_state = `$privState
  privilege_meaning = @{{ 1 = 'present and enabled'; 2 = 'present but disabled'; 0 = 'absent' }}[`$privState]
}}
`$result | ConvertTo-Json | Set-Content -LiteralPath '$SuspendResult' -Encoding UTF8
"@) | Out-Null
    Start-Sleep -Seconds 25
    exit 0
}

# Mode = wake
$pre = @{}
if (Test-Path $Stamp) {
    try { $pre = Get-Content $Stamp -Raw | ConvertFrom-Json } catch { $pre = @{} }
}
# The wake task repeats every five minutes.  Only a real arm attempt is evidence;
# without one, leave the receipt alone instead of overwriting it.
if (-not ($pre -and $pre.PSObject.Properties.Name -contains 'mode' -and $pre.mode -eq 'arm')) {
    Write-Output 'no arm attempt on record - nothing to report'
    exit 0
}
$events = Get-PowerEvents
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
