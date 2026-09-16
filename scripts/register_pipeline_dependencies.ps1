# Make the enabled existing analytical/data tasks available while signed out.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$backup = Join-Path $PSScriptRoot '_debug\scheduler_backup_20260916'
New-Item -ItemType Directory -Force -Path $backup | Out-Null
Start-Transcript -Path (Join-Path $backup 'dependencies-deployment.log') -Append | Out-Null
try {
    $tasks = Get-ScheduledTask | Where-Object { $_.TaskName -match '^(tw-invest-suite-|OpenAlice )' -and $_.State -ne 'Disabled' }
    foreach ($task in $tasks) {
        $name = $task.TaskName
        $safe = $name -replace '[^a-zA-Z0-9_-]', '_'
        $xml = Join-Path $backup ($safe + '.xml')
        if (-not (Test-Path -LiteralPath $xml)) { Export-ScheduledTask -TaskName $name | Out-File -LiteralPath $xml -Encoding Unicode }
        $task.Principal = New-ScheduledTaskPrincipal -UserId $task.Principal.UserId -LogonType S4U -RunLevel $task.Principal.RunLevel
        $task.Settings.WakeToRun = $true
        $task.Settings.StartWhenAvailable = $true
        $task.Settings.DisallowStartIfOnBatteries = $false
        $task.Settings.StopIfGoingOnBatteries = $false
        if ($name -eq 'tw-invest-suite-publish') {
            $task.Actions = @(New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -ExecutionPolicy Bypass -File "' + (Join-Path $PSScriptRoot 'publish_verified_sites.ps1') + '"') -WorkingDirectory $PSScriptRoot)
        } elseif ($name -eq 'tw-invest-suite-yfinance') {
            $runtime = 'C:\Users\icemo\.claude\skills\tw-invest-suite\scripts'
            $task.Actions = @(New-ScheduledTaskAction -Execute 'C:\Python314\python.exe' -Argument ('-X utf8 "' + $runtime + '\yfinance_daily.py"') -WorkingDirectory $runtime)
        } elseif ($name -like 'OpenAlice *' -and $task.Actions[0].Execute -like '*python.exe' -and $task.Actions[0].Arguments -notmatch '^-X utf8 ') {
            $task.Actions[0].Arguments = '-X utf8 ' + $task.Actions[0].Arguments
        }
        Set-ScheduledTask -InputObject $task | Out-Null
        $actual = Get-ScheduledTask -TaskName $name
        if ($actual.Principal.LogonType -ne 'S4U' -or -not $actual.Settings.WakeToRun) { throw "Dependency verification failed: $name" }
        Write-Output "UPDATED $name"
    }
} finally { Stop-Transcript | Out-Null }
