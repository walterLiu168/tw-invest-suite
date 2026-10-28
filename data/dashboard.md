# tw-invest-suite Daily Dashboard
**Generated**: 2026-10-28T15:07:18
**OVERALL**: 🟡 WARNING

**Data date**: 2026-10-27
**DB picks**: 24 active; run_id=78
**OHLCV coverage**: 1964 rows ／ 1964 tickers
**Nightly**: c000946f1b3d45a1a05dba53c5d53bd7
**Optional degraded**: 0
**Publication**: verified ／ data_date=2026-10-27
**Verified at**: 2026-10-28T15:06:55.642502
**Published commit**: 35ca85da8f6db6a638f199062b0067b33e2801e1

## Action items
- 🟡 35 個股資料不完整，頁面已標示；fresh=1939 ／ rendered=1974
- 🟡 tw-invest-suite-health-check: rc=1; 請見當次檢查明細
- 🟡 tw-invest-suite-publish: rc=1; 請見當次檢查明細

## Cron results
| Task | State | LastRun | RC |
|---|---|---|---|
| tw-invest-suite-daily-report | Ready | 2026-10-27T21:30:30.0000000+08:00 | 0 |
| tw-invest-suite-market-screen | Ready | 2026-10-27T18:20:20.0000000+08:00 | 0 |
| tw-invest-suite-yfinance | Ready | 2026-10-27T22:30:30.0000000+08:00 | 0 |
| tw-invest-suite-health-check | Ready | 2026-10-27T23:00:00.0000000+08:00 | 1 |
| tw-invest-suite-company-refresh | Ready | 2026-10-27T23:25:25.0000000+08:00 | 0 |
| tw-invest-suite-sync-legacy | Ready | 2026-10-27T23:30:30.0000000+08:00 | 0 |
| tw-invest-suite-marker-watchdog | Ready | 2026-10-27T23:55:55.0000000+08:00 | 0 |
| tw-invest-suite-publish | Ready | 2026-10-27T22:50:50.0000000+08:00 | 1 |
| tw-invest-suite-postflight | Ready | 2026-10-28T00:05:05.0000000+08:00 | 0 |

## Scope
- Nightly: analyze pages、watchlist、patterns；日期與 SHA 均由完成標記驗證。
- chips／chips-advanced／sectors／concepts、30 個交易日籌碼歷史、產業與股票 metadata、OG 圖均為每日必要報告，由同一完成標記驗證。
- 雙站 SHA 與 postflight 通過後，自動向現有 Telegram 聊天室傳送籌碼摘要；每日傳送結果另記錄。
- Weekly Shareholding 等任務的實際結果見上方 Cron results；不沿用歷史 PENDING 狀態。
- 未登錄的 legacy FinMind 資料表不列入 canonical 新鮮度認證。
