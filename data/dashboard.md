# tw-invest-suite Daily Dashboard
**Generated**: 2026-11-06T17:07:34
**OVERALL**: 🟡 WARNING

**Data date**: 2026-11-05
**DB picks**: 24 active; run_id=93
**OHLCV coverage**: 1960 rows ／ 1960 tickers
**Nightly**: 5848fa998acd45a790159c04dffa259a
**Optional degraded**: 0
**Publication**: verified ／ data_date=2026-11-05
**Verified at**: 2026-11-06T17:07:12.486524
**Published commit**: 523f081d5267eb24cdef3987a426cc1ece8220a8

## Action items
- 🟡 26 個股資料不完整，頁面已標示；fresh=1948 ／ rendered=1974
- 🟡 tw-invest-suite-health-check: rc=1; 請見當次檢查明細
- 🟡 tw-invest-suite-publish: rc=1; 請見當次檢查明細

## Cron results
| Task | State | LastRun | RC |
|---|---|---|---|
| tw-invest-suite-daily-report | Ready | 2026-11-05T21:30:30.0000000+08:00 | 0 |
| tw-invest-suite-market-screen | Ready | 2026-11-05T18:20:20.0000000+08:00 | 0 |
| tw-invest-suite-yfinance | Ready | 2026-11-05T22:30:30.0000000+08:00 | 0 |
| tw-invest-suite-health-check | Ready | 2026-11-05T23:00:00.0000000+08:00 | 1 |
| tw-invest-suite-company-refresh | Ready | 2026-11-05T23:25:25.0000000+08:00 | 0 |
| tw-invest-suite-sync-legacy | Ready | 2026-11-05T23:30:30.0000000+08:00 | 0 |
| tw-invest-suite-marker-watchdog | Ready | 2026-11-05T23:55:55.0000000+08:00 | 0 |
| tw-invest-suite-publish | Ready | 2026-11-05T22:50:50.0000000+08:00 | 1 |
| tw-invest-suite-postflight | Ready | 2026-11-06T00:05:05.0000000+08:00 | 0 |

## Scope
- Nightly: analyze pages、watchlist、patterns；日期與 SHA 均由完成標記驗證。
- chips／chips-advanced／sectors／concepts、30 個交易日籌碼歷史、產業與股票 metadata、OG 圖均為每日必要報告，由同一完成標記驗證。
- 雙站 SHA 與 postflight 通過後，自動向現有 Telegram 聊天室傳送籌碼摘要；每日傳送結果另記錄。
- Weekly Shareholding 等任務的實際結果見上方 Cron results；不沿用歷史 PENDING 狀態。
- 未登錄的 legacy FinMind 資料表不列入 canonical 新鮮度認證。
