# register_nightly_health_cron.ps1 — D056-2 hardening
# Run this ONCE as Administrator to register the nightly-health watchdog cron.
# After registration, runs every 30m at 22:30-02:00, plus 02:30/04:00/06:00.
# processes (PowerShell + python wrapper) and force-fails them so the next
# scheduled run can take over without manual intervention.
#
# Run as admin:  powershell -NoProfile -ExecutionPolicy Bypass -File register_nightly_health_cron.ps1
$ErrorActionPreference = "Stop"
$TaskName = "tw-invest-suite-nightly-health"
$Script = "C:\Users\icemo\Projects\tw-invest-suite\scripts\nightly_health_daily.ps1"
$PythonExe = "C:\Python314\python.exe"
$Action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Script`""
$Window = New-ScheduledTaskTrigger -Daily -At "22:30"
$Repeat = New-ScheduledTaskTrigger -Once -At "22:30" `
    -RepetitionInterval (New-TimeSpan -Minutes 30) -RepetitionDuration (New-TimeSpan -Hours 4)
$Window.Repetition = $Repeat.Repetition
$Triggers = @(
    $Window,
    (New-ScheduledTaskTrigger -Daily -At "02:30"),
    (New-ScheduledTaskTrigger -Daily -At "04:00"),
    (New-ScheduledTaskTrigger -Daily -At "06:00")
)
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Highest
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -MultipleInstances IgnoreNew
$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Existing) {
    # Preserve credentials, action and all existing operational settings.
    Set-ScheduledTask -TaskName $TaskName -Trigger $Triggers | Out-Null
} else {
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Triggers `
        -Principal $Principal -Settings $Settings | Out-Null
}
Write-Host "[ok] registered $TaskName (22:30-02:00 every 30m; 02:30/04:00/06:00)"
Get-ScheduledTaskInfo -TaskName $TaskName | Select-Object TaskName, NextRunTime, LastRunTime
