#requires -Version 5.1
[CmdletBinding()]
param([switch]$Unregister, [switch]$SelfCheck)
$ErrorActionPreference = 'Stop'
$TaskName = 'tw-invest-suite-news-refresh'
$ScriptDir = 'C:\Users\icemo\.claude\skills\tw-invest-suite\scripts'
$Cmd = Join-Path $ScriptDir 'news_refresh_watchlist.py'
if ($Unregister) {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
  Write-Output "Unregistered $TaskName"
  exit 0
}
if ($SelfCheck) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) {
        $existing | Select-Object TaskName,State,@{N='UserId';E={$_.Principal.UserId}},@{N='LogonType';E={$_.Principal.LogonType}},@{N='RunLevel';E={$_.Principal.RunLevel}},@{N='Triggers';E={$_.Triggers.Count}} | ConvertTo-Json -Compress
    } else {
        Write-Output "MISSING: $TaskName"
    }
    exit 0
}
if (-not (Test-Path -LiteralPath $Cmd)) { throw "Missing launcher: $Cmd" }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$admin = ([Security.Principal.WindowsPrincipal]$identity).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $admin) { throw 'Run this from an elevated PowerShell (right-click / Run as administrator).' }
$action = New-ScheduledTaskAction -Execute 'C:\Python314\python.exe' -Argument "-X utf8 `"$Cmd`"" -WorkingDirectory $ScriptDir
# Eight independent daily triggers: 08, 10, 12, 14, 16, 18, 20 and 22.
$triggers = @()
foreach ($hour in 8, 10, 12, 14, 16, 18, 20, 22) {
    $triggers += New-ScheduledTaskTrigger -Daily -At (Get-Date -Hour $hour -Minute 0 -Second 0)
}
if ($triggers.Count -ne 8) { throw "Expected 8 triggers, got $($triggers.Count)" }
$settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15)
$principal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType S4U -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Description 'News-only refresh for the live C:\Groove-Lab\watchlist.html. Preserves certified public artifacts and does not push GitHub Pages.' -Force | Out-Null
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName,State,@{N='UserId';E={$_.Principal.UserId}},@{N='LogonType';E={$_.Principal.LogonType}},@{N='Triggers';E={$_.Triggers.Count}} | ConvertTo-Json -Compress
