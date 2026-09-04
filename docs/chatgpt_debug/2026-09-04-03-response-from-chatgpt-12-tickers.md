# ChatGPT response: 12 newly listed tickers master table backfill review

> **Submitted**: 2026-09-04 by ChatGPT (visible UI)
> **Target**: industry_type + cron + 12 tickers
> **Status**: pending
> **Scope**: db | cron | scripts

> **Coding preflight**: REUSE — 沿用現有 FinMind client、Task Scheduler 與 renderer 架構；本次僅唯讀審查，未修改 DB、排程或檔案。

## Review of Mavis findings F1-F4

### F1. `industry_type` 確實過期，但時間證據需修正
- **Verdict**: 部分成立
- File: `docs/chatgpt_debug/2026-09-04-01-debug-12-newly-listed-tickers.md:20`
- Live DB:
  - 1,962 rows
  - `MIN(last_updated)=2026-04-29 21:15:52`
  - `MAX(last_updated)=2026-04-29 21:15:53`
  - `information_schema.TABLES.UPDATE_TIME` 目前為 NULL
- Issue: InnoDB 的 table `UPDATE_TIME` 不宜作為可靠 freshness gate；文件中的 21:04:05 也與目前資料列時間不符。
- Decision: 改以 ingestion run audit、source_as_of、last_seen_at 與資料列 changed_at 判定 freshness。
- Priority: **high**

### F2. 12 檔確實不在四表，但只有 `industry_type` 是現役主檔
- **Verdict**: 缺漏成立，master 分類不成立
- File: `docs/chatgpt_debug/2026-09-04-01-debug-12-newly-listed-tickers.md:26`
- Live DB:
  - `industry_type`: 1,962 rows
  - `shares_master`: **2,196 rows** (我之前誤報為 0/12)
  - `stock_info`: 0 rows
  - `stock_names`: 0 rows
  - 12 檔在四表皆為 0/12
- Issue: 空表 `stock_info`、`stock_names` 不能視為可切換的 master；`shares_master` 是流通股數資料，不應承擔公司名稱 canonical 職責。
- Decision: 近期仍由 `industry_type` 當 operational master。不要用本次 FinMind 資料建立 `shares_master` 空殼列。
- Priority: **high**

### F3. OHLCV 命中成立，但 2,628 是歷史全集，不是最新日
- **Verdict**: 部分成立
- File: `docs/chatgpt_debug/2026-09-04-01-debug-12-newly-listed-tickers.md:37`
- Live DB:
  - 全歷史 distinct ticker：2,628
  - 2026-09-03 最新日：1,955 tickers
  - 12 檔於 2026-08-27 至 2026-09-03 每個交易日皆有資料
  - **2026-09-03 的 company 為 NULL／空值：1,955/1,955**，而不只是 12 檔
- Issue: 最新日與歷史全集混用，且 `daily_data2_full.company` 的回填本身不是穩定日常階段。
- Decision: 將「最新交易日 universe count」「歷史 distinct count」「metadata gap count」拆成三個獨立 gate。
- Priority: **high**

### F4. FinMind 有資料，但不是一個 ticker 一列
- **Verdict**: 12/12 有命中；直接 full upsert 不安全
- File: `scripts/finmind_client.py:105`
- 2026-09-04 live query:
  - 回傳 3,570 rows（現有 client 預設近 365 天）
  - 12 tickers 共命中 32 rows
  - 同一 ticker 可同時有歷史 emerging、目前 twse／tpex，甚至同日多個 `industry_category`
- Issue: 如果直接依 API 回傳順序 upsert，最終產業可能由不確定的最後一列覆蓋；也可能把興櫃歷史狀態當成目前市場。
- Decision: recurring job 必須先 staging、排序、去重及分類；不接受 raw rows 直接進 canonical。
- Priority: **high**

## Architecture decisions

| 問題 | 決策 |
|---|---|
| Upsert 或 staging | 採 hybrid：raw staging + validation；無歧義的新 ticker 可自動新增，名稱／產業／市場變更及刪除須 quarantine 或 review。PK upsert 只能保證機械冪等，不能保證語意正確。 |
| 執行時間 | **不選 17:30**。現役 OHLCV 是 17:35、失敗重試 17:55；建議 **18:05～18:10**。若將來需要上市首日開盤前可見，再增加 09:00 metadata-only discovery，但仍保留收盤後 reconciliation。 |
| 通知 | 要。只在新增、歧義、殘留缺漏、資料量異常或執行失敗時通知；零變更與週末保持安靜。 |
| Canonical table | 近期保留 `industry_type`。中期建立完整 `security_master`，或先補齊並擴充 `stock_info` 後再遷移；保留 `industry_type` compatibility view／projection。 |
| 其他三表 | `stock_info`／`stock_names` 目前為空，不建議同步製造第二、第三份 truth；`shares_master` 只由可靠股本來源維護。 |

## Additional findings

### F5. 目前 12 個靜態頁面是缺檔，不是單純顯示 NULL
- File: `scripts/daily_full_tickers.py:45`
- Issue: renderer 的 ticker universe 完全取自 `industry_type`；12 檔不在主檔，因此不會進入批次。`C:\Groove-Lab\analyze` 現有 1,965 個 HTML，但 12 個目標檔案全部不存在；抽查 tw-invest-suite GitHub Pages 與 stock-report GitHub Pages 皆為 404。
- Suggested fix: 完成主檔 promotion 後，明確驗證 12/12 檔案產生、頁首公司名、GitHub Pages HTTP 200 與公開內容；不能只驗證 SQL row count。
- Priority: **high**

### F6. 不可直接執行 `src/_daily_backfill.py` 修公司名稱
- File: `src/_daily_backfill.py:39`
- Issue: 該腳本除了更新 company，還會刪除／重建多張 legacy table、關閉 picks，並新增硬編碼 `total_tickers=1957`、`picks_count=24` 的 market run。
- Suggested fix: 建立專用 metadata backfill，僅更新受影響 ticker；legacy table 交由既有 23:30 sync。所有寫入放在 transaction，驗證失敗 rollback。
- Priority: **high**

### F7. 17:30 早於實際 OHLCV landing
- File: `docs/handoff_chatgpt.md:81`
- Issue: Task Scheduler 顯示 OpenAlice Daily OHLCV 1735 在 17:35、retry 在 17:55；Mavis 所稱「17:30 after daily close pipeline」不成立。
- Suggested fix: 單一 cron 設 18:05～18:10，並檢查當日／最新有效交易日是否 landing；加 advisory lock，避免補跑重疊。
- Priority: **high**

### F8. 市場別不能用 ticker 長度判斷
- File: `scripts/render_ticker_db_only.py:210`
- Issue: 程式目前把所有四碼 ticker 判為 twse，但這 12 檔同時包含 twse、tpex，另有歷史 emerging。
- Suggested fix: canonical master 儲存標準化 market／listing_status，renderer 直接讀欄位；禁止以代碼長度推斷市場。
- Priority: **high**

### F9. Canonical schema 缺少生命週期與來源欄位
- File: `data/schema/mysql.sql:67`
- Issue: repo schema、文件與 live DB 已漂移；現有 `industry_type` 也沒有 market、listed_date、status、source、source_as_of、first_seen_at、last_seen_at。
- Suggested fix: 中期改為：
  - canonical security identity：ticker、name、market、listed date、status
  - classification：industry、taxonomy source/version
  - provenance：source、source_as_of、raw hash
  - lifecycle：first seen、last seen、changed at、delisted at
  `industry_type` 保留為相容 projection，降低其他模組遷移風險。
- Priority: **mid**

### F10. Blind full refresh 會破壞稽核時間並擴大 universe
- File: `docs/chatgpt_debug/2026-09-04-01-debug-12-newly-listed-tickers.md:72`
- Issue: API universe 明顯大於現有 1,962 檔；直接 upsert 全部可能納入 ETF、ETN、權證、興櫃或歷史證券。即使值未變，全面 update 也會重寫 `last_updated`，消除真正的變更時間。
- Suggested fix:
  - staging 保存所有 raw rows
  - promotion set 必須一 ticker 一列且符合允許的 security type
  - 只有欄位實際變更才更新 `changed_at`
  - source 缺少 ticker 時不得自動 DELETE
  - API row count 大幅下降、重複衝突或缺必要欄位時 fail closed
- Priority: **high**

### F11. 告警必須涵蓋完整修復鏈
- File: `scripts/daily_full_tickers.py:214`
- Issue: 僅告警「發現新 ticker」仍可能留下未回填、未渲染或未發布狀態。
- Suggested fix: 通知包含 run id、交易日、來源筆數、新增／更新／quarantine ticker、promotion 後 missing count、12/12 render 結果及 publish 結果。相同事件以 ticker + source date 去重。
- Priority: **mid**

### F12. 尚需處理的 domain edge cases
- File: `scripts/render_ticker_db_only.py:205`
- Issue:
  - 興櫃轉上市／上櫃，同 ticker 多 lifecycle rows
  - 上市、上櫃、創新板與產業分類是不同維度
  - -創、-KY創 等名稱後綴變更
  - 更名、併購、ticker 重新使用或換號
  - 暫停交易、下市櫃與恢復交易
  - FinMind HTTP 200 但 partial／duplicate／blank data
  - 同日多個產業 taxonomy，不可依回傳順序決定
  - 非普通股、ETF、ETN、權證及特殊代碼誤入
  - source absence 不等於 delisted
  - 公司名稱回填是 current-name 還是 historical-as-of 語意
- Suggested fix: 以 lifecycle/status 模型與明確 taxonomy priority 處理；不要假設「有 OHLCV＝目前上市普通股」，也不要硬刪歷史證券。
- Priority: **high**

## Questions back to Mavis

1. 哪一個 renderer／哪個已存在的 `analyze/<ticker>.html` 實際顯示 NULL？目前 canonical 產生流程會排除這 12 檔，且本機與 GitHub Pages 都是缺檔。
2. FinMind 同 ticker、同日多個 industry_category 時，預定採用哪一套 taxonomy priority？
3. Promotion universe 是否只含目前 twse／tpex 普通股？emerging、ETF、ETN、權證與已下市資料如何分類？
4. 是否同意禁止呼叫 `src/_daily_backfill.py`，改由專用 metadata transaction，再交給 23:30 legacy sync？
5. 公司更名／產業變更可否自動更新，或一律進 quarantine？建議新增 ticker 自動、既有 ticker 變更需 review。
6. 請在實作結果附上 staging counts、12/12 canonical rows、最新日 missing count、12/12 HTML、公開 HTTP 200 與 alert 測試證據。

## Status

> 建議 Walter 核准的範圍是：**一次性 staged backfill 12 檔、18:05～18:10 recurring reconciliation、異常告警及端到端 artifact gate**。暫不核准 blind full upsert、執行 `_daily_backfill.py`，也不核准直接把空的 `stock_info` 升為 canonical。

*(Mavis 將 append 實作結果)*
