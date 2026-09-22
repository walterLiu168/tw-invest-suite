# tw-invest-suite Daily Dashboard
**Generated**: 2026-09-22T15:29:22
**OVERALL**: 🟡 WARNING

**Data date**: 2026-09-21
**DB picks**: 24 active; run_id=28
**OHLCV coverage**: 1964 rows ／ 1964 tickers
**Nightly**: c833f72da1b74239a41d7619431ae2b7
**Optional degraded**: 0
**Publication**: verified ／ data_date=2026-09-21
**Verified at**: 2026-09-22T15:28:59.242248
**Published commit**: cc9214d4663a7b65de16dd03451e4d74e010d96a

## Action items
- 🟡 26 個股資料不完整，頁面已標示；fresh=1948 ／ rendered=1974
- 🟡 5 個 watchlist ticker 補充資料不完整；各卡片列出失敗來源
- 🟡 6 個股的估值／基本面來源含無效數值，已標為缺漏並在頁面警示

## Cron results
| Task | State | LastRun | RC |
|---|---|---|---|
| tw-invest-suite-daily-report | Ready | 2026-09-22T14:22:22.0000000+08:00 | 0 |
| tw-invest-suite-market-screen | Ready | 2026-09-22T08:26:26.0000000+08:00 | 0 |
| tw-invest-suite-yfinance | Ready | 2026-09-21T22:30:30.0000000+08:00 | 0 |
| tw-invest-suite-health-check | Ready | 2026-09-22T08:26:26.0000000+08:00 | 0 |
| tw-invest-suite-company-refresh | Ready | 2026-09-21T23:25:25.0000000+08:00 | 0 |
| tw-invest-suite-sync-legacy | Ready | 2026-09-21T23:30:30.0000000+08:00 | 0 |
| tw-invest-suite-marker-watchdog | Ready | 2026-09-22T13:16:16.0000000+08:00 | 0 |
| tw-invest-suite-publish | Running | 2026-09-22T15:21:21.0000000+08:00 | 267009 |
| tw-invest-suite-postflight | Ready | 2026-09-22T15:20:20.0000000+08:00 | 0 |

## Scope
- Nightly: analyze pages、watchlist、patterns；日期與 SHA 均由完成標記驗證。
- chips／chips-advanced／sectors／concepts、30 個交易日籌碼歷史、產業與股票 metadata、OG 圖均為每日必要報告，由同一完成標記驗證。
- 雙站 SHA 與 postflight 通過後，自動向現有 Telegram 聊天室傳送籌碼摘要；每日傳送結果另記錄。
- Weekly Shareholding 等任務的實際結果見上方 Cron results；不沿用歷史 PENDING 狀態。
- 未登錄的 legacy FinMind 資料表不列入 canonical 新鮮度認證。
