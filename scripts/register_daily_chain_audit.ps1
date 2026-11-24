[CmdletBinding()]
param([switch]$Unregister)
$ErrorActionPreference = 'Stop'
$TaskName = 'tw-invest-suite-daily-chain-audit'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Cmd = Join-Path $ScriptDir 'run_daily_chain_audit.cmd'
if ($Unregister) {
  Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
  exit 0
}
if (-not (Test-Path -LiteralPath $Cmd)) { throw "Missing launcher: $Cmd" }
$action = New-ScheduledTaskAction -Execute $Cmd -WorkingDirectory $ScriptDir
$trigger = New-ScheduledTaskTrigger -Daily -At 06:30
$settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType S4U -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Read-only D056-3 tw-invest-suite and AI-Telegram daily chain audit; no ChatGPT dependency.' -Force | Out-Null
Write-Output (Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName,State,TaskPath | ConvertTo-Json -Compress)
