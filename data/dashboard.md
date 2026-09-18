# tw-invest-suite Daily Dashboard
**Generated**: 2026-09-18T17:07:20
**OVERALL**: 🟡 WARNING

**Data date**: 2026-09-17
**DB picks**: 24 active; run_id=19
**OHLCV coverage**: 1958 rows ／ 1958 tickers
**Nightly**: d672ae59becb417ba9c075cd7928e0e7
**Optional degraded**: 0
**Publication**: verified ／ data_date=2026-09-17
**Verified at**: 2026-09-18T17:06:55.545847
**Published commit**: 43690e927db915c363d450c7d39e73d51b7d93c4

## Action items
- 🟡 38 個股資料不完整，頁面已標示；fresh=1936 ／ rendered=1974
- 🟡 5 個股的估值／基本面來源含無效數值，已標為缺漏並在頁面警示
- 🟡 tw-invest-suite-marker-watchdog: rc=1; 請見當次檢查明細
- 🟡 tw-invest-suite-postflight: rc=1; 請見當次檢查明細

## Cron results
| Task | State | LastRun | RC |
|---|---|---|---|
| tw-invest-suite-daily-report | Ready | 2026-09-18T16:03:03.0000000+08:00 | 0 |
| tw-invest-suite-market-screen | Ready | 2026-09-18T09:15:15.0000000+08:00 | 0 |
| tw-invest-suite-yfinance | Ready | 2026-09-17T22:30:30.0000000+08:00 | 0 |
| tw-invest-suite-health-check | Ready | 2026-09-18T16:00:00.0000000+08:00 | 0 |
| tw-invest-suite-company-refresh | Ready | 2026-09-18T07:06:06.0000000+08:00 | 0 |
| tw-invest-suite-sync-legacy | Ready | 2026-09-18T07:15:15.0000000+08:00 | 0 |
| tw-invest-suite-marker-watchdog | Ready | 2026-09-18T16:02:02.0000000+08:00 | 1 |
| tw-invest-suite-publish | Running | 2026-09-18T16:59:59.0000000+08:00 | 267009 |
| tw-invest-suite-postflight | Ready | 2026-09-18T00:05:05.0000000+08:00 | 1 |

## Scope
- Nightly: analyze pages、watchlist、patterns；日期與 SHA 均由完成標記驗證。
- chips／chips-advanced／sectors／concepts、30 個交易日籌碼歷史、產業與股票 metadata、OG 圖均為每日必要報告，由同一完成標記驗證。
- 雙站 SHA 與 postflight 通過後，自動向現有 Telegram 聊天室傳送籌碼摘要；每日傳送結果另記錄。
- Weekly Shareholding 等任務的實際結果見上方 Cron results；不沿用歷史 PENDING 狀態。
- 未登錄的 legacy FinMind 資料表不列入 canonical 新鮮度認證。
