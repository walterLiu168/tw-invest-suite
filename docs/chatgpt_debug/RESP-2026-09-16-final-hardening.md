# MiniMax 最後一輪 hardening — 實作與驗收

日期：2026-09-16，Asia/Taipei。範圍：程式修補、runtime 一致性與可重現故障測試；不做 schema migration、不手動發布或推送。

來源：`C:\Users\icemo\.codex\attachments\f2838594-778b-418d-96e9-49a232e17198\pasted-text-1.txt`。

## 未來 24 小時優先順序

| 優先 | 處置 | 本輪結果 |
|---|---|---|
| P0 | Q1：認證成功不可被尾段 trap 撤銷 | 已修補並故障注入驗證 |
| P0 | Q2：終止卡住的補充抓取，保留 exact 24 picks | 已修補、隔離實機驗收通過 |
| P1 | Q3：依 stage deadline 與 owner identity 恢復 | 程式已同步；較密集 triggers 待授權 |
| P1 | Q5：可靠 certification sidecar、程序清理及 dashboard 查詢 | 已修補並實機測試 |
| P2 | Q4：按 run 身分讀日志並訂 retention | 已完成政策；不自動刪證據 |

本輪實作的完整 diff 可在 local commit 中以 `git show -- scripts tests docs` 檢視；下列節錄說明關鍵行為，不需再次貼入程式。

## Q1：完成後 trap 改壞 state

**Modified；信心 HIGH。** 採 Option A 的精簡尾段及 Option B 的狀態防護：完成驗證為最後一個必要操作；刪除後續全目錄統計，最終日志／狀態寫入只做 best effort。`pipeline_state.fail_run` 對同一個已認證成功的 run 保持狀態，拒絕不同 run_id 的失敗寫入。舊 marker 不能保護新的 running／failed attempt。

檔案：`scripts/run_daily.ps1`、`scripts/pipeline_state.py`。

`state_lock` 使用 Windows named mutex，讓 begin、complete、fail 及 watchdog recovery 串行，避免 watchdog 檢查舊 state 後覆蓋新 attempt。沒有以 marker 修補 failed state 的自動旁路。

驗證：真實 PowerShell 在 certification 後故意令 Log-Msg 拋錯仍 exit 0；同一成功 state 的 bytes 不變；不同 attempt 失敗仍被記錄，且舊成功 marker 無法阻擋它。

關鍵防護（`pipeline_state.fail_run`）：

```python
if value.get("status") == "ok":
    marker = read_json(MARKER)
    if (marker.get("nightly_id") == nightly_id and marker.get("status") == "ok"
            and marker.get("marker_version") == "D056-2"):
        return value
    raise ValueError("inconsistent completed state; refusing overwrite")
```

## Q2：Stage 6 抓取卡住

**Modified；信心 HIGH（期限與 picks 保留）；補充資料完整率需看實際來源。** 拒絕只加 `as_completed(timeout=...)` 或 `fut.result(timeout=...)`：無法終止執行中的 thread，executor 退出仍可能等待它。也拒絕略過正式 pick，因為完成契約要求 exact 24。

檔案：`scripts/bounded_deep_dive.py`、`scripts/render_full_watchlist.py`。

補充資料改由獨立、可終止程序抓取；每 ticker 最多 45 秒、總抓取預算 360 秒。FinMind 呼叫保持串行，符合 AGENTS 的限速規則。timeout 使用 taskkill 清掉 worker tree；其後其他 ticker 可繼續。總預算用盡時仍產生全部正式 DB picks 的卡片，缺少補充資料以警示列出，receipt／dashboard 保留 warning。

正常結果保持既有資料結構；原始錯誤／URLs 不加入公開警告，失敗只列來源名稱。正式 OHLCV 缺漏仍屬 required failure，不把它降級。

驗證：1 個故意 sleep 的 worker 被終止，其餘 23 個成功；全局預算用盡仍保留所有 ticker；真實 DB／快取的完整 watchlist 另在隔離目錄執行，結果見下方。

Watchlist 呼叫改為 `data_map = fetch_tickers(c.ticker for c in all_picks)`；worker wait 使用 `proc.wait(timeout=min(timeout_sec, remaining))`，timeout 路徑終止程序樹後回傳含 `stock_id`／`fetch_errors` 的 fallback。

## Q3：watchdog 門檻與恢復

**Modified；信心 HIGH（故障注入）；02:30 前的實際排程偵測延遲仍存在。** 不以總時間 90 分鐘或日志安靜 30 分鐘直接 kill。Stage 2 有合法 90 分鐘预算，總預設 budgets 已是 200 分鐘。

檔案：`scripts/run_stage.py`、`scripts/nightly_health.py`、`scripts/nightly_health_daily.ps1`、`scripts/register_nightly_health_cron.ps1`。

- Wrapper 每 15 秒寫 heartbeat，記錄 start、timeout、child／wrapper PID、完成狀態。
- 活躍 stage 依其 start + timeout + 45 秒判斷逾時；heartbeat 安靜但期限未到只回 UNKNOWN。
- 前一 stage 完成後超過 5 分鐘仍未進入下一 stage，或初始 preflight 5 分鐘無 stage 證據，判為 stuck。
- 總硬上限 240 分鐘；owner 必須符合 PID 與 process creation identity。
- 恢復前重讀 run，持 state mutex、重新判斷，再清理 owner tree；失敗清理不偽造 recovered。
- 缺檔／failed／unknown 不回健康 rc=0；completed 只代表本機完成，發布新鮮度仍由 publisher 驗證。

舊 ignored `_debug/nightly_health.py` 不再是 Scheduler 依賴；普通 scripts 檔案納入來源 SHA 檢查。

Registrar 已備好 22:30-02:00 每 30 分鐘檢查，加上既有 02:30／04:00／06:00；更新 existing task 只改 triggers，保留 principal／action／settings。**本輪未執行 registrar，現有排程時間未變。** 已驗證 trigger 建構為 PT30M／PT4H，無排程副作用。

驗證：合法 stage 在總時間 110 分鐘時不被誤殺；stage 逾時／between-stage gap 被抓到；故意使用錯誤 creation identity 的 PID 不被當作 owner；實際 owner 及 child tree 清理成功並記錄 failed；舊 watchdog 不可處理新 attempt。

## Q4：舊日志與 retention

**Accepted（保留審計軌跡）；信心 HIGH。** Watchdog 只讀當前 nightly_id 的 heartbeat／logs，舊 recovery artifacts 不影響新 run。不要在 kill／recovery 路徑加入 cleanup。

政策記錄於 `docs/pipeline-reference.md`：本機保留 30 天；較舊日志封存至 90 天；current marker／receipt 引用的證據及仍活躍 owner 的檔案永不清理。刪除需 operator 核准。本次不新增 cleanup cron，不刪現有診斷資料。

## Q5：額外發現與修正

**HIGH：dashboard Scheduler 查詢語法錯誤。** `build_dashboard.fetch_cron_lastruns` 缺 ForEach-Object 的結束大括號。實際 PowerShell 回傳 MissingEndCurlyBrace，導致 dashboard CRITICAL 並使 postflight exit 1。已修正，實機查詢可列出全部 9 tasks／結果。

**HIGH：certification 原生 stderr 與 ExitCode。** 直接用 PowerShell pipeline redirect 可能先觸發 native ErrorRecord／trap，且本機 Start-Process 即使 WaitForExit／Refresh，ExitCode 仍實測為 null。改為既有 run_stage 封裝，雙層 file redirect、exit sidecar、180 秒 child deadline／210 秒 wrapper deadline；實際 0 與 7 都能讀到正確 rc 及錯誤內容。

**HIGH：PowerShell timeout 清理。** 移除 PS 5.1 不支援的 Process.Kill(bool) 及無期限 WaitForExit；改 taskkill /T 與有期限 wait。wrapper stdout／stderr 也分別寫檔，避免繼承 console／pipe 阻住最後的診斷輸出。

**MEDIUM：09:55 Stage 2→3 停滯的確切歷史根因。** 原 process 已由 Mavis 終止，無法證明當時停在哪個 OS call。上述措施消除可見的 inherited-stream 及 unbounded-wait 風險；測試涵蓋連續 stage 的大輸出，不能代替當時的 dump。

**HIGH：预算與 latest-run 查詢。** `run_daily.ps1` 驗證 TimeoutMin=1–120，stage 总预算不得超過 235 分鐘，預留四小時 Scheduler cap 的 overhead；postflight 同資料日多個 screen run 時明確取最新 id。

**HIGH：歷史測試自身 import 失敗。** `test_publish_manifest.py` 原本以 substring 清 sys.modules，刪到自己的 test module，unittest discovery 報 KeyError。改為只清 exact publish_manifest；21 項歷史測試通過。

**HIGH：直接 CLI 的 cp950 診斷輸出。** 首次隔離驗收已產生 HTML／receipt，但最後 emoji 日志在 cp950 下丟出 UnicodeEncodeError。watchlist 與 supplemental worker 的 stdout 現使用 backslashreplace，無法表示的診斷字元不會把已完成輸出改成 stage failure；正式排程仍用 UTF-8。

## 本輪驗證

- `test_final_hardening.py`：14 tests 通過。
- `test_daily_pipeline.py`：25 tests 通過。
- `test_market_screen_runner.py`：31 tests 通過。
- `test_publish_manifest.py`：21 tests 通過。
- 完整 `C:\Python314\python.exe -B -m unittest discover -s tests -p 'test_*.py' -q` 共 91 tests 通過；PowerShell 5.1 syntax parse 與 changed-source diff whitespace 檢查通過。
- 首次 Stage 6 隔離目錄 `C:\Users\icemo\Projects\tw-watchlist-acceptance-9zbf3_q1` 用於重現 cp950 退出錯誤；此輪不是完整成功。
- 修正後 Stage 6 隔離實際驗收目錄：`C:\Users\icemo\Projects\tw-watchlist-acceptance-b72b58na`。
- 實際 DB 身分：data_date=2026-09-16、run_id=17、24 picks。第二次隔離驗收 exit 0，輸出 `REAL_WATCHLIST_ACCEPTANCE_OK`，耗時 242.2 秒、12 個 ticker 有補充資料警示；全部 24 picks 保留。驗收檢查 HTML exact multiset、JSON picks 與 snapshot 相同、HTML／Groove 複本 SHA 與 receipt 相同。此驗收不寫 production marker／產物，也不發布。
- 已同步 runtime 的九個修補檔案，26 個受管來源 SHA 通過（24 個 runtime mirrors、2 個 repo-only margin 檔案）。備份：`C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug\d056_backup_20260916_final`。
- 實際 Scheduler query 返回 9 tasks；目前 watchdog --json 正常讀取完成的舊 run，沒有 kill／state 修改。這不等於今晚已執行或 postflight 已重新通過。

## 交接／後續驗收

1. 合併／push 前核對 local commit 與 runtime 來源 SHA；manual Git push／publication 仍需 Walter 的授權。
2. 如要啟用半小時 watchdog window，先核准 registrar 的 trigger expansion；現有 nightly-health 仍按三個原時間執行。
3. 今晚 22:25 正式 nightly 應有同一 UUID 的必要 stages、新的 D056-2 marker、data_date／run_id／24 picks、來源與產物 SHA。
4. 00:30 publisher 仍须等待實際 daily-report 完成，再驗證遠端 manifest／watchlist／patterns／所有 selected ticker SHA；不能以 HTTP 200 判定發布成功。
5. postflight 若未通過，讀 checks 與 dashboard 明細；已知資料缺漏／7768 quarantine／補充 fetch warning 保留，不強制改綠燈。修補前 15:48 receipt 的 overall_pass=false 由 Scheduler query 語法錯誤觸發，不是所有核心 DB checks 失敗。

## 已檢查且無需再改

- 完成閘門仍要求 exact 24 multiset；margin 的 60 額外卡片不會誤計。
- 發布預設 prepare-only，手動修復沒有自動 push 旁路。
- Git staging 保留 certified bytes；remote verification 覆蓋全部 selected ticker 頁面。
- runtime／repo 複本界線明確；舊 watchdog 無法補造成功 marker。
- 無 DB schema migration、無 quarantine 刪除、無新增投資策略或 UI 功能。
