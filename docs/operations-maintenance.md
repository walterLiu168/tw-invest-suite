# tw-invest-suite 維運與維護手冊

版本：2026-09-21
適用人員：值班工程師、發布負責人、接手 AI agent

## 1. 維運原則

1. 先確認資料日期與 `nightly_id`，再看 exit code。
2. timeout 只代表 inconclusive；檢查 process tree、heartbeat、state、artifact growth、DB 與 downstream receipts 後再決定是否重跑。
3. 不要同時啟動第二個 nightly、publisher 或 FinMind 大批次；mutex 與 source hash 契約要求單一 owner。
4. 不可從 picks 或舊 marker 製造 success marker。
5. 任何 Telegram 不確定回應都先查 ledger，不可盲目重送。

## 2. 已安裝的核心 Scheduler 任務

下面是目前認證過的任務類別。任務讀回應保持 `WakeToRun=True`、`StartWhenAvailable=True`；publisher 目前使用 `InteractiveToken`，其餘正常任務依部署設定使用 S4U 或既有登入型態。

| 任務 | 作用 |
|---|---|
| `tw-invest-suite-daily-report` | 22:25 產生、驗證並 certify nightly |
| `tw-invest-suite-publish` | 等待 certified marker，發布 GitHub/Groove/Telegram |
| `tw-invest-suite-market-screen` | 18:00 選股與 dated market-screen artifacts |
| `tw-invest-suite-marker-watchdog` | 檢查 marker，不會偽造成功 |
| `tw-invest-suite-health-check` | DB、排程、資料與外部健康檢查 |
| `tw-invest-suite-nightly-health` | 偵測卡住 owner、heartbeat deadline 與 stage gap |
| `tw-invest-suite-postflight` | 發布後本機與遠端結果檢查 |
| `AI-Telegram Daily Report 22-47` | AI-Telegram 全報告與 Telegram brief |
| `AI-Telegram Enrichment Update 18-25` | 補充 enrichment |
| `AI-Telegram Pattern Scan 18-30` | AI pattern scan |

檢查命令：

```powershell
Get-ScheduledTask -TaskName 'tw-invest-suite-daily-report','tw-invest-suite-publish','tw-invest-suite-health-check','tw-invest-suite-nightly-health','tw-invest-suite-postflight' |
  Get-ScheduledTaskInfo | Format-List TaskName,LastRunTime,LastTaskResult,NextRunTime
```

## 3. 主要手動操作

### 3.1 檢查目前狀態

```powershell
Set-Location 'C:\Users\icemo\Projects\tw-invest-suite\scripts'
C:\Python314\python.exe pipeline_state.py verify
C:\Python314\python.exe postflight_daily.py --after-publish
C:\Python314\python.exe check_openalice_health.py --json
```

查看 receipts：

```powershell
Get-Content .\_debug\pipeline_run.json
Get-Content .\_debug\last_completed.json
Get-Content .\_debug\publication_result.json
Get-Content .\_debug\postflight_latest.json
Get-Content .\analyze\render_receipt.json
```

### 3.2 只做本機 render

```powershell
powershell.exe -NoProfile -File .\run_daily.ps1 -Mode render
```

這不應被當成新資料認證，也不會取代完整 full run。

### 3.3 啟動完整 nightly

```powershell
Start-ScheduledTask -TaskName 'tw-invest-suite-daily-report'
```

執行期間保留 owner、stage log 與 artifacts；不要重複啟動。

### 3.4 發布

```powershell
Start-ScheduledTask -TaskName 'tw-invest-suite-publish'
```

publisher 的正常順序：

1. 等待 daily-report 結束。
2. `pipeline_state.py verify`。
3. `publish_ghpages.py --publish`，驗證遠端 SHA/manifest。
4. `sync_groove_release.py`，只複製認證 stock-report paths。
5. `src/chip_push.py`，查 ledger 後送現有 Telegram bot。

## 4. 完成契約

`pipeline_state.py complete` 必須同時通過：

- required stages 成功；optional failure 只能標 degraded。
- frozen `data_date` 與 expected trading session 一致。
- 24 active picks、四個 bucket、long/short 每組各三檔。
- 至少 1,900 current OHLCV tickers。
- render universe receipt 完整；selected picks 不得使用 stale quote。
- patterns、watchlist、all_reports 與本次 UUID/date 一致。
- runtime/repo source hashes 執行期間不變。
- 每個發布 artifact 有 SHA-256。
- all-report receipt 對上 30 個 history dates 與 50 個 advanced artifacts。

## 5. 故障排除矩陣

| 症狀 | 先查 | 行動 |
|---|---|---|
| `verify` 失敗 | `pipeline_run.json`, `last_completed.json` | 不發布；找出日期、UUID、required stage 差異 |
| stage timeout | heartbeat、owner creation identity、子程序樹 | 先確認仍在成長；確認卡住後才讓 nightly-health recovery 處理 |
| marker 缺失 | `pipeline_run.json`, stage logs | 重新完成正式 stage；不要從 picks 生成 marker |
| GitHub 已推但 remote hash 不符 | `publication_result.json`, remote manifest | 停止重送，檢查 staging、autocrlf、source hash |
| Groove SHA 不同 | `groove_stock_headers_audit*.json` | 確認 stock route 的 no-transform；不要修改 index/config |
| Telegram 已不確定 | `chip_delivery_ledger.json` 與 API receipt | 若已有 message id，維持 idempotent；不盲重送 |
| DB 日期落後 | `db_client.py`, `market_calendar.py`, `daily_data2_full` | 等資料落地或修正日期契約，不能硬標當日成功 |
| 健康檢查顯示 advisory | `check_openalice_health.py --json` | 區分 required task failure 與已知 auxiliary advisory |

## 6. 回滾

- 分析資料回滾：以 certified `last_completed.json`、prepared release 與對應 manifest 為依據，禁止直接覆蓋 DB。
- GitHub 回滾：使用已驗證的 fast-forward commit，保留 status/postflight receipt。
- Groove 回滾：只同步上一份已認證 stock-report paths；保留 music root index/config。
- Telegram：不刪除已送訊息；以 ledger 和後續更正訊息處理。
- Scheduler 回滾：先匯出 XML，再還原 task action/settings；不要刪除任務來「修復」pipeline。

## 7. 保留與清理

目前策略是 stage logs 本機保留 30 天，之後 archive 90 天，再由人工批准刪除。偵測與 recovery 期間不可清理 active owner 的 logs，也沒有自動清理 cron。

## 8. 憑證與秘密

- MySQL：`scripts/db_client.py` 只接受 `TW_DB_PASSWORD`；沒有密碼時會 fail closed。`TW_DB_HOST`、`TW_DB_USER`、`TW_DB_NAME` 可由環境變數覆寫預設值。
- FinMind：`FINMIND_TOKEN` 或 `~/.finmind_token`。
- Telegram：由既有 AI-Telegram shared/local/environment config 讀取；支援 `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`。
- FinLab／LLM／OpenAI：只用 environment 或既有 backend config。
- DB 密碼應由 Windows 使用者環境變數、Credential Manager 或部署平台 secret 注入；不可把本機密碼寫進 public repository。

## 9. 日常值班 checklist

```text
[ ] 檢查 latest trading data date
[ ] 檢查 pipeline_run / last_completed UUID
[ ] 檢查 required stages 與 degraded stage
[ ] 檢查 render/all-report receipts
[ ] 檢查 GitHub remote SHA/manifest
[ ] 檢查 Groove remote paths
[ ] 檢查 Telegram message id / idempotency ledger
[ ] 檢查 Scheduler LastTaskResult、WakeToRun、StartWhenAvailable
[ ] 保存當日證據，不把 warning 改寫成 success
```
