# RESP-2026-11-22-01：週末 nightly 認證失敗的根因與修正，以及每日排程的健康處置

**日期**：2026-11-22
**目標**：「check data integrity and make sure all daily task run smoothly」
**對應決策**：D026

---

## §0 摘要

2026-11-21（週六）21:30 的 nightly 失敗在 Stage 7（`src/all_reports.py:99` → `KeyError: 'picks'`）。
2026-11-22（週日）21:30 的 nightly 會以**完全相同的方式**失敗——週末路徑從未被認證過
（`public/data/publish_manifest_*.json` 只有平日，最新 2026-11-20）。

**根因不是「週末沒有資料」，是「週末沒有任何東西把已提交的 picks 綁回 run state」。**
`run['picks']`／`run['run_id']` 從來不是 render 寫的，是 `finalize_inputs` 綁的；
而 `finalize_inputs` 只存在於交易日分支。週末跳過下載階段 → 那兩個鍵從頭到尾不存在 →
Stage 7 讀 `run['picks']` 就炸。

同一個根因還解釋了稽核症狀：11/21 的 render **已經改寫了 1,974 個 analyze 檔**才在 Stage 7 崩，
所以 manifest 對不上 → chain audit 報 1,978 個 hash 不符。**一個根因、兩個症狀。**

本次處置：

| 項目 | 處置 |
|---|---|
| 週末 nightly 認證失敗 | 新增 `bind-screen-inputs`：把 DB 已提交的 24 picks 綁進 run state（§3.1） |
| 修好後會不會每小時重跑 nightly | 維護收據繼承機制：canonical 摘要位元組相同才准繼承（§3.2） |
| `tw-invest-suite-yfinance` rc=2 | 非交易日不再誤報，也不再覆寫 nightly 的 finance 收據（§4.1） |
| `AI-Telegram Scheduled Pipeline` 0x800710E0 | 卡在殘留 Running 實例 → 清掉並重啟 owner；加 watchdog（§4.2） |
| `OpenAlice RSS Refresh Every 2h` rc=1（429） | 查詢間隔 + 429 退避重試 + 單一查詢失敗不拖垮整批（§4.3） |
| 實體睡眠喚醒未證明 | 查出上次的真因（用錯 API）；本機權杖為 UAC 過濾權杖 → 需提權（§4.4） |
| manifest 1,978 個 hash 不符 | 週末重新認證後重新產生 manifest（§5） |

---

## §1 症狀：2026-11-22 15:30 的排程全景

```
tw-invest-suite-daily-report        Ready   last=11/21 21:30 rc=1（一般失敗）
tw-invest-suite-publish             Ready   last=11/21 22:50 rc=1
tw-invest-suite-yfinance            Ready   last=11/21 22:30 rc=0x00000002
tw-invest-suite-daily-chain-audit   Ready   last=11/22 06:30 rc=0x0000000A
AI-Telegram Scheduled Pipeline      Running last=11/21 17:45 rc=被拒絕(0x800710E0)
OpenAlice RSS Refresh Every 2h      Ready   last=11/22 15:00 rc=1（一般失敗）
tw-invest-suite-sleep-wake-proof-arm Ready  last=11/21 23:35 rc=0x00000002
```

chain audit（11/22 06:30）→ `DEGRADED`，findings：

- `postflight 缺失/失敗/批次不一致`
- `all_reports identity 不一致`
- `all_reports 收據未通過或不足 50 份`
- `manifest missing/hash_mismatch=1978`
- 喚醒項（見 §4.4）

11/21 失敗那次的 stage 清單（`_debug/stages_4c058afcd5694fd3b12165aa8f12cba3.json`）
**只有 Stage 7 `all_reports` 失敗**，Stage 2–6 全綠；對照 11/20 成功的清單，
交易日多出的是 valuation／finmind_maint／stock_features／market_screen／finalize_inputs 五個 stage。

---

## §2 根因：缺的是綁定，不是資料

### 2.1 `run['picks']` 從來不是 render 寫的

`pipeline_state.py`：

- `begin()` → `db_snapshot(require_screen=False)` → 只回傳
  `data_date`／`ohlcv_rows`／`ohlcv_tickers`／`render_tickers`，**沒有 `picks`、沒有 `run_id`**。
- `finalize_inputs()` → `db_snapshot()`（require_screen=True）→ 才會帶回
  `run_id`／`picks_count`／`bucket_counts`／`picks`（24 檔，全部 active）。
- `complete()` → `snapshot[k] != run[k]`（k 含 `run_id`、`picks`）→ 缺就直接 KeyError。

`run_daily.ps1` 的 stage 清單：

```powershell
if ($Mode -eq 'full' -and $run.trading_session -and -not $SkipFinmind) {
    ... market_screen ...
    $stages += @{ N=1; Name='finalize_inputs'; Cmd='pipeline_state.py finalize-inputs'; To=120 }
}
```

`finalize_inputs` 在**交易日分支裡**。週末（`$run.trading_session = False`）這個分支整個不存在
→ 沒有任何東西把 picks 綁進 run state → Stage 7 讀 `run['picks']` → `KeyError`。

**旁證**：資料庫裡 `market_screen_runs` 的 `run_date` **全部是平日**（最近 12 筆：11/20、11/19、11/18…），
週末從來沒有新的 screen run；但週五那次（run_id 119）的 24 檔 picks 一直在 DB 裡、全部 active。
**picks 一直都在，只是沒綁。**

### 2.2 一個根因，兩個症狀

11/21 的 nightly 在 Stage 2 render 已經把 1,974 個 analyze 檔改寫成新的 nightly_id 戳章，
才在 Stage 7 崩掉。認證從未完成 → manifest 停在 11/20 那份 → 檔案雜湊對不上 →
chain audit 報 `manifest missing/hash_mismatch=1978`。

### 2.3 修好之後會不會反而更糟

這是本次唯一需要設計的地方。若只補「綁 picks」，週末認證會成功，但：

- 新 marker 的 `nightly_id` 是新的 → `maintenance_fetch.json` 的 `nightly_id` 還是上一次的 →
  `certification_catchup_guard.ps1` 的 `$maintenanceVerified` 為 false → `$markerReady` 為 false →
  guard 轉呼叫 catchup → catchup 的 `certified_for()` 要求
  `maintenance.nightly_id == marker.nightly_id` → 不成立 → **每小時重跑一次整條 nightly**。

所以「能認證」不等於「修好了」。

---

## §3 修正

### 3.1 `bind-screen-inputs`：第二條綁定路徑

新增 `pipeline_state.py bind-screen-inputs`（`@state_guarded`），做 `finalize_inputs` 綁定的
同一件事，但**不要求**下載階段的收據：

```python
previous = read_json(MARKER)
if previous.get('status') != 'ok' or previous.get('data_date') != run['data_date']:
    raise ValueError('No certified release for this data_date to inherit')
canonical = canonical_inputs_hash(run['data_date'])
if previous.get('canonical_inputs_sha256') != canonical:
    raise ValueError('Canonical inputs changed since the last certification')
snapshot = db_snapshot()
run.update(snapshot)
run['canonical_inputs_sha256'] = canonical
run['inherited_maintenance_nightly_id'] = previous.get('nightly_id')
```

`run_daily.ps1` 在 `finalize_inputs` **不存在時**補上這個 stage（涵蓋週末、`-SkipFinmind` 的 catch-up）：

```powershell
if (-not ($stages | Where-Object { $_.Name -eq 'finalize_inputs' })) {
    $stages += @{ N=1; Name='bind_inputs'; Cmd='pipeline_state.py bind-screen-inputs'; To=420 }
}
```

`src/all_reports.py` 的揀配檢查改成講清楚缺什麼，不再丟 KeyError：

```python
run_picks = run.get('picks')
if not run_picks:
    raise ValueError('Run state has no bound screen picks')
```

`complete()` 的缺鍵也改成名單：`Run state is missing bound inputs: ['run_id', 'picks']`。

### 3.2 維護收據的繼承：證明，不是信任

維護收據（`maintenance_fetch.json`）證明的是**那份 canonical 資料**有從供應商正確刷新過
（`canonical_refresh_rows` 1962、`source_value_mismatches` 0、price/chips 各 30 個 session）。
它綁的是資料，不是某個 nightly 實例；`nightly_id` 相等只是**交易日的巧合**。

週末沒有 canonical refresh，所以新認證要繼承上一輪的收據。准不准繼承，用**證明**回答：

- 重新算 `canonical_inputs_hash(data_date)`（240 個 session × 每日宇宙，SHA-256），
  必須與**上一次認證**存進 marker 的 `canonical_inputs_sha256` **位元組相同**。
- 相同 → 這批產物與被認證過的那批產物出自**同一份 canonical 資料** → 收據仍然有效 →
  記 `inherited_maintenance_nightly_id = 上一輪的 nightly_id`。
- 不同 → **拒絕綁定**，並明確報錯（那代表 canonical 資料變了，週末重渲染不該被認證）。

這比「nightly_id 相等」更嚴格：canonical 摘要相同才准繼承，nightly_id 相同只是它的必要條件之一。

對應放寬兩處（**只**放寬 maintenance 這一條）：

- `daily_certification_catchup.py::certified_for()`：
  `maintenance.get("nightly_id") in (nightly_id, marker.get("inherited_maintenance_nightly_id"))`
- `certification_catchup_guard.ps1` 的 `$maintenanceVerified`：同樣的兩選一。

**沒有**放寬的部分：publication 的 `nightly_id` 仍須與 marker 相等（那是「這批產物有沒有被發佈出去」，
不能用繼承代替）；marker 的 `data_date`、`marker_version`、`status` 全部照舊。

### 3.3 同步與雜湊

`source_hashes()` 對 `scripts/` 的 47 個檔案要求 repo 與 runtime（`~/.claude/skills/tw-invest-suite/scripts`）
SHA-256 一致，不一致會直接擋下認證。本次改了 5 個 hashed 檔案，全部同步後驗證：

```
pipeline_state.py c8c4ab0ecc44
run_daily.ps1 cddc38216d5c
daily_certification_catchup.py b1234a27b5d3
yfinance_daily.py 307dee401f5f
source_hashes OK: 72 files
```

（`certification_catchup_guard.ps1` 與 `src/all_reports.py` 不在 hashed 清單裡／或只取 repo 端。）

---

## §4 其他每日排程

### 4.1 `tw-invest-suite-yfinance` rc=2 —— 是誤報，不是故障

11/21 22:30 的日誌：

```
[2026-11-21 22:30:03,565] Non-trading session: preserved cache receipt 0/1974 for 2026-11-21
```

`yfinance_daily.py` 的非交易分支拿 `target_date = 2026-11-21`（星期六）去找行情 →
**那個日期本來就沒有 session** → 新鮮標的數 0 → `status='failed'` → `return 2`。
**0 不是供應商失敗，是「非交易日的正確答案」。**

而且更嚴重：該分支**無論有沒有 nightly_id 都寫 `finance_fetch.json`**
（交易分支才會寫成 `finance_refresh_latest.json`）——獨立的 22:30 排程會用
`nightly_id='manual'`、`status='failed'` 覆寫掉 nightly 自己的收據。
下一次交易日的 `complete()` 若讀到它就會被拖下水。

修正：

- 獨立排程（無 `TW_NIGHTLY_ID`）→ 寫 `finance_refresh_latest.json`，**不碰** `finance_fetch.json`，回傳 0。
- nightly 自己的執行 → 行為完全不變。

實測（非交易日、獨立執行）：`EXITCODE=0`，且 `finance_fetch.json` 前後雜湊相同。

### 4.2 `AI-Telegram Scheduled Pipeline` 0x800710E0 —— owner 死了，排程還以為它在跑

**量到的事實**：

- 全機沒有任何行程的命令列帶 `AI-Telegram` → **owner 行程不存在**。
- 排程狀態卻是 `Running`，`MultipleInstances = IgnoreNew` → 之後每次觸發都被拒
  （0x800710E0 = 已有實例在跑）。
- AI-Telegram 最後的產出停在 **2026-11-21 23:07**（`automation/_logs/run_finmind_daily_status.json`），
  之後 `output/` 下再無任何檔案更新（11/22 整天零產出）。

**處置**：

1. `Stop-ScheduledTask` 清掉殘留實例 → 狀態回到 `Ready` → 17:45 的觸發終於能真正啟動 owner
   （已驗證：owner 行程 PID 20556 起來，`task=Running`）。
2. owner 的 `cmd.exe` 命令列是**空的**（排程啟動時不帶參數），所以只能用行程命令列判活 →
   在 `run_pipeline_scheduled_forever.cmd` 的迴圈開頭加一行心跳：
   `echo %DATE% %TIME%> "%~dp0.codex-work-state\owner_heartbeat.txt"`。
   （心跳寫在**每輪之前**，所以正在跑一個長 stage 時也不會被誤判成死亡。）
3. 新增 `scripts/ai_telegram_owner_watchdog.ps1` + 排程 `tw-invest-suite-ai-telegram-owner-watchdog`
   （每 15 分鐘，Interactive／Limited）：**Running 但沒有 owner → 清殘留 → 重啟**；
   30 分鐘冷卻避免重啟風暴；`scripts/_debug/ai_telegram_owner_pause.marker` 可暫停。

### 4.3 `OpenAlice RSS Refresh Every 2h` rc=1（HTTP 429）

- 原料庫 `stock_news` 有 2,434,706 篇、涵蓋到 2026-11-20 → **原料本身是新鮮的**，
  但每次排程都失敗 → `rss_ingestion_latest.json` 的 `status: failed`、`http_status: 429`。
- 根因：目錄有 **81 個關鍵字**，`rss_to_db.py` 原本**無間隔連打**
  → 觸發 Google News 的速率限制 → `httpx` 的 429 讓**整批**中止，**DB 一列都沒寫進去**。
- 量測：單獨抓 3 個 feed 現在都回 200 → 是**批次突發**造成的限流，不是封鎖。

修正（`news-digest/app/rss.py` + `news-digest/app/rss_to_db.py`，AI-Telegram repo，本地）：

- 查詢之間間隔 1.2 秒。
- 429／5xx 退避重試（3 次，15s → 45s → 135s）。
- **單一查詢失敗不再拖垮整批**：記進 `query_errors` 繼續跑；全部失敗才算失敗，
  部分失敗 → `status: degraded`、rc=2，並在收據裡列出失敗的關鍵字。

實測（81 個查詢，dry-run）：**fetched 1086、`query_errors: []`（零 429）**。

### 4.4 實體睡眠喚醒：上次的真因找到了，但這台機器做不到

上次的 arm 任務（11/21 23:35）寫了收據卻**沒有真的睡**。真因有兩個：

1. **用錯 API**。原腳本廣播 `WM_SYSCOMMAND` / `SC_MONITORPOWER`（0xF170）——
   那是「**關螢幕**」指令，不是休眠。已改成真正的
   `SetSuspendState(FALSE, TRUE, FALSE)`（S3）。
2. **權杖被 UAC 過濾**。`whoami /priv` 顯示 `SeShutdownPrivilege` 存在但 Disabled，
   但 `AdjustTokenPrivileges` 回 **win32=5（ACCESS DENIED）**——
   非提升權杖是 UAC 過濾權杖（`BUILTIN\Administrators` = *deny only*），
   這個權限啟用不了。`Set-ScheduledTask -RunLevel Highest` 也回 **Access is denied**。

⇒ **受控休眠需要提權的排程**，這台 session 做不到。
喚醒能力本身是備妥的：`powercfg /devicequery wake_armed` 列出兩張 **Intel I210 網卡**
（wake-on-LAN 已啟用）、`powercfg /a` 有 S3 與休眠；缺的是「誰來按下休眠」。

腳本已改成會**大聲失敗**而不是靜默假成功：`-Mode verify` 直接回報權杖能不能用，
arm 任務在沒有核准的測試時回 0（正常狀態，不是紅字），有核准但提權不足時寫
`status: suspend_unavailable` 並回 4。

**待 Walter 決定**：在有提權權限的 session 裡把 arm 任務改成「使用最高權限執行」，
就能做真正的受控睡眠 → 喚醒 → 證明。若不升權，本機的實體睡眠喚醒**維持未證明**，
這是誠實的現況，不是缺陷。

---

## §5 端到端驗證

### 5.1 週末路徑第一次被認證（2026-11-22 17:21:06）

`nightly_id = adbf6c6c1a2844f3a829e9cd1ff28c05`、`data_date = 2026-11-20`、
`execution_date = 2026-11-21`、`marker_version = D056-3`、`status = ok`。

| stage | 結果 | 備註 |
|---|---|---|
| 1 bind_inputs | OK（61 秒） | 重算 canonical 摘要 52.5 秒 + DB 快照 |
| 2 render | OK（1,420 秒） | 1,974 個 HTML、**0 失敗** |
| 3 patterns / 4 patterns_html | OK | |
| 5 margin_scan | OK | optional stage，未進 degraded |
| 6 watchlist | OK | |
| 7 **all_reports** | **OK** | ← 11/21 在這裡 `KeyError: 'picks'` |

marker 內容：`run_id 119`、`picks 24`、`artifacts 2,037`、`render_count 1,974`、
`fresh_render_count 1,949`、`degraded_stages 0`。

**維護收據繼承成立**：`inherited_maintenance_nightly_id = 37e9e86f…`（週五那一輪），
`canonical_inputs_sha256 = ca64fa12…`（與週五認證存下的值**完全相同**）。

### 5.2 發佈

`publish_verified_sites.ps1` → exit 0：

- `PUBLISHED_AND_VERIFIED data_date=2026-11-20 postflight_exit=0`、`copied_paths 2040`
- `publication_result.json`／`groove_publication_result.json`：`status=verified`、nightly 為本輪
- `postflight_latest.json`：`overall_pass=true`
- `publish_manifest_2026-11-20.json`：重寫為本輪 nightly、2,037 個產物
  （**11/21 那次留下的 1,978 個 hash 不符在此歸零**）
- Telegram：`Telegram sent data_date=2026-11-20 message_id=4288 already_sent=True`
  → **沒有重複推送**（同一個 session 的同一則籌碼摘要）。

### 5.3 chain audit 復綠

稽核的三個檢查點原本都用「nightly_id 必須完全相同」判定，對「週末重渲染」這種
「同一份 canonical 資料、另一輪認證」的情況不成立，已改成同一條語意
（`maintenance_claim_holds()` 三路判定：同一輪／繼承／現存摘要）：

- `canonical_history`：原本 `identity 不一致` + `同批次逐欄 log 證據缺失`
  → 現在 **verified**（30/30 sessions、price 58,836 列、chips 294,180 列）。
  log 交叉檢查改為對應**收據自己的那一輪**（收據證明的是哪一輪的刷新，就核哪一輪的 log）。
- `chips ledger`：原本 `缺失或與 receipt 不一致` → 收據標 `already_sent` 時，
  ledger 記的是**實際寄送**的那一輪、receipt 記的是**觀察到既有投遞**的那一輪，
  其餘投遞識別欄位（data_date／chat_hash／message_id／message_sha256）仍必須逐欄相同。
- `manifest` 1,978 個 hash 不符 → **歸零**；postflight／all_reports 兩項 finding → 歸零。

**稽核結果：只剩一項 finding**——「本機自上次開機後未曾從睡眠喚醒」。
那不是缺陷，是本機的誠實現況（§4.4）。

### 5.4 catchup 不再每小時重跑 nightly

`certification_catchup_guard.ps1` 與 `daily_certification_catchup.py` 改用同一條
`maintenance_claim_holds()` 規則：維護收據不再被要求「必須是同一個 nightly_id」，
但 publication 的 nightly_id 仍必須與 marker 相等、marker 的 data_date／marker_version／
status 全部照舊。週末認證因此**不會**讓 hourly catchup 判定「未認證」而每小時重跑整條 nightly。

### 5.5 其他排程的實測

| 排程 | 實測 |
|---|---|
| `OpenAlice RSS Refresh Every 2h` | 17:00 那次排程 → `status: verified`、`exit_code: 0`、81 個查詢、零 429 |
| `tw-invest-suite-yfinance`（非交易日獨立執行） | exit 0，且 `finance_fetch.json` 前後雜湊相同（不再被覆寫） |
| `AI-Telegram Scheduled Pipeline` | owner 行程活著（心跳每輪更新）、singleton lock 回報「another scheduler is already running」→ 管線確實在跑 |
| `tw-invest-suite-ai-telegram-owner-watchdog` | 已註冊（每 15 分鐘）；「owner alive, task=Running - nothing to do」 |

---

## §6 未解與需要授權的事項

1. **受控睡眠喚醒**：需要提權的排程（§4.4）。
2. **`AI-Telegram` 的兩筆 commit 是否 push**：維持 local-only。
3. **新模型是否推廣**：建議不推（六項門檻只過 AUC）。
4. **新聞家族**：把訓練窗也用原料庫重建（924 天／約 7.7 小時），或整族排除——需要授權。
5. **約 102 張已停寫的資料表**是否清理：未問。
6. **舊表 `daily_data2` 的 166 檔／9,276 列凍結**：模型不讀，屬未引爆的地雷。
7. **法人欄位約 16% NULL**：需確認是「來源沒給」還是「管線漏抓」。
8. **預測表 53 個空白交易日**：依交接邊界不重建。
9. **認證鏈其餘 8 個未追蹤檔**：這次為了修 catchup／guard 必須動
   `certification_catchup_guard.ps1`，因此它一併納入版控；其餘 8 個仍待 Walter 決定。
10. **catchup 的盲點**：`certified_for()` 只驗 marker／publication／maintenance，
    **不驗磁碟上的產物雜湊**。11/21 那次「render 已改寫 1,974 個檔、認證卻沒完成」的情況，
    catchup 完全沒有察覺（它到 11/22 15:00 都還回 ALREADY_CERTIFIED）。
    這是 manifest 漂移能持續兩天的原因，值得另案處理。
