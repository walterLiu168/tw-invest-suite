# tw-invest-suite Daily Dashboard
**Generated**: 2026-09-22T13:13:57
**OVERALL**: 🔴 CRITICAL

**Data date**: 2026-09-21
**DB picks**: 24 active; run_id=28
**OHLCV coverage**: 1964 rows ／ 1964 tickers
**Nightly**: d26467b5f9f04e89984b79131182a11e
**Optional degraded**: 0
**Publication**: verified ／ data_date=2026-09-21
**Verified at**: 2026-09-22T13:13:36.670190
**Published commit**: 704bc1f96de5475cad3f71701d896e60b845024e

## Action items
- 🟡 26 個股資料不完整，頁面已標示；fresh=1948 ／ rendered=1974
- 🟡 5 個 watchlist ticker 補充資料不完整；各卡片列出失敗來源
- 🟡 6 個股的估值／基本面來源含無效數值，已標為缺漏並在頁面警示
- 🔴 tw-invest-suite-daily-report: rc=1; 請見當次檢查明細
- 🟡 tw-invest-suite-marker-watchdog: rc=1; 請見當次檢查明細
- 🟡 tw-invest-suite-postflight: rc=1; 請見當次檢查明細
- 🔴 本次 postflight 未通過

## Cron results
| Task | State | LastRun | RC |
|---|---|---|---|
| tw-invest-suite-daily-report | Ready | 2026-09-21T22:25:25.0000000+08:00 | 1 |
| tw-invest-suite-market-screen | Ready | 2026-09-22T08:26:26.0000000+08:00 | 0 |
| tw-invest-suite-yfinance | Ready | 2026-09-21T22:30:30.0000000+08:00 | 0 |
| tw-invest-suite-health-check | Ready | 2026-09-22T08:26:26.0000000+08:00 | 0 |
| tw-invest-suite-company-refresh | Ready | 2026-09-21T23:25:25.0000000+08:00 | 0 |
| tw-invest-suite-sync-legacy | Ready | 2026-09-21T23:30:30.0000000+08:00 | 0 |
| tw-invest-suite-marker-watchdog | Ready | 2026-09-21T23:55:55.0000000+08:00 | 1 |
| tw-invest-suite-publish | Running | 2026-09-22T13:05:05.0000000+08:00 | 267009 |
| tw-invest-suite-postflight | Ready | 2026-09-22T00:05:05.0000000+08:00 | 1 |

## Scope
- Nightly: analyze pages、watchlist、patterns；日期與 SHA 均由完成標記驗證。
- chips／chips-advanced／sectors／concepts、30 個交易日籌碼歷史、產業與股票 metadata、OG 圖均為每日必要報告，由同一完成標記驗證。
- 雙站 SHA 與 postflight 通過後，自動向現有 Telegram 聊天室傳送籌碼摘要；每日傳送結果另記錄。
- Weekly Shareholding 等任務的實際結果見上方 Cron results；不沿用歷史 PENDING 狀態。
- 未登錄的 legacy FinMind 資料表不列入 canonical 新鮮度認證。
