# tw-invest-suite daily status check
# Usage: powershell -File daily_status_check.ps1
#         powershell -File daily_status_check.ps1 -Json

[CmdletBinding()]
param([switch]$Json)

$scriptDir = "C:\Users\icemo\.claude\skills\tw-invest-suite\scripts"
$cacheDir = "$scriptDir\_cache"
$outputDir = "C:\Groove-Lab\analyze"

$dow = (Get-Date).DayOfWeek.value__
$isWeekend = ($dow -eq 0 -or $dow -eq 6)
$dowName = (Get-Date).DayOfWeek.ToString()
$dateStr = Get-Date -Format "yyyy-MM-dd"

if ($Json) {
    $status = @{
        date = $dateStr
        day_of_week = $dowName
        is_weekend = $isWeekend
        skip_download_recommended = $isWeekend
    }
    $status | ConvertTo-Json
    exit 0
}

function Section {
    param($title)
    Write-Host ""
    Write-Host "== $title =="
}

Section "tw-invest-suite Status"
Write-Host ("Date: {0} ({1})" -f $dateStr, $dowName)
Write-Host ("Weekend: {0}" -f $(if ($isWeekend) { 'YES - skip download' } else { 'NO - can download' }))

Section "MySQL DB"
& python "$scriptDir\_debug\db_status.py" 2>&1 | ForEach-Object { Write-Host "  $_" }

Section "Scheduled Task"
schtasks /Query /TN "tw-invest-suite-daily-report" /FO LIST /V 2>&1 |
    Select-String -Pattern 'Status|Next Run|Last Run|Last Result' |
    ForEach-Object { Write-Host ("  " + $_.Line.Trim()) }

Section "Latest daily log"
$latestLog = Get-ChildItem "$scriptDir\_debug\daily_run_*.log" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($latestLog) {
    Write-Host ("  File: {0} ({1} bytes, {2})" -f $latestLog.Name, $latestLog.Length, $latestLog.LastWriteTime)
    Get-Content $latestLog.FullName -Tail 5 -ErrorAction SilentlyContinue |
        ForEach-Object { Write-Host ("    " + $_) }
} else {
    Write-Host "  (no log file)"
}

Section "HTML output"
$todayStart = Get-Date -Hour 0 -Minute 0 -Second 0
$newFiles = @(Get-ChildItem $outputDir -Filter "*.html" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -ge $todayStart })
$newestFile = Get-ChildItem $outputDir -Filter "*.html" -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1
Write-Host ("  Today produced: {0}" -f $newFiles.Count)
if ($newestFile) {
    Write-Host ("  Newest: {0} ({1})" -f $newestFile.Name, $newestFile.LastWriteTime.ToString('HH:mm:ss'))
}

Section "Status JSON"
$statusFile = "$scriptDir\_debug\daily_status.json"
if (Test-Path $statusFile) {
    Get-Content $statusFile | ForEach-Object { Write-Host "  $_" }
} else {
    Write-Host "  (no status file)"
}
