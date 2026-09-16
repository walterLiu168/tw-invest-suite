# D056-2 修補驗收紀錄

狀態：完整執行驗收中；未宣稱遠端發布成功。時間均為 Asia/Taipei。

## 已修正的可重現問題

1. 舊流程可由 DB picks 補造成功 marker，與渲染結果脫鉤。改為逐次 nightly 身分、必要 stage 成功、DB picks、來源及產物 SHA 的聯合驗證；watchdog 只檢查。
2. 子程序旗標與回傳碼不可靠，optional failure 可能被算成成功。實際 PowerShell 子程序測試涵蓋含空白路徑、旗標、非零結果與 timeout。
3. 午夜發布日與資料日脫鉤。從驗證完成的 marker 傳递 data_date；以官方交易日曆檢查上游資料時效，早晨修復屬於前一晚 operational date。
4. 我新增的 watchlist 驗證器誤把 60 張 margin 卡片算入正式 24 picks，造成前一晚六個 stage 成功但最後驗收失敗。已改為辨識 `pick-` 卡片身分，保留 exact multiset 驗證，並補混合分頁測試。
5. Windows Git 的系統 `core.autocrlf=true` 會在 `git add` 時改變已驗收位元組。已用真實 Git 重現，並對獨立發布副本停用換行及 filter 轉換；測試比對 Git blob 與原檔完全一致。
6. Runtime `render_ticker_full.py` 有既存缺值／KD 修正，未進 Git。已保留 runtime 內容納入版本；另同步 report writer 的 data_date 介面，並加入來源一致性檢查。
7. 真實渲染發現 1452 的 yfinance P/E 為字串 `Infinity`，導致格式化失敗；全快取檢查另找到 2540、3049、3550。現於來源組裝階段將非有限數值／placeholder 標為缺漏，頁面及 dashboard 列出警示，原始快取不改寫。

## 已有驗證

- `tests/test_daily_pipeline.py`：15 tests 通過（2026-09-16）。
- 1452、2540、3049、3550：以真實 DB／快取在獨立目錄成功渲染，修復前的相同輸入會拋出 `ValueError: Unknown format code 'f' for object of type 'str'`。
- 既有 market-screen runner：31 tests 通過（本次修補前段）。
- 最新程式提交 diff whitespace 檢查通過；既有 generated HTML 有空白行，不列入程式修補提交。
- 23 個受管來源 SHA 驗證通過；其中 21 個 runtime mirror，2 個 repo-only margin 腳本。
- 真實 HTTP fixture：任何被選中個股頁面內容舊於 staged release，遠端驗證失敗。
- 真實 Git fixture：即使 `core.autocrlf=true` 及 `.gitattributes` 宣告文字正規化，發布設定仍保存原始位元組。
- 前次真實 1,973 頁的隔離 completion fixture 通過：1,982 個 core artifacts、1,925 fresh、48 個資料缺漏警示、optional degraded=0；這不是 production marker，也不是遠端發布證據。

## 本次完整重跑

- 09:31 的 run `92fe440a26ab416cbf1bc0bc846afbcc`：為修正 Git 位元組問題而明確中止並標為 failed，沒有發布。
- 09:40:27 run `32fd54c84faa412a8783e0305ecdcf39`：200 個結果出現 1 個 render failure，定位無限值資料問題後中止並標 failed，沒有發布。
- 09:55:23 由既有 Windows Scheduler 任務啟動 run `dcdffd71c272421f8d66d0f55fece3ea`（local commit `d64e38d`）。
- `data_date=2026-09-15`、`run_id=16`、24 active picks、OHLCV=1,949 tickers。
- Stage 1 維持率成功：Sep 8–15 共 12,275 筆；Sep 15 為 2,049 筆。
- 待完成：完整 render、patterns、watchlist、marker 驗證、prepare-only release、postflight。

## 邊界與尚未完成

- 全部 source commits 為 local-only；沒有手動推送 GitHub。
- 需完成實際遠端發布及 SHA 驗證，才能宣稱 end-to-end 成功。
- 原有自動 nightly／publisher 排程仍啟用；publish 最多等待 130 分鐘，Scheduler 上限 2 小時 40 分鐘；daily-report 上限 4 小時。
- 48 個非選中股票報價缺漏、7768 quarantine、補充資料抓取問題會顯示為警示，不強制改成綠燈。
- 先前失敗的 Scheduler 結果會保留；手動重跑成功不等於排程曾成功。
- FinMind weekly、Weekly Shareholding 1330、cloudflared 仍為獨立 pending，本次不做 schema migration 或 quarantine 刪除。

## 可攜到其他模組的原則

完成證據包含相同的 run／data identity、實際生成檔案及發布後的 SHA。相同做法可用於 SwingWar Terminal 的資料、策略報告與 UI 更新，避免只靠 rc=0 或 HTTP 200 判定成功。資料缺漏明示，不假設任何特定市場行情。
