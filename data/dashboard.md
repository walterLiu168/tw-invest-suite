# tw-invest-suite Daily Dashboard
**Generated**: 2026-10-04T01:10:09
**OVERALL**: 🟡 WARNING

**Data date**: 2026-10-02
**DB picks**: 24 active; run_id=49
**OHLCV coverage**: 1960 rows ／ 1960 tickers
**Nightly**: UNVERIFIED
**Optional degraded**: ?
**Publication**: verified ／ data_date=2026-10-02
**Verified at**: 2026-10-04T01:06:38.599424
**Published commit**: 10046389f806fd62c1d5f3bcab726f67208ea1ca

## Action items
- 🟡 nightly 執行中，等待完成
- 🟡 tw-invest-suite-yfinance: rc=2; 請見當次檢查明細
- 🟡 本次 GitHub Pages 發布尚未驗證；HTTP 200 不等於資料已更新

## Cron results
| Task | State | LastRun | RC |
|---|---|---|---|
| tw-invest-suite-daily-report | Ready | 2026-10-03T22:25:25.0000000+08:00 | 0 |
| tw-invest-suite-market-screen | Ready | 2026-10-03T18:20:20.0000000+08:00 | 0 |
| tw-invest-suite-yfinance | Ready | 2026-10-03T22:30:30.0000000+08:00 | 2 |
| tw-invest-suite-health-check | Ready | 2026-10-03T23:00:00.0000000+08:00 | 0 |
| tw-invest-suite-company-refresh | Ready | 2026-10-03T23:25:25.0000000+08:00 | 0 |
| tw-invest-suite-sync-legacy | Ready | 2026-10-03T23:30:30.0000000+08:00 | 0 |
| tw-invest-suite-marker-watchdog | Ready | 2026-10-03T23:55:55.0000000+08:00 | 0 |
| tw-invest-suite-publish | Running | 2026-10-04T00:30:30.0000000+08:00 | 267009 |
| tw-invest-suite-postflight | Ready | 2026-10-04T00:05:05.0000000+08:00 | 0 |

## Scope
- Nightly: analyze pages、watchlist、patterns；日期與 SHA 均由完成標記驗證。
- chips／chips-advanced／sectors／concepts、30 個交易日籌碼歷史、產業與股票 metadata、OG 圖均為每日必要報告，由同一完成標記驗證。
- 雙站 SHA 與 postflight 通過後，自動向現有 Telegram 聊天室傳送籌碼摘要；每日傳送結果另記錄。
- Weekly Shareholding 等任務的實際結果見上方 Cron results；不沿用歷史 PENDING 狀態。
- 未登錄的 legacy FinMind 資料表不列入 canonical 新鮮度認證。
