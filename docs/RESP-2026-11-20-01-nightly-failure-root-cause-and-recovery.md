# 2026-11-20 nightly 失敗根因、兩處修補與認證鏈恢復

**日期**：2026-11-20
**範圍**：`tw-invest-suite`（repo 與 runtime）、`AI-Telegram`（local-only 未 push）

> **2026-11-20 15:1x 更新（push 狀態）**：本文件寫成時，`tw-invest-suite` 的四筆提交尚未 push；
> Walter 隨後指示「tw-invest-suite 三筆 push, omit telegram for now」，
> 該 repo 的提交**已 push**（`HEAD == origin/main`）。`AI-Telegram` 的兩筆（`9760439`、`0d6ead8`）
> **仍未 push**（依指示保留）。

---

## 0. 結論先講

11/19 的 nightly **不是「成品待確認」，而是失敗**。複查過程中另外挖出一個更嚴重的問題：
**每小時的認證補救排程自 2026-09-30 起就是壞的**，十次午夜嘗試全部在同一行錯誤上死掉。
這解释了為什麼 11/11 與 11/19 的 nightly 失敗後從來沒有自癒過。

三個根因都已修補並驗證，並在正式排程下完成一次端到端恢復，提交為：

| 倉庫 | 提交 | 內容 |
|---|---|---|
| `tw-invest-suite` | `00e343511` | P6：listing venue 在供應商快照缺口期的解析（含完整性門檻與交易所備援） |
| `tw-invest-suite` | `a1bed6c11` | P8：認證可取代更早的排程執行 → stale rc 降為 WARNING，讓發布鏈不再自我封鎖 |
| `tw-invest-suite` | `a33e68aa1` | docs：本文件與決策紀錄 D023／D024 |
| `AI-Telegram` | `0d6ead8` | P5：132 MB 續傳狀態檔的原子替換在 WinError 5 下退避重試 |

四筆寫成當時皆為 **local-only，未 push**；**2026-11-20 更新：該 repo 已 push**
（Walter 指示「tw-invest-suite 三筆 push, omit telegram for now」），
`AI-Telegram` 的 `0d6ead8` 依指示仍未 push。

**最終結果（2026-11-20 06:13）**：05:00 那班 catchup 以修補後的原始碼重跑，
Stage 1–7 全綠並重新認證（`nightly_id=ffa8f4ca…`，06:04:14），
GitHub Pages、Groove-Lab、Telegram 三段收據全部轉綠（Telegram `message_id=4219`）。
chain audit 的 5 項 nightly findings 全部清零，只剩一項與本次無關的既存項。
詳見第 8 節。

---

## 1. 複查結果：11/19 nightly 是失敗的

`daily_run_20261119.log`（3,287 bytes）：

```
[Stage 1] valuation ... OK (exit 0)
[Stage 1] finmind_maint ... FAILED (exit 1)
FATAL: nightly not certified; publication is blocked
  reason: FATAL: required stage failed/missing
```

- `complete_e8d17d1f71774058ab49aabab9dff671.exit` = `1`
- `stages_e8d17d1f71774058ab49aabab9dff671.json` = valuation `true`／finmind_maint `false`
- 因此 **Stage 2–7 未執行、postflight 未跑、無 nightly marker、無發布、無 Telegram 收據**

線上看起來有 11/19 資料的原因：`groovelab.dev/watchlist.html` 是 22:06 的 `news_refresh`（groove-only 輸出）寫的，
不是 nightly 的認證產物。**頁面有資料 ≠ 認證完成**。

---

## 2. 根因一（P5）：132 MB 狀態檔的原子替換競態

`AI-Telegram/strategy_lab/finmind_batch_update.py` 的 `StateStore.save()` 用
`tmp.replace(self.path)` 原子替換 `finmind_batch_state.json`（132 MB）。
22:00:43 拋 `[WinError 5] 存取被拒`（tmp → 正式檔的 rename 被拒）。

同一個檔案有**兩個 producer**：`AI-Telegram Scheduled Pipeline` 與 nightly 的
`_fetch_today.py --phase canonical`。`logs/canonical_universe_<date>_<ts>.json` 在
**22:00:29 與 22:00:33 各產生一支** → 兩者並行。

這是**既有基礎設施競態，不是本次改動造成的 regression**。`dl_errors.jsonl` 中同型 WinError 5 共 5 次：

| 日期 | 備註 |
|---|---|
| 10/13 23:00 | |
| 10/15 23:00 | |
| **11/11 22:03** | **當時 nightly 同样 FAILED，log 完全同型** |
| 11/12 22:01 | |
| 11/19 22:00 | 本次 |

### 修法

狀態檔的 marker 只是**續傳快取**——資料本身早已寫進 DB，掉一個 marker 只會多下一次載。
所以不值得讓它中止整個階段：

- `StateStore.__init__`：改為 `path.read_bytes().decode("utf-8")` → `json.loads`。
  先讀完關掉 handle 再解析，避免 132 MB 檔在解析期間被別的 producer 鎖住。
- `StateStore.save()`：原子替換失敗時以 `PermissionError` 退避重試（`retries=8`，指數退避上限 3.0s，
  最長約 13.5 秒）；最終仍失敗時刪掉 tmp 並重新拋出（**保持 fail-closed**）。

---

## 3. 根因二（P6）：午夜後供應商快照還沒發布——補救網壞了七週

### 3.1 症狀

午夜那班的 `daily_run_<date>.log` 在 **00:00:05** 死在同一行：

```
RuntimeError: Listing venue metadata unavailable
[Stage 1] valuation FAILED (exit 1)
FATAL: nightly not certified; publication is blocked
```

出現在 **09/30、10/01、10/02、10/03、10/06、10/07、10/22、11/04、11/12、11/20** 共 **10 次**——
每個有午夜補跑的交易日都一樣。

### 3.2 供應商的快照語意（實測 2026-11-20）

`yfinance_batch.refresh_market_map()` 原本只查 `TaiwanStockInfo` 的 `start_date=today, end_date=today`。

實測結果：

| 查詢 | 回傳 |
|---|---|
| 單日 `2026-11-20` | **3,358 列**（twse 1,383 ＋ tpex 1,020 ＋ emerging 374），全部標記 date=2026-11-20 |
| 7 天視窗 `11-13..11-20` | 3,361 列 = 11/20 完整快照 3,358 ＋ 11/14、11/18、11/19 各 1 列差異 |
| 30 天視窗 `10-21..11-20` | 3,385 列，過去日期最多 17 列 |

**供應商只保留一份完整快照，日期標成「今天」；過去日期只留當日變更的差異列。**
完整快照約在**午夜後一小時**才發布（11/20 那天的證據：00:00:05 查不到、01:00:03 查得到）。

於是：00:00:01 的補救跑永遠落在缺口裡 → Stage 1 valuation 失敗 → 整輪 FAILED。
**每小時的補救網形同虛設**，11/11 與 11/19 的 nightly 失敗後自然沒有任何東西把它救回來。

### 3.3 修法

三層：

1. **擴大視窗**：查 7 天而不是今天。
2. **完整性門檻**：`MIN_LISTING_SNAPSHOT_ROWS = 1500`。完整快照有數千列，差異日只有 1–2 列。
   這個門檻把「已發布」「**發布中**」「只有差異」三種狀態分開——
   **半成品發布不會再被誤當成完整快照**（原程式會直接收下當天所有列）。
3. **備援來源**：當視窗裡沒有任何完整快照時（Model B 的午夜缺口），
   改用**交易所自己的 Open Data**：
   - TWSE `https://openapi.twse.com.tw/v1/opendata/t187ap03_L` → 1,098 檔
   - TPEx `https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O` → 898 檔
   - 聯集 **1,996 檔，零衝突**，對估值宇宙 1,974 檔覆蓋 **1,966**。

   選它的理由：交易所名單**沒有發布排程**，午夜隨時可用；FinMind 快照約 01:00 才出現。

另外把 venue 來源寫進 `finance_fetch.json` 收據（`venue_source`／`venue_source_date`），
讓降級是**可見的**而不是靜默的（延續 D022 的「不可靜默」原則）。

---

## 4. 驗證

### 4.1 P6 故障注入（8 情境全綠）

`scripts/_debug/_test_p6_candidate.py`：

| 情境 | 期望 | 結果 |
|---|---|---|
| 供應商今日完整快照 | source=provider | PASS（mapped=2400） |
| 午夜缺口：視窗只有差異列 | source=exchanges | PASS（mapped=2200） |
| 今日快照發布中（半成品 ＋ 昨日完整） | 取**昨日**那一份 | PASS（source_date=昨日） |
| 供應商呼叫直接回錯誤 | source=exchanges | PASS |
| 兩邊都掛 | fail closed | PASS（`RuntimeError: Listing venue metadata unavailable`） |
| 供應商錯 ＋ 交易所錯 | fail closed | PASS（同上） |
| 注入 rows 的既有語意 | 尾綴正確 | PASS（`2330.TW`／`1584.TWO`／`3293.TWO`／`2881A.TW`） |
| 過期／衝突 rows | fail closed | PASS |

### 4.2 venue 一致性（決定快取會不會被作廢）

`cache_coverage` 會用 `_market_map` 比對已快取資料的 `_symbol`
（`yfinance_daily.py`：`data.get('_symbol') == ticker + _market_map.get(ticker,'?')`）。
所以換來源若會改變 `.TW`／`.TWO`，全部 1,974 檔的估值快取會被判定失效。

實測 **1,982 個共同代號，尾綴相反 0 處** → 切換來源不影響既有快取。

覆蓋差異：官方名單有 14 檔是供應商快照沒有的；供應商多 421 檔是 ETF／ETN。

對估值宇宙 1,974 檔而言，**官方名單覆蓋 1,966，供應商快照只有 1,958**——備援來源的覆蓋率其實比較好。
11/19 那 16 檔缺估值快取的代號裡：

| 來源 | 數量 | 代號 |
|---|---|---|
| 官方名單有、供應商沒有 | 8 | 1808 潤隆建設、4804 大略國際、8084 巨虹電子、8291 尚茂電子材料、9103 美德向邦、9105 泰金寶、9110 越南製造加工、9136 巨騰國際 |
| 兩個來源都沒有 | 8 | 1589、2867、3426、4130、4987、5371、6806、8183 |

後者 8 檔已不在掛牌名單裡，只是還留在 `industry_type` 這張靜態表 → 走哪個來源都補不回來。
前者 8 檔在備援路徑下反而拿得到 venue。

### 4.3 既有測試與線上煙霧測試

- `pytest tests/test_valuation_sources.py -q` → **7 passed**
- runtime 實際檔案 `refresh_market_map()` → `{'source': 'provider', 'source_date': '2026-11-20', 'mapped_tickers': 2403}`
- 尾綴抽樣：2330.TW／1584.TWO／3293.TWO／0050.TW

---

## 5. 第三個缺陷（P8）：認證成功了，卻發布不出去

11/19 在 04:04:34 終於取得有效認證（`last_completed.json`：`status=ok`、`data_date=2026-11-19`、
`nightly_id=db92dacd…`、`run_id=114`、24 檔 picks），GitHub Pages 也發布並遠端驗證成功
（commit `c2df18c3`）。但 **Groove 同步與 Telegram 籌碼推送沒有執行**。

### 5.1 循環依賴

```
tw-invest-suite-daily-report（就是 nightly 本體，21:30 觸發）在 11/19 失敗 → task rc=1
  └→ build_dashboard.py 把 daily-report rc≠0 判成 🔴 CRITICAL（dashboard exit 2）
      └→ postflight_daily.py 看到 dashboard exit≥2 → overall_pass=False → exit 1
          └→ publish_ghpages.py 只看 post.returncode → status 翻成 "failed" → exit 1
              └→ publish_verified_sites.ps1 逐段檢查 exit code → 在 Groove 同步前停下
                  └→ chip_push.py 沒跑 → Telegram 收據停在 11/13
```

**用「要修的故障」去擋「修復路徑」**：`tw-invest-suite-daily-report` 的 rc=1 就是 11/19 nightly
失敗的倒影；catchup 在 03:00 重跑並成功認證之後，這個 rc 仍是舊的，要等到 11/20 21:30 的下一次
nightly 才會被覆蓋。於是只要某一晚 nightly 失敗，恢復路徑就會被永久堵住。

這和 P6 是同一種病：**用一個過時的失敗訊號去判斷現在的狀態**。

### 5.2 修法

認證若發生在某個排程上次執行**之後**，就代表那次執行已被取代 → 該排程的 rc 降級為 🟡 WARNING
（仍顯示在 Action items，不靜默）。判定用 `marker.started_at` 與 task `last_run` 比較，
兩者都是本機時間，取前 19 個字元做字典序比較。`build_dashboard.py` 的行尾是混用的
（CRLF 與 LF 交錯），因此替換用行尾無關的正則進行，其餘位元組逐 byte 保留。

### 5.3 代價

改動 `build_dashboard.py` 會改變 `source_hashes()` → 04:04 的認證立即失效
（`verify_marker()` 會比對 source 雜湊）→ 必須用新原始碼重新認證。
**05:00 的 catchup 會自動 `run_daily.ps1 -Force` 重跑整條**——這也是它第一次真正派上用場：
先前十次午夜補救都死在 P6，現在它把整條鏈重跑、重新認證，再往下發布。

## 6. 過程中的兩次自傷（已記錄）

### 6.1 只改 repo 未同步 runtime → 01:00 補救死在 SHA 閘門

`finalize_inputs` 會逐一比對 runtime 與 repo 的 SHA。01:00 那班在 Stage 1 四個階段全綠之後，
死在 `FATAL: runtime/repo SHA mismatch: yfinance_batch.py`。已補上同步步驟。

### 6.2 在 run 進行中改檔 → 02:00 補救死在「來源已變更」閘門

02:00 那班我在 02:12（Stage 1 stock_features 執行中）套用了 P6。
`pipeline_state.py` 的 `finalize_inputs` 另有一道閘門：
比對 run 開始時記錄的 `run['source_hashes']` 與執行當下的值 → 02:24:36 拋
`FATAL: Source changed before input finalization`。

**教訓**：認證鏈有**兩組**獨立的來源雜湊檢查，而且各在 `finalize_inputs` 與 `complete` 兩處執行。
**run 進行期間不可變更任何被 `source_hashes()` 涵蓋的檔案**
（`scripts/`、`src/`、`public/`，以及 AI-Telegram 的 `finmind_batch_update.py`）。
已寫進 `AGENTS.md` 的「不要做的事」第 10、11 項。

---

## 7. 殘餘風險（認證恢復後仍存在）

- **P1–P3 重訓仍被阻塞**：chip 特徵來源表（`data_source` 欄位顯示 2020-01～2026-06-11 建自
  `daily_data2`，之後改用 `daily_data2_full` 且從未回填）、歷史回填、缺漏日補齊。
- `chipscore_daily` 長期缺最新交易日（short 分數的 chip 來源）。
- margin 資料集自 11/13 起每天 `Canonical source is empty`。
- `company_refresh.py` 走同一個供應商快照，也有同樣的午夜脆弱性；
  目前 `industry_type` 的 `company` 欄位沒有損壞字元（0 筆），所以那條路徑是惰性的，尚未修。
- `C:\Groove-Lab` 的 origin 行程需提升權限才能重啟，`no-transform` 要等它自然重啟才生效。

## 8. 最終結果（認證與發布）

### 8.1 認證

| 項目 | 值 |
|---|---|
| data_date | 2026-11-19 |
| nightly_id | `ffa8f4ca35324509a613c0e7a2dcdd7d` |
| status | ok |
| run_id | 114 |
| picks | 24 |
| 認證完成時間 | 2026-11-20T06:04:14.117419 |
| venue 來源 | provider ／ 2026-11-20 |
| 估值覆蓋 | 1958／1974 fresh |

### 8.2 三段收據

| 收據 | 狀態 |
|---|---|
| `publication_result.json`（GitHub Pages） | verified ／ postflight_exit=0 |
| `groove_publication_result.json`（Groove-Lab） | verified ／ beacon 容錯 ['watchlist-history.html'] |
| `chip_telegram_result.json`（Telegram 籌碼摘要） | sent ／ message_id=4219 |

### 8.3 chain audit

狀態 **DEGRADED**（target 2026-11-19，檢查於 2026-11-20T06:14:41.399682+08:00）

剩餘項：
- 電源喚醒計時器證據無法讀取；尚未驗證實際睡眠喚醒

## 9. 附帶查到的另一個問題：AI-Telegram 18:00 那班中止

（獨立於 nightly，順手查完。）

`AI-Telegram Scheduled Pipeline` 的 `publish_static_site` stage **自 2026-11-03 起每天失敗**
（最後一次成功是 11/02，exit=0）。根因是 AWS 憑證檔不見了：

```
FileNotFoundError: [Errno 2] No such file or directory: 'C:\Users\icemo\Downloads\rootkey.csv'
  aws_amplify_deploy.py:53 in credentials()
```

- `config/shared_config.json` 的 `aws_amplify.credentials_csv` 寫死指向 `C:\Users\icemo\Downloads\rootkey.csv`；
  該檔已不存在（Downloads 目錄已被清理，只剩兩個無關檔案），整個使用者目錄下也找不到。
- `api_keys` 裡沒有 AWS 憑證，`credentials()` 第 52 行只有在 access/secret 齊全時才會跳過 CSV，
  因此**沒有替代來源**。
- pipeline 有 `SCHEDULER_CONTINUES_AFTER_FAILURE`，其他 stage 照跑，但
  `https://main.d1ydtmhelzqul1.amplifyapp.com` 這個靜態站自 11/03 起就沒有再更新。

修法需要憑證，必須由 Walter 決定（我不動憑證檔）：

1. 重新產生 root access key 並下載 CSV，放回 `C:\Users\icemo\Downloads\rootkey.csv`；**或**
2. 把 `credentials_csv` 改指到不會被清理的固定位置（例如 `D:\CODEX\AI-Telegram\config\rootkey.csv`）；
   **或**
3. 直接把 `aws_access_key_id` / `aws_secret_access_key` / `aws_session_token` 放進
   `config/shared_config.local.json` 的 `api_keys`（程式會跳過 CSV 這條路）。

建議 2 ＋ 3 併用：憑證不放在 Downloads 這種會被整理的目錄，也就不會再被清掉一次。
