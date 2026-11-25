# tw-invest-suite Daily Dashboard
**Generated**: 2026-11-25T09:07:40
**OVERALL**: 🟡 WARNING

**Data date**: 2026-11-24
**DB picks**: 24 active; run_id=125
**OHLCV coverage**: 1963 rows ／ 1963 tickers
**Nightly**: 4bfce1025dfa4e4f9e24f41994610e6a
**Optional degraded**: 0
**Publication**: verified ／ data_date=2026-11-24
**Verified at**: 2026-11-25T09:07:19.514609
**Published commit**: a8db9df9592e6a5a691d0e95440e36329a75896b

## Action items
- 🟡 18 個股資料不完整，頁面已標示；fresh=1956 ／ rendered=1974

## Cron results
| Task | State | LastRun | RC |
|---|---|---|---|
| tw-invest-suite-daily-report | Ready | 2026-11-24T21:30:30.0000000+08:00 | 0 |
| tw-invest-suite-market-screen | Ready | 2026-11-24T18:20:20.0000000+08:00 | 0 |
| tw-invest-suite-yfinance | Ready | 2026-11-24T22:30:30.0000000+08:00 | 0 |
| tw-invest-suite-health-check | Ready | 2026-11-24T23:00:00.0000000+08:00 | 0 |
| tw-invest-suite-company-refresh | Ready | 2026-11-24T23:25:25.0000000+08:00 | 0 |
| tw-invest-suite-sync-legacy | Ready | 2026-11-24T23:30:30.0000000+08:00 | 0 |
| tw-invest-suite-marker-watchdog | Ready | 2026-11-24T23:55:55.0000000+08:00 | 0 |
| tw-invest-suite-publish | Ready | 2026-11-24T22:50:50.0000000+08:00 | 0 |
| tw-invest-suite-postflight | Ready | 2026-11-25T00:05:05.0000000+08:00 | 0 |

## Scope
- Nightly: analyze pages、watchlist、patterns；日期與 SHA 均由完成標記驗證。
- chips／chips-advanced／sectors／concepts、30 個交易日籌碼歷史、產業與股票 metadata、OG 圖均為每日必要報告，由同一完成標記驗證。
- 雙站 SHA 與 postflight 通過後，自動向現有 Telegram 聊天室傳送籌碼摘要；每日傳送結果另記錄。
- Weekly Shareholding 等任務的實際結果見上方 Cron results；不沿用歷史 PENDING 狀態。
- 未登錄的 legacy FinMind 資料表不列入 canonical 新鮮度認證。
