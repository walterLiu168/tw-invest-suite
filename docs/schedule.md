# Schedule — 每日 22:25 自動排程

## Windows Task Scheduler 設定

任務名稱：`tw-invest-suite-daily`

觸發：每日 22:25

動作：PowerShell 跑 `scripts\run_daily.ps1`

## 安裝

```powershell
# 自動建立（用 schtasks + XML）
$xml = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>tw-invest-suite 每日 batch（yfinance + FinMind + render + publish）</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2026-08-12T22:25:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>S-1-5-21-...</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT6H</ExecutionTimeLimit>
  </Settings>
  <Actions>
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-NoProfile -ExecutionPolicy Bypass -File "C:\Users\icemo\Projects\tw-invest-suite\scripts\run_daily.ps1"</Arguments>
    </Exec>
  </Actions>
</Task>
"@

$xmlPath = "$env:TEMP\tw-invest-suite-daily.xml"
$xml | Out-File -FilePath $xmlPath -Encoding Unicode

schtasks /Create /TN "tw-invest-suite-daily" /XML $xmlPath /F
```

## 移除

```powershell
schtasks /Delete /TN "tw-invest-suite-daily" /F
```

## 立即手動跑

```powershell
# 從 Task Scheduler UI
Get-ScheduledTask -TaskName "tw-invest-suite-daily" | Start-ScheduledTask

# 或直接跑
.\scripts\run_daily.ps1
```

## 監控

```powershell
# 狀態
Get-ScheduledTask -TaskName "tw-invest-suite-daily" | Get-ScheduledTaskInfo

# 最後 log
Get-Content C:\Users\icemo\Projects\tw-invest-suite\scripts\_debug\daily_status.json

# 完整健康檢查
.\scripts\daily_status_check.ps1
```

## Stage 預估時間

| Stage | 預估 | 說明 |
|---|---|---|
| 1. yfinance batch | ~10 min | 1,962 隻 × yf.Ticker |
| 2. FinMind PE/div/fin/month | ~80 min | 4 datasets × 1,962 隻 × 1.05s |
| 3. FinMind news (watchlist only) | ~5 min | 24 隻 × 4h 新聞 |
| 4. Cross-source assemble | ~6 min | 1,962 隻 DB query |
| 5. Render | ~50 min | 1,962 隻 × 17 tabs × 8 workers |
| 6. Patterns classify | ~10 min | 1,962 隻 × 8 patterns |
| 7. Publish | ~2 min | GitHub Pages + groovelab.dev |
| **總計** | **~3 hr** | 平日 |

週末模式跳 stage 1-3，只跑 4-7：**~70 min**
