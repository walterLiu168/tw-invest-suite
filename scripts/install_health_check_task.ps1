param(
    [switch]$SelfCheck,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$TaskName = 'tw-invest-suite-health-check'
$Script = 'C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug\check_openalice_health.py'
$LogDir = 'C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug\health_logs'
$Py = 'python'

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false | Out-Null
        Write-Output "Unregistered: $TaskName"
    } else {
        Write-Output "Not found: $TaskName"
    }
    exit 0
}

if (-not (Test-Path -LiteralPath $Script -PathType Leaf)) {
    throw "Missing check script: $Script"
}
if (-not (Test-Path -LiteralPath $LogDir -PathType Container)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

$today = Get-Date -Format 'yyyy-MM-dd'
$logFile = Join-Path $LogDir "health_${today}.log"

# Action: run the check, log to file, exit code reflects pass/fail
$action = New-ScheduledTaskAction `
    -Execute $Py `
    -Argument "`"$Script`" --json" `
    -WorkingDirectory (Split-Path -Parent $Script)

# Trigger: every day at 23:00 (after 22:25 tw-invest-suite batch finishes)
$trigger = New-ScheduledTaskTrigger -Daily -At '23:00'

$principal = New-ScheduledTaskPrincipal `
    -UserId ("{0}\{1}" -f $env:USERDOMAIN, $env:USERNAME) `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable

if ($SelfCheck) {
    Write-Output "Script: $Script (exists: $([bool](Test-Path $Script)))"
    Write-Output "LogDir: $LogDir (exists: $([bool](Test-Path $LogDir)))"
    Write-Output "TaskName: $TaskName"
    Write-Output "Trigger: daily 23:00"
    Write-Output "SELF-CHECK PASS"
    exit 0
}

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false | Out-Null
    Write-Output "Unregistered old: $TaskName"
}

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Principal $principal `
    -Settings $settings `
    -Description "Daily self-check of OpenAlice + tw-invest-suite schedule. Verifies each task ran and DB data landed. Run after 22:25 batch." `
    -Force | Out-Null

Write-Output "Registered: $TaskName (daily 23:00)"
Write-Output "Script:     $Script"
Write-Output "JSON log:   $LogDir\health_<date>.log"
Write-Output "Exit code 0 = all OK, exit 1 = some failures (see JSON log)"
