# 驗收修正與 MiniMax 維護交接 — 2026-10-16

## 本次結論

21:02 Asia/Taipei 的只讀驗收目標為 2026-10-15，結果 DEGRADED。
先前 HEALTHY 不能當作全鏈完成的充分證據：驗收器存在漏驗，這次已修正部分入口。
未重跑 nightly、未發布、未重送 Telegram、未更動 Task Scheduler 或認證 marker。

## 已修正並同步 source/runtime

- scripts/daily_chain_audit.py：canonical gate 依目標日期選取並檢查內容日期；四份報告必須為指定檔名且非空。
- Telegram：message_id 必須為正整數，排除 bool/string；收據日期與 nightly_id 必須吻合 marker；以 date:chat_hash 精確核對 ledger 的訊息編號、內容摘要及批次。
- 發布：缺失或錯批次 postflight 不再通過；核對 manifest、all_reports、Groove 收據的日期與批次；缺少 artifact SHA 不再略過。
- 排程或 wake timer 證據不可讀時列為未驗證。
- 模型：依驗收目標日期判斷新鮮度；今日價格先更新，不應將已涵蓋昨日目標的預測判為過期。
- scripts/certification_catchup_guard.ps1：確認官方目標日期；補查交付證據才回報 ALREADY_DELIVERED；publication 缺失時仍可走 publish-only；避開活躍 nightly；發布返回成功後再驗交付。

## 驗證

- C:\Python314\python.exe -m pytest tests/test_daily_chain_audit.py -q：14 passed。
- PowerShell AST parser：無語法錯誤。
- 單獨執行 guard 的只讀 Test-Delivery 函式，目標 2026-10-15 返回 False，正確攔住當前不完整交付；未執行整支會產生副作用的 guard。
- 實際 --no-notify audit：DEGRADED；詳見 C:\Groove-Lab\automation\audit\latest.json 與 history。
- source/runtime 的兩個修改檔案已同步。兩檔不在 pipeline_state.SOURCE_FILES，未改寫現有認證來源雜湊。

## 已確認但尚未完成的問題

1. C:\Groove-Lab\watchlist.html 與 10/15 manifest 不符。預期 SHA256 為 04b713ea19df65a443fb43ecf5fe25af2b8576e556e5d9b0db845216e86c0b19；實際為 67379d8ffe44da574c64584c1b59a4719bfcc38b916e9659e16f1aa3785aab7e。
   repo/public/watchlist.html 仍吻合認證版本。news_refresh_watchlist.py 呼叫 render_full_watchlist.py --groove-only，後者直接覆寫已認證的 Groove watchlist.html；這是即時新聞與不可變發布共用路徑的設計衝突。勿盲目還原而抹除即時新聞，也勿更新舊 manifest 掩蓋差異。下一個完整發布應將即時新聞頁與認證頁分開，或建立明確獨立的新聞版本與驗證契約。
2. powercfg 喚醒證據本次無法讀取；不能據此聲稱自動睡眠喚醒已實測成功。設定、可讀性、實際喚醒事件須分開驗證。
3. daily_certification_catchup.py 本身的 certified_for 還未補齊 Groove/Telegram 契約；本次 guard 增強不等於其他直接呼叫入口都已修正。該 Python 檔在認證來源清單內，改動後必須正常重建認證，不能偽造 marker。
4. AI owner 的早晨排程日期、waiting_provider 前置條件返回路徑、日曆請求頻率，以及來源完整雜湊驗證，尚未在本次重新驗證，不能宣稱無 bug。
5. 同資料日重建時，chip_push.py 的 already_sent 分支會以新 nightly_id 包裝舊 ledger 收據；新驗收會將其列為不一致。修復需保留原始發送身份及明確重用關係，不能修改歷史 ledger 或重送以讓驗收變綠。

## 給 MiniMax 的接手提示

先讀這份文件與現有未提交修改。維護 source C:\Users\icemo\Projects\tw-invest-suite 與 runtime C:\Users\icemo\.claude\skills\tw-invest-suite\scripts；AI canonical 專案是 D:\CODEX\AI-Telegram。
先處理上述未完成項目並建立失敗案例。保留新聞更新功能，同時確保已認證版本可重現。任何聲稱完成都要附同資料日、nightly_id、run_id 的 DB、檔案與遠端證據。保留原始 Telegram ledger；不因不一致而盲目重送。不重啟健康 owner，不偽造零值、日期或認證收據。自動執行應由現有 Windows 排程持續負責，不能依賴 AI 開始工作。
