# 2026-11-17 篩選驗證、衍生欄位退化與修補、精選歷史分頁

**日期**：2026-11-17
**範圍**：`tw-invest-suite`（repo 與 runtime）、`AI-Telegram`（local-only 未 push）

---

## 1. 18:20 篩選驗證：long／short 互斥契約 **PASS**

排程 `tw-invest-suite-market-screen` 於 2026-11-17 18:20:20 執行，結果：

| 檢查項 | 結果 |
|---|---|
| `market_screen_runs` | run_id=110，run_date=2026-11-17，universe=1927，picks_count=24 |
| `market_screen_picks` | 24 列，**distinct ticker = 24**（無重複） |
| 每個 `(bucket, horizon)` | 皆 3 檔（4 bucket × 3 long + 3 short） |
| `market_screen_20261117_182001.log` | 無 FAILED／ERROR／duplicate |
| 前一筆 11/16（修正前） | run_id=108，24 槽只有 **23** 檔（3443 重複）→ 確認互斥邏輯首次生效 |

這是 D019 修正後的**第一次正式運行**，契約成立。

---

## 2. 衍生欄位退化：當天新出現的問題（已修）

### 2.1 症狀

11/17 的 18:20 篩選產出的 24 檔，`change_pct` **全部為 0**，且 short 分數異常整齊
（12 檔只有 5 種分數，多組同分靠代號升序決定）。追查後確認：

- `daily_data2_full` 的 `change_pct` 在 11/17 為 **1,964 列全 NULL**（11/16 起往前 19 個交易日皆 0 NULL）
- `sma_13`／`sma_27`／`sma_54`／`atr_14`／`rsi_14`／`is_gap` 在 11/17 為**欄位 DEFAULT 0 佔位值**
  （11/16 為真值）
- `SharesOutstanding_shares` 同樣全 NULL
- 其餘欄位（Open/High/Low/Close/Volume/sma 以外的全域欄位、ForeignNet、MarginBalance…）正常

### 2.2 為什麼會讓選股退化

`market_screen.short_term_score()` 的八個組成裡有四個直接吃這些欄位：

| 組成 | 上限 | 11/17 狀態 |
|---|---|---|
| trend（`sma13 > sma27` 且 `close > sma13`） | 1.0 | **失效**（sma 全 0） |
| rsi（`50 ≤ rsi14 ≤ 65`） | 0.8 | **失效**（rsi 全 0） |
| gap（`is_gap == 1 and change_pct > 0`） | 0.3 | **失效**（change_pct NULL） |
| volume_burst / kd_cross / foreign_flow / news / liquidity | — | 正常 |

結果：short 分數上限從理論 3.5 塌到 1.4（實測最高 1.4），大量同分只能靠代號升序決定，
**等於在 bucket 內近乎任意挑選**。

long 側不受影響：long 分數只用 `market_cap`（走 `shares_map` fallback）與價格報酬，
兩者都正確。

### 2.3 影響範圍

- `market_screen_picks.change_pct` 24 列全 0 → 精選卡與 MD 報告的「漲跌」全顯示 `+0.00%`
- 12 檔 short 名單的組成錯誤。用正確衍生欄位重跑的對照實驗（唯讀）：

  | bucket | 18:35 實際產出（退化） | 正確值 | 差異 |
  |---|---|---|---|
  | `<100` | 2849, 2911, 2923 | 2923, 4155, 1323 | 2 檔不同 |
  | `100-300` | 2597, 3570, 4722 | 3570, 5209, 2221 | 2 檔不同 |
  | `300-1000` | 2404, 6944, 7717 | 7717, 6870, 7799 | 2 檔不同 |
  | `>1000` | 2059, 2308, 5269 | 6446, 3491, 3661 | **3 檔全不同** |

  **9 檔 short 選股會變**；12 檔 long 完全不變。

### 2.4 根因

FinMind canonical 階段在 **18:00–18:07** 執行（`TaiwanStockPrice` 18:00:47、
`TaiwanStockInstitutionalInvestorsBuySell` 18:01:42、`TaiwanStockKBar5Min` 18:07:54），
但 `TaiwanStockMarginPurchaseShortSale` 回報
`Canonical source is empty; existing DB rows cannot prove readiness`，
`TaiwanStockDayTrading`／`TaiwanStockShareholding`／`TaiwanStockIssuedShares` **完全沒有 11/17 的紀錄**。

`finmind_batch_update.main()` 的流程是：資料集階段 → `refresh_price_history` →
`if touched_dates and "price" in phase_names: recompute_derived(...)`。
`recompute_derived` 寫的就是那 7 個衍生欄位。**資料集階段中途丟例外 → 整段中止 → 補算從未執行**，
11/17 的列就留在欄位 DEFAULT 上。

19:00 的 price 階段（`tw-invest-suite-finmind-download`）也救不回來：
`db_complete=1964 pending=0 affected_rows=0 downloaded_tickers=0` → 狀態已標記完成 → 整段跳過，
`written == 0` → `touched_dates` 維持 False → 補算仍然不會跑。

下一次有機會補算是 **23:00 的 canonical 階段**（帶 `--refresh-existing`），
但那已經晚在 22:45 的 nightly 渲染與 22:50 的發佈之後。

### 2.5 對照組：為什麼 11/16 沒事

- 11/16 的 MD 由 **22:29:48** 的 nightly 重跑產生，漲跌是真值（+2.91%／−8.50%／+9.86%…）
- 11/17 的 MD 由 **18:35:18** 的 18:20 排程產生，漲跌全是 `+0.00%`

nightly（`run_daily.ps1`）的 market_screen stage 會用 `--refresh-existing` 再跑一次篩選並覆蓋同一筆
run（`market_screen_runs` 以 `run_date` UPSERT），所以 11/16 那天的最終成品是好的。
**今天會不會好，取決於 22:25 的重跑時衍生欄位是否已經補好**——這就是為什麼需要立刻補算。

---

## 3. 立刻補算 11/17（已執行，Walter 授權選項 A）

做法：直接重算 `daily_data2_full` 的 7 個衍生欄位，來源是**同一張表的既有 OHLCV**，
不呼叫 FinMind API、不改 schema、不動其他欄位。

先在 **11/16 的真值上做唯讀驗算**，確認公式與上游 `recompute_derived` 一致
（差異僅為 MySQL 欄位小數位進位）：

| 欄位 | 最大絕對差 | 欄位小數位 | 判定 |
|---|---|---|---|
| change_pct | 4.981e-05 | 4 | OK |
| sma_13 | 4.615e-03 | 2 | OK（進位） |
| sma_27 | 4.815e-03 | 2 | OK（進位） |
| sma_54 | 5.000e-03 | 2 | OK（半進位邊界） |
| atr_14 | 4.286e-05 | 4 | OK |
| rsi_14 | 5.000e-05 | 4 | OK |
| is_gap | 0 | int | OK |

寫入後複查：`change_pct` NULL 1,964 → **0**、`sma_13` 全 0 → **0**、`rsi_14` 全 0 → 1
（與 11/16 同樣只有 1 檔 RSI 合理為 0）、漲跌幅範圍 [−100, 10] 與 11/16 一致。

**額外交叉驗證**：另外用上游 `finmind_batch_update.recompute_derived()` 重算 5 檔抽樣，
結果與本回合補寫的值 **逐欄 0 差異**（1e-9 以內）→ 兩套公式等價，資料可信。

---

## 4. 結構性漏洞修補（AI-Telegram repo，local-only 未 push）

檔案：`D:\CODEX\AI-Telegram\strategy_lab\finmind_batch_update.py`

兩個漏洞：

1. **補算綁在資料集階段的成敗上**：任一資料集丟例外 → 整段中止 → `recompute_derived` 永不執行
2. **補算綁在 `touched_dates` 上**：price 階段因狀態已標記完成而 `affected_rows=0` 時，
   `touched_dates` 維持 False → 補算被跳過，即使衍生欄位仍是佔位值

修法（4 個 hunk）：

- 新增 `tickers_missing_derived(start_date, end_date)`：查出範圍內
  `change_pct IS NULL OR sma_13 = 0` 的標的（這兩個值不可能是合法值；
  `rsi_14 = 0` 會誤判連 14 根跌停的標的，已排除）
- 資料集階段包在 `try/except` 裡，記下錯誤但不中斷，讓補算照跑
- 補算條件由 `touched_dates and "price" in phase_names` 改為
  `"price" in phase_names`；`touched_tickers` 為空時改用 `tickers_missing_derived()` 兜底
- 補算與 inst-nets、cache 失效都跑完後**再 re-raise**，讓 exit code 仍然回報失敗（fail-closed）

驗證：

| 測試 | 結果 |
|---|---|
| 健康日期 `tickers_missing_derived('2026-11-17','2026-11-17')` | 0 檔（無誤判） |
| 人為清空 5 檔的衍生欄位後 | 5 檔全數被偵測到 |
| 上游 `recompute_derived` 補回 | 與原值逐欄 0 差異 |

**注意**：該檔另有**他人未提交的改動**（`official_twse_json`／`capital_suspensions`／
`resolve_price_universe`），所以本回合的改動**不可整檔 commit**，必須逐 hunk 取用。
本回合依 Walter 指示**保留 local、不 push**。

---

## 5. 首頁新增「📜 精選歷史」tab ＋「每日 24 檔」視圖

需求：首頁要能查 top 24 精選的歷史（Walter 口述「like we mentioned before」）。

### 5.1 發現的缺口

`public/watchlist-history.html` 早就存在（逐檔視角），但：

- **沒有被任何頁面連到**，首頁 nav 也沒有它
- 頁面本身沒有 `module-tabs` nav，離開後沒有路徑回來
- 只有「逐檔」視角，沒有「每日 24 檔」的時間軸

### 5.2 實作

**a) nav 分頁**（8 → 9 個 tab）

- 靜態頁：`readme.html`／`sectors.html`／`chips.html`／`concepts.html`／
  `chips-advanced.html`／`chips-history.html`／`monitor.html`
- **產生器**（這 4 個頁面每晚重新生成，只改輸出檔會被蓋掉）：
  `src/chip_rank.py`（chips.html）、`src/render_chips_advanced.py`、
  `src/render_concepts.py`、`src/sector_aggregate.py`（sectors.html）
- `watchlist-history.html` 自己補上完整 nav（本頁為 active）
- `watchlist.html` 是 nightly 生成檔、本來就沒有跨頁 nav，且每張精選卡已有「📜 選股歷史」連結 → 不動

**b) 首頁首發處**：CTA 列加一顆按鈕、功能卡片區新增「精選歷史」卡、
「全站 8 大功能」→「9 大功能」、「8 個跨頁 tab」→「9 個跨頁 tab」。

**c) 新視角「📅 每日 24 檔」**（在 `watchlist-history.html` 內）

由既有 `public/data/watchlist-history.json` 的 `tickers[*].entries[*]` **在前端推導**，
不改動已認證的 artifact（`REPORT_FRONTEND_FILES` 只驗檔名與執行時重算的 SHA）。

內容：

- 日期選擇器（50 次篩選）
- 統計卡：在榜檔數、延續前一日、新進、離榜、長期/短中期、當日平均、上漲/下跌
- 當日名單表：依 4 個 bucket 分組，欄位含分級、方向、分數、收盤、當日漲跌幅、
  超額 60／240 日、延續／新進標記；點任一列可開抽屜看該檔完整時間軸
- 「每日 24 檔總覽」表：每個日期的檔數／延續／新進／離榜／長短比／當日平均／漲跌家數，
  點擊切換該日明細
- 深層連結 `?view=day`、`?ticker=`

### 5.3 驗證

- 8 個頁面的 inline script 全數通過 `node --check`
- 瀏覽器實測（http://127.0.0.1:18766）：nav 9 個 tab 正確、逐檔視角正常、
  每日視角正常、`?view=day` 深層連結可用、console 無錯誤
- 抓到自己寫的兩個 bug 並修掉：
  1. 「當日平均」顯示 −327.98% → `chg` 本身已是百分比，`sign()` 又乘了 100
  2. 標題寫死「當日 24 檔名單」但當天可能只有 23 檔 → 改為動態字串
- 順帶修掉 `apply()` 內 `sort==="first"` 比較器的打字錯誤（原本拿 `b.last_seen` 比）

---

## 6. 未解與邊界

- **`chipscore_daily` 沒有最新交易日**：11/17 的篩選 log 顯示 `chipscore: 0`，
  11/16 也是 0（該表最新只到 11/16）。這是**天天如此**的結構性缺口，
  對 short 分數的 chip 來源（kd_golden_cross 以外）持續有影響，本次未處理。
- **`market_screen_picks` 沒有 `(run_id, ticker)` 唯一鍵**（D019 已記錄，本次仍未加）
- **`stock_chip_features_daily` 涵蓋率斷層**（train/serve skew）尚未處理，
  重訓仍被 P1–P3 阻塞
- **AI-Telegram 的改動未 push**，且該檔有他人未提交內容，不可整檔提交
  （**2026-11-20 更新**：該改動已在遠端 `2a3808aa3`；該檔工作樹目前的差異是**他人**的未提交內容）
- 22:25 的 nightly 重跑與 22:50 的發佈結果，另行複查

---

## 7. 發佈時序修正（2026-11-18，Walter 批准「do 1 and 2」）

### 7.1 問題

11/17 的 nightly 認證通過（23:09:53）且 gh-pages push 成功（23:18:24），但
`https://groovelab.dev/` 仍顯示 11/16 的內容。

追查鏈路：

1. 22:50 的發佈器等 nightly 結束 → 23:10 執行 publish → gh-pages push 成功
2. `publish_ghpages.py` 接著跑 `postflight_daily.py --after-publish` → **exit=1**
3. `publish_verified_sites.ps1` 在第一個子腳本非零時就 `exit` → `sync_groove_release.py`
   與 `chip_push.py` 從未執行 → `C:\Groove-Lab` 停在 11/16
4. 直到 11/18 00:00 的 hourly catchup（`PUBLISH_ONLY` → 00:09）才補上，線上才回到 11/17

失敗的 check 是 **`company_null`**（不是排程時序）：

| 檢查 | 23:19（同夜發佈） | 00:05（跨午夜補同步） |
|---|---|---|
| `company_null` | **false**（當日 company 空值 > 5） | true（`null=0`） |
| 其他 check | true | true |

`daily_data2_full.company` 是由 `tw-invest-suite-company-refresh`（**23:25**）填的，比發佈器晚；
所以同夜發佈時 postflight 如實失敗 → 整條發佈鏈中止。

### 7.2 修法

在 `scripts/publish_ghpages_daily.ps1` 加上依賴感知等待（repo 與 runtime 同一份 bytes）：
等 nightly 停止後，若 nightly 是「今天」跑的，再等 `company-refresh` 與 `sync-legacy`
今日已執行過。判斷用 `LastRunTime.Date` 而非 rc，失敗的 producer 仍讓 postflight 如實失敗。

原本想直接改排程觸發時間（22:50 → 23:45），但該排程以 S4U 登入、`Set-ScheduledTask` 被 ACL 拒、
`schtasks /change` 要求互動式密碼 → 改用程式碼層方案（版本可控、不依賴排程權限）。
原始排程 XML 已備份於 `scripts/_debug/publish_task_before_20261118.xml`。

### 7.3 預期效果

發佈時間由約 23:19 移到約 23:31，但**同夜完成**兩站同步與 Telegram push，
`groovelab.dev` 不再落後一個 session，也不再需要跨午夜補同步。

### 7.4 Push（Walter 批准）

- `tw-invest-suite`：`a1e6244`（精選歷史 tab ＋ 每日 24 檔視圖）、`87e3ce1d4`（short 分數保留兩位小數）、
  以及本次的發佈等待修正與文件 → push 到 `origin/main`
- `AI-Telegram`：`strategy_lab/finmind_batch_update.py` 的 derived 補算修補 → 逐 hunk 取用後 commit 與 push
  （該檔另有他人未提交內容，**不可整檔提交**）

---

## 8. 2026-11-19 資料完整性檢查與四項修補

### 8.1 檢查範圍

官方 `daily_chain_audit.py --no-notify`（唯讀）+ 自訂 DB 層稽核：

- `daily_data2_full` 最新日、列數／不重複標的數、重複 `(Ticker, Date)`
- 衍生欄位（`change_pct`／`sma_*`／`atr_14`／`rsi_14`／`is_gap`）逐日 NULL／0 統計
- `company`／`SharesOutstanding_shares` 空值、`metadata_quarantine` 未結案數
- D019 精選契約（名額數／distinct／每 bucket 組數）
- 認證 manifest 的 2,037 個 artifact 逐一雜湊比對
- 線上 `groovelab.dev` 與 `walterliu168.github.io` 的實際回應位元組

### 8.2 健康的項目

| 項目 | 狀態 |
|---|---|
| DB 最新交易日 | 2026-11-19，1,962 列／1,962 檔 |
| 重複 `(Ticker, Date)` | 0 |
| `metadata_quarantine` 未結案 | 0 |
| 衍生欄位 11/13～11/18 | 全部正常（`change_pct` NULL=0、sma/atr 全非 0、漲跌幅範圍 [-100, 10]） |
| 衍生欄位 11/19 | 19:00 那班已補算完成（見 8.4） |
| D019 精選契約（run 114／11-19） | 24 名額／24 distinct／8 組各 3 檔 → PASS |
| 11/18 nightly | marker D056-3 ok、run_id 112、publication verified、**postflight_exit=0**（D021 的發佈等待修正生效） |
| live 資料層 | groovelab.dev 的 JSON／manifest／readme 與本地**位元組相等**，nightly_id 與認證 session 一致 |
| runtime ↔ repo SHA | 9 個 cron 檔全 MATCH |

### 8.3 P1：live 精選頁每天有 6 小時少了「🎯 潛在反彈」分頁

**症狀**：`https://groovelab.dev/watchlist.html` 不含「潛在反彈」；live 檔 1,951,377 bytes／25 個
pick-ticker，認證版 2,118,583 bytes／85 個。官方 audit 的 `manifest missing/hash_mismatch=1`
指的就是 `watchlist.html`。

**根因**：`news_refresh_watchlist.py`（排程 18:00）會重渲染 live 頁面（腳本明文寫「live 頁面會被覆寫」）。
該次渲染時 `render_full_watchlist.py` 的 `_fetch_margin_distress_candidates()` 回空：

1. `outputs/margin_rebound/<今天>.json` 還沒產生（margin_rebound scan 在 nightly 的 Stage 5，約 23:06）
2. 退回 DB fallback，但 11/19 的 `MarginBalance` **1,962 列全部是 0**（margin 資料集尚未載入，
   `dl_errors` 有 `Canonical source is empty`）
3. → `margin_candidates` 為空 → `if margin_candidates:` 整個分頁被**靜默略過**
4. live 頁面被覆蓋 → 使用者整天看到少一頁、少 60 檔的頁面

**修法**：候選改為**逐級回退**，且分頁標明資料日：
today 的 scan JSON → **最新已產生的 scan JSON** → 最新有 `MarginBalance > 0` 的日期的 DB fallback → 原行為。
回退到較舊日期時，分頁會顯示「⚠ 本次融資資料日為 X（最新一筆資料尚未含融資資料，22:25 後自動更新）」。

實測（runtime 副本）：`candidates=60  source_date=2026-11-18`。

### 8.4 P4：FinMind 18:00 那班為何仍留下佔位值

- 18:00 那班是 AI-Telegram Scheduled Pipeline（`automation/openalice_phased_download.cmd`
  分階段呼叫 `_fetch_today.py --phase price|inst|margin|daytrade`，都用同一份
  `strategy_lab/finmind_batch_update.py`）
- 18:00:09 的 `canonical_universe` 顯示 **degraded=true**：ticker **8291** 當日 TPEx 官方停牌
  （1963 候選 → 1962 解析，coverage 0.99949）；19:00 那班已是 coverage 1.0
- 18:01:54 margin 資料集報 `Canonical source is empty`；`TaiwanStockShareholding` /
  `TaiwanStockIssuedShares` **完全沒有 11-19 的 state** → 該階段在資料集迴圈**之後**就中止
- 原本的修補只把 derived 補算包在「資料集迴圈」的 try/except 之後 → 例外若發生在迴圈之後
  （例如 `--ensure-state-schema` 的狀態檢查），補算仍然被跳過 → 11/19 仍留下佔位值

**修法**：把 derived 補算移進 `finally`（涵蓋 refresh 階段），只要 price 階段在範圍內就一定會補算。

**驗證**：把 2330 在 11/19 的 7 個衍生欄位清成佔位值後重跑 price 階段（`affected_rows=0` 的空跑情境）
→ `[derived] updated_rows=1`，且**修回的值與原值完全相同**。

### 8.5 P2／P3：Telegram 未送與 Groove 收據失敗

**P3 根因**：`C:\Groove-Lab\server.py` 有一份「認證股票頁」白名單，命中者送
`Cache-Control: no-store, no-transform`。`no-transform` 正是告訴 Cloudflare 邊緣不得改寫回應的標頭。
`/watchlist-history.html` **不在白名單**（11/16 新建該頁時漏加）→ 只送 `no-store` →
Cloudflare 有權注入 Web Analytics beacon → 線上回應 31,324 bytes vs 檔案 30,957 bytes →
`sync_groove_release.py` 的位元組驗證**永遠失敗** → Groove 收據 failed → `chip_push.py`
要求收據 verified → **Telegram 籌碼摘要自 11/13 起未送出**（ledger 是空的）。

**兩處修補**（Walter 指示「兩者都做」）：
1. `C:\Groove-Lab\server.py`：把 `/watchlist-history.html` 加入白名單 → 送 `no-transform`。
   備份：`scripts/_debug/groove_server.py.before-20261119`。**但 origin 行程以其他使用者身分執行，
   無提升權限無法重啟**（`Stop-Process` → Access denied），所以這項會在 origin 下次自然重啟時生效。
2. `scripts/sync_groove_release.py`（repo 與 runtime 同步）：驗證端容忍 beacon 注入——
   只移除 `cloudflareinsights.com/beacon.min.js` 那一支 script（整行移除與行內移除各試一次），
   其餘任何差異仍失敗；被容忍的路徑記在收據的 `cloudflare_beacon_tolerated_paths`。
   線上實測：`verified=5  tolerated=['watchlist-history.html']  PASS`。

**連帶效果**：Groove 收據轉綠 → Telegram 恢復 → hourly catchup 不再每小時重發同一場
（今天已重發 3 次：15:05／16:05／17:05，gh-pages 被重複提交）。

### 8.6 未修與邊界

- `chipscore_daily` 仍沒有最新交易日（11/19 缺），short 分數的 chip 來源長期缺料（既有結構性缺口）
- margin 資料集自 11/13 起每天報 `Canonical source is empty`，屬資料來源的問題，未追到底
- AI-Telegram 的 18:00 那班在資料集迴圈後中止的**根因**（哪個步驟拋例外）尚未定位，
  但補算已改為 `finally`，不再受它影響
