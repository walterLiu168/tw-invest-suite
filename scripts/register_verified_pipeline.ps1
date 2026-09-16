# Update existing tasks only; preserve their identities and existing triggers.
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$backup = Join-Path $PSScriptRoot '_debug\scheduler_backup_20260916'
New-Item -ItemType Directory -Force -Path $backup | Out-Null
$log = Join-Path $backup 'deployment.log'
Start-Transcript -Path $log -Append | Out-Null
try {
    $names = @('tw-invest-suite-daily-report', 'tw-invest-suite-publish',
               'tw-invest-suite-health-check', 'tw-invest-suite-nightly-health',
               'OpenAlice Weekly Shareholding 1330', 'OpenAlice RSS Refresh Every 2h')
    foreach ($name in $names) {
        $task = Get-ScheduledTask -TaskName $name -ErrorAction Stop
        $safeName = $name -replace '[^a-zA-Z0-9_-]', '_'
        $xml = Join-Path $backup ($safeName + '.xml')
        if (-not (Test-Path -LiteralPath $xml)) {
            Export-ScheduledTask -TaskName $name | Out-File -LiteralPath $xml -Encoding Unicode
        }
        $task.Settings.WakeToRun = $true
        $task.Settings.StartWhenAvailable = $true
        $task.Settings.DisallowStartIfOnBatteries = $false
        $task.Settings.StopIfGoingOnBatteries = $false
        if ($name -eq 'tw-invest-suite-health-check') {
            $runtime = 'C:\Users\icemo\.claude\skills\tw-invest-suite\scripts'
            $task.Actions = @(New-ScheduledTaskAction -Execute 'C:\Python314\python.exe' -Argument ('-X utf8 "' + $runtime + '\check_openalice_health.py" --json') -WorkingDirectory $runtime)
        }
        if ($name -eq 'OpenAlice Weekly Shareholding 1330') {
            $task.Actions = @(New-ScheduledTaskAction -Execute $task.Actions[0].Execute -Argument '-X utf8 "D:\CODEX\AI-Telegram\strategy_lab\_fetch_today.py" --phase weekly --max-requests-per-minute 57 --no-csv --no-invalidate-cache --no-derived' -WorkingDirectory 'D:\CODEX\AI-Telegram')
            $task.Triggers = @(New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At '21:10')
        }
        if ($name -eq 'OpenAlice RSS Refresh Every 2h' -and $task.Actions[0].Arguments -notmatch '^-X utf8 ') {
            $task.Actions[0].Arguments = '-X utf8 ' + $task.Actions[0].Arguments
        }
        # S4U runs while signed out, using the existing account without storing a password.
        if ($name -in @('tw-invest-suite-daily-report', 'tw-invest-suite-publish', 'tw-invest-suite-health-check', 'OpenAlice Weekly Shareholding 1330', 'OpenAlice RSS Refresh Every 2h')) {
            $task.Principal = New-ScheduledTaskPrincipal -UserId $task.Principal.UserId -LogonType S4U -RunLevel $task.Principal.RunLevel
        }
        # Only failed tasks retry; analytical completion gates remain authoritative.
        if ($name -in @('tw-invest-suite-daily-report', 'tw-invest-suite-publish', 'OpenAlice Weekly Shareholding 1330', 'OpenAlice RSS Refresh Every 2h')) {
            $task.Settings.RestartCount = 1
            $task.Settings.RestartInterval = 'PT10M'
        }
        Set-ScheduledTask -InputObject $task -ErrorAction Stop | Out-Null
        $actual = Get-ScheduledTask -TaskName $name
        if (-not $actual.Settings.WakeToRun) { throw "WakeToRun verification failed: $name" }
        Write-Output "UPDATED $name logon=$($actual.Principal.LogonType) wake=$($actual.Settings.WakeToRun) retries=$($actual.Settings.RestartCount)"
    }
} finally {
    Stop-Transcript | Out-Null
}
