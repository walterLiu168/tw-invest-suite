# Run through the normal Windows UAC prompt to install this existing-site recovery task.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$name = 'GrooveLab Site Recovery'
$backup = Join-Path $PSScriptRoot '_debug\scheduler_backup_20260916'
New-Item -ItemType Directory -Force -Path $backup | Out-Null
Start-Transcript -Path (Join-Path $backup 'groove-deployment.log') -Append | Out-Null
try {
    $existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    $xml = Join-Path $backup 'GrooveLab_Site_Recovery.xml'
    if ($null -ne $existing -and -not (Test-Path -LiteralPath $xml)) {
        Export-ScheduledTask -TaskName $name | Out-File -LiteralPath $xml -Encoding Unicode
    }
    $account = (Get-ScheduledTask -TaskName 'tw-invest-suite-daily-report').Principal.UserId
    $principal = New-ScheduledTaskPrincipal -UserId $account -LogonType S4U -RunLevel Limited
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $PSScriptRoot 'groove_service_watch.ps1') + '"') -WorkingDirectory 'C:\Groove-Lab'
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $trigger.Delay = 'PT1M'
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Keep the existing GrooveLab origin and named connector available after reboot; recover owned failed processes.' -Force | Out-Null
    $actual = Get-ScheduledTask -TaskName $name
    if ($actual.Principal.LogonType -ne 'S4U' -or $actual.Settings.ExecutionTimeLimit -ne 'PT0S') { throw 'Recovery task verification failed' }
    Start-ScheduledTask -TaskName $name
    Write-Output "REGISTERED $name logon=$($actual.Principal.LogonType)"
} finally { Stop-Transcript | Out-Null }
