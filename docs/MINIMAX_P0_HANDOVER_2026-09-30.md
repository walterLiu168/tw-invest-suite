# MiniMax 接手文件：P0 正確性修復

日期：2026-09-30（Asia/Taipei）。本文件記錄 Codex 實作與實測，不能代替下一次正式 nightly 認證。

> 後續更新：7/31 模型停滯已修復，並加入無 AI agent 的原生每日 inference 與輔助來源刷新。完整設計與 MiniMax 維護 prompt 位於 `D:\CODEX\AI-Telegram\docs\DAILY_MODEL_AUTOMATION_2026-09-30.md` 與 `D:\CODEX\AI-Telegram\docs\MINIMAX_DAILY_MODEL_MAINTENANCE_PROMPT_2026-09-30.md`；本文件下方「仍停在 7/31」是修復前歷史狀態。

## 1. 可直接貼给 MiniMax 的接手指令

請接手 `tw-invest-suite` 與 `AI-Telegram` 的維護。先讀本文件，再讀兩個 repository 的 `AGENTS.md`、既有 PLAN／BUGS／CHANGELOG，以及 `C:\Users\icemo\Documents\strategy-review-2026-09-29\p0-fixes-20260930` 的證據。不要假設舊對話中的日期、狀態或行號仍然有效。

Codex 已修復選股因子接線、特徵消費驗證、報酬定義標示、可選 ML 時間切分、歷史籌碼驗證證據，以及 forward ledger 自動刷新。11 個 runtime 檔案已同步；每日 Windows 排程的新子程序會載入修改。請勿再加第二個 scheduler，也不要重啟健康中的 AI forever owner。沒有依賴 ChatGPT 或 MiniMax 定時喚醒才能執行的新增流程。

下一步：觀察正常 18:20 選股與 22:25 nightly，以實際官方交易日、當次 nightly_id／data_date／run_id 驗證 DB、50 份報告收據、當次受管來源雜湊、D056-3 marker、兩站遠端 manifest、postflight=0、四份 Telegram 報告及籌碼摘要的 positive message_id／去重 ledger。不要把 9 月 29 日已發布的舊證據當作本次新程式的正式發布證明。若來源未落地，保留真實日期與缺漏原因；可用的正確資料繼續報告，不填零、不偽造收據。

尚需處理的維護事項：正式模型最後預測仍停在 2026-07-31；AI 主排程仍為 Interactive 登入。請先查明模型生命週期與既有排程政策，再提最小修復。不要直接啟用凍結研究模型、重新訓練／commission 策略，或重建過去訊號來假裝前瞻績效。排程設定與實際睡眠喚醒證據要分別驗證。八個舊 OpenAlice 重複 FinMind 任務維持停用。

既有 repository 有大量使用者／其他 agent 未提交修改。只整合本次 before→after patch；不要 `git add -A`、reset、clean 或覆蓋整棵目錄。先檢查 patch 與目前 SHA 再套用。不要修改資料庫 schema、下單或輸出憑證。只有失敗、恢復、完成或需要使用者處理時用繁體中文通知；健康且證據未變時保持安靜。

## 2. 修復範圍與設計決策

| 項目 | 本次處理 | 明確界線 |
|---|---|---|
| P0-1 因子無效 | 從 canonical OHLCV 推導 VolumeBurst／KD；news 在全部候選排名前載入；分數保留來源與貢獻 | Zen 保留為選後描述，不宣稱參與排名；沒有隨機換股 |
| P0-2 freshness ≠ consumption | 驗證當日 volume_ratio_20d 有效覆盖率，實際用於量能加分；KD 整欄未知會失敗；個別未知保留並列註記 | excess_return_20d 明確是描述欄位，沒有擅自加成為新排名因子 |
| P0-3 報酬名稱 | 保留現有日曆日 raw-close 算法並提供 return_definition，報告標示日曆日價格報酬與基準定義；缺報酬持續存 NULL | 沒有改成交易日 total return，也未建立公司行動調整來源。此屬定義／標示修正，不是新策略 commissioning |
| P0-4 ML | 未成熟標籤保留 NaN，訓練 purging 排除越過測試起點的標籤，重疊日期只計一次 | 此模組不是每日 24 檔規則評分器；測試通過不代表獲利證明 |
| 歷史籌碼 audit | 同 nightly 收據＋原始 SOURCE／HISTORY／CHIPS_HISTORY／DB_VERIFY log 交叉核對 | 不再用 min(price_days,5) 推算；這是重讀實際逐欄驗證證據，不是 audit 再呼叫 provider 完整下載一次 |
| 過期 ledger | 補齊既有 DB 訊號與到期 outcome，原始訊號與已完成 outcome 保留；atomic replace＋writer lock | 新增的歷史 DB 列標示 stored_db_signal_backfill，不能算成當時真實發布的前瞻訊號 |

### 因子契約

- VolumeBurst：當日量 ≥ 前 20 個已存交易觀測量平均的 2 倍。需完整 20 筆基準量；沒有完整資料則未知。
- KD：9 筆窗口，K／D 遞迴係數 1/3，50 起算；讀取截至目標日的最近 60 個 canonical 市場日期。無效 OHLC 或平坦區間會重置，不能硬填訊號。
- KD 交叉：前次 K≤D 且當次 K>D。缺少足夠歷史保留 NULL。
- 新聞：published_at 與 crawled_at 都受目標日截止上限約束；JSON related_tickers 精確匹配。最多讀 50,000 列，超出時報錯而非悄悄截斷；每 ticker 最近 5 則、5 日視窗。這是日級截止，並非精確盤中時間的回測保證。
- 長期評分維持四維 percentile：市值 50%、240 曆日 30%、120 曆日 10%、60 曆日 10%；同分 ticker 升冪。不同量綱先各自正規化。
- 短期權重保持原規則；已恢復的量能、KD、新聞會改變名單。分數原樣寫進 market_screen_picks.score。
- stock_features.excess_return_20d = 原始 20 曆日價格報酬 − 當日有效樣本的等權平均價格報酬；不是 TAIEX 超額總報酬。
- 舊欄位名 excess_return_60d／240d 為相容用途保留，含義必須搭配 calendar_day_raw_price_return_v1。未遷移 schema。

## 3. 程式地圖

主 repository：`C:\Users\icemo\Projects\tw-invest-suite`。
runtime：`C:\Users\icemo\.claude\skills\tw-invest-suite\scripts`。
AI repository：`D:\CODEX\AI-Telegram`。

| 檔案／函式 | 維護責任 |
|---|---|
| scripts/db_client.py：signal_flags、screen_signal_features、refresh_chip_signals | canonical 訊號計算、日期界線、更新既有 chipscore 列 |
| scripts/db_client.py：assert_feature_freshness、news_for_tickers、RETURN_DEFINITION | 消費欄位有效率、新聞截止、報酬契約 |
| scripts/stock_features_daily.py：refresh、main | 每日特徵 UPSERT、chip flags、可選自動帳本更新，帳本失敗有收據且不阻擋其他有效市場報告 |
| scripts/sync_legacy_tables.py | legacy 同步後同交易重新計算 flags，避免再次被 NULL 覆蓋 |
| scripts/market_screen.py | 全候選預先 enrich、排名、score_details；Zen 選後補描述 |
| scripts/market_screen_runner.py：persist_atomic、generate_artifacts | score/NULL 寫入、保留文字 rationale、獨立分數稽核 JSON |
| scripts/market_report.py、market_report_html.py、render_full_watchlist.py | 報酬定義與缺漏註記；修正缺報酬時 HTML 格式化 None 的錯誤 |
| scripts/market_screen_daily.ps1、run_daily.ps1 | 原有 Windows 任務接入 --refresh-forward-ledger |
| src/ml/features.py：add_target | 未成熟方向標籤 NaN、fwd_end_*d；所有 fwd_* 排除於輸入特徵 |
| src/ml/xgb_predictor.py：walk_forward_one | horizon purge、實際標籤成熟日檢查、latest causal fold 日期去重 |
| scripts/daily_chain_audit.py：canonical_history_snapshot、remote_snapshot | 30 日／五條籌碼實測證據、遠端實際 bytes SHA256 |
| AI taiwan_stock_report/forward_validation_log.py | stored signal merge、as-of outcomes、鎖、atomic replace、摘要；用 config.env_config 安全設定讀取器 |
| tests/test_p0_correctness.py | 邊界資料／新聞時間／缺值／ML 因果／audit 證據與遠端 hash 反例 |
| AI test_forward_validation_refresh.py | immutable signals/outcomes、無效價格、as-of、摘要、雙 writer 鎖 |

`src/ml` 由 repository 使用，本次沒有另建 runtime 副本。

## 4. 自動執行鏈

1. 既有 AI canonical downloader 落地並驗證資料。
2. `tw-invest-suite-market-screen` 約 18:20 啟動現有 PS1。先 stock_features_daily.py --refresh-forward-ledger，再選股 runner。
3. `tw-invest-suite-daily-report` 約 22:25 啟動 runtime run_daily.ps1；stock_features 階段同樣刷新 ledger，隨後既有 render／all_reports／publish／postflight。
4. `tw-invest-suite-daily-chain-audit` 隔日約 06:30 由原有 CMD 與 S4U 任務執行；改版後直接讀新 audit.py。預設通知政策與 Telegram 去重沿用現有設定。

沒有新增永駐 agent、ChatGPT automation 或 Windows 任務。AI forever owner 不支援 YAML hot reload，本次不靠改 YAML 生效，亦未重啟它。

新收據：`scripts/_debug/forward_validation_refresh.json`（stock_features 呼叫所在 repo/runtime 下）；`scripts/_debug/screen_scores/YYYY-MM-DD.json` 保存新跑選股的分數與因子明細，repair-only 不會用空因子覆盖原明細。這些是 debug 證據，不冒充 D056-3 正式 marker。

## 5. 2026-09-30 實測結果

- 最新 canonical 資料日：2026-09-29；chipscore 當日 1,963 列。
- 特徵刷新與讀回：1,938 列；被消費的 volume_ratio_20d 有效 1,938 列。
- chipscore：VolumeBurst 已知 1,962 列、true 196；KD 已知 1,857 列、true 109。未知 ticker 清單在 live_db_readback.json；不改成 false。
- DB-only 特徵＋實際帳本刷新 exit=0，129.18 秒，在既有 300 秒特徵階段上限內。單次成功不代表每天性能保證。
- 全選股＋Zen＋MD／HTML 預覽：24 筆，136.33 秒。與原已發布 cohort 的 (ticker,horizon) 對稱差 10；沒有覆寫原 published picks／run_id。
- 帳本原 267 筆訊號保留，905 筆從既有 DB 補回，共 1,172 筆。5D／10D pending 都 0。原訊號及既有 done outcomes 對照通过，再跑一次 CSV SHA256 完全相同。
- 帳本 price_as_of=2026-09-29；latest_source_prediction_date=2026-07-31；signal_stale=true。帳本收益是 raw close-to-close 觀測，未含費用、滑價、可成交性或公司行動調整，不是可交易的淨績效。
- 實際歷史驗證收據：30 個 session，price_rows_checked=58,719；五條籌碼 chips_rows_checked=293,595；同批次 log 核對通過。
- 既有 9/29 發布：nightly_id=330b4cb6cba641e28a979fcea02f1eaf、run_id=40、postflight=0；2,035 個 manifest artifacts，hash_mismatch=0；籌碼 message_id=1753。本次未重送。
- GitHub Pages 與 groovelab.dev 的該日 rawSHA 同為 233ab8bad1ce635ab82fbd61b4f002c01a77869c66f25b5d4a8550eacefb8024。
- 本次完整測試結果、執行時間、runtime SHA 以 tests.json／tests log／deployment_receipt.json 為準。包含真正 XGBoost 小型因果 smoke test；不報告其數值作策略績效。

## 6. 維護／除錯手冊

先看最新日期與 active owner，再看具體收據；不要看到 timeout 就重啟或重送。

```powershell
# 帳本內建純合成驗證；不改 production ledger
C:\Python314\python.exe -X utf8 D:\CODEX\AI-Telegram\taiwan_stock_report\forward_validation_log.py --self-check

# 補既有訊號 outcomes；會安全更新 production ledger，不訓練、不發訊息
C:\Python314\python.exe -X utf8 D:\CODEX\AI-Telegram\taiwan_stock_report\forward_validation_log.py --refresh-only

# 讀回稽核；會寫 audit 狀態檔，不送 Telegram、不跑 production pipeline
C:\Python314\python.exe -X utf8 C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\daily_chain_audit.py --no-notify
```

TW DB 使用受保護的 TW_DB_PASSWORD 環境；AI ledger 用既有 config.env_config 載入 local／環境／Windows 使用者設定。不要將密碼寫進命令、文件或提交。若缺憑證，修復執行帳戶的設定來源，不要移除安全檢查。

故障分流：

- 整欄 KD 未知：檢查 canonical 日期、OHLC 數值與歷史；個別缺歷史則保留 unknown 與註記。
- News 不加分：先檢查 published_at／crawled_at 截止與精確 ticker；不能改用未來新聞使排名看起來有變化。
- Ledger lock 失敗：確認另一個 writer 還在跑，稍後由正常階段重試；不要刪鎖檔解鎖。
- forward summary stale：分開判斷 price_as_of 過期、source prediction 過期；刷新 outcomes 不能治好沒有新預測。
- Canonical history unverified：核對 nightly_id、六條當日來源、30 日價格、五條 30 日歷史及 DB_VERIFY。缺 log 必須當缺證據，不推算替代。
- Runtime drift：先比較 source/runtime/部署收據，保留其他 agent 修改；不要把工作樹所有檔案直接覆盖到 production。

## 7. 回復與發布界線

本次前置备份、runtime 备份、DB derived snapshot、原 ledger one-time backup、before→after patch 均保留於交接包；production ledger 自動備份在其目錄下的 `forward_validation_log.before_refresh.csv`。

修補檔使用 LF，部分原始 Windows 檔案為 CRLF。檢查或套用時使用 `git apply --check --ignore-space-change --whitespace=nowarn <patch>`；本次已在原始備份副本驗證可套用。現有工作樹已含修改，請勿重複套用；`after/` 與 source_manifest.json 提供完整檔案與 SHA256 對照。

回復前先確認 owner 不在使用該階段，並比對目前 SHA 等於本次部署後 SHA；只回復本次涉及檔案，避免覆蓋後續維護。原始 canonical 資料、歷史預測、published picks／marker 沒有被本次改寫。derived_before_2026-09-29.json 僅作已改衍生欄位的比對，不要整表還原；不要倒退覆蓋新交易日。帳本原始及已完成 outcome 不應回退。

目前兩個 repository 原有大量未提交修改，本次沒有混合 commit／push，也未重跑完整夜間發布或盲目重送 Telegram。程式部署與 DB 刷新已完成；**新程式的下一次正式每日發布仍需實際收據驗收**。這是 MiniMax 接手的第一個完成條件。
