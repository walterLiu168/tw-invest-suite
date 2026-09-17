# tw-invest-suite Daily Dashboard
**Generated**: 2026-09-17T00:05:13
**OVERALL**: 🔴 CRITICAL

**Data date**: 2026-09-16
**DB picks**: 24 active; run_id=17
**OHLCV coverage**: 1949 rows ／ 1949 tickers
**Nightly**: UNVERIFIED
**Optional degraded**: ?
**Publication**: verified ／ data_date=2026-09-15
**Verified at**: 2026-09-16T15:48:13.782449
**Published commit**: cb00e3b4b0232bb1e0e483e78a86dcc7d6713121

## Action items
- 🔴 nightly is incomplete/failed or marker belongs to another run
- 🔴 tw-invest-suite-daily-report: rc=1; 請見當次檢查明細
- 🟡 tw-invest-suite-health-check: rc=1; 請見當次檢查明細
- 🟡 tw-invest-suite-marker-watchdog: rc=1; 請見當次檢查明細
- 🟡 tw-invest-suite-publish: rc=267014; 請見當次檢查明細
- 🔴 本次 nightly 尚無有效完成證據
- 🟡 本次 GitHub Pages 發布尚未驗證；HTTP 200 不等於資料已更新

## Cron results
| Task | State | LastRun | RC |
|---|---|---|---|
| tw-invest-suite-daily-report | Ready | 2026-09-16T22:25:25.0000000+08:00 | 1 |
| tw-invest-suite-market-screen | Ready | 2026-09-16T20:58:58.0000000+08:00 | 0 |
| tw-invest-suite-yfinance | Ready | 2026-09-16T22:30:30.0000000+08:00 | 0 |
| tw-invest-suite-health-check | Ready | 2026-09-16T23:00:00.0000000+08:00 | 1 |
| tw-invest-suite-company-refresh | Ready | 2026-09-16T23:25:25.0000000+08:00 | 0 |
| tw-invest-suite-sync-legacy | Ready | 2026-09-16T23:30:30.0000000+08:00 | 0 |
| tw-invest-suite-marker-watchdog | Ready | 2026-09-16T23:55:55.0000000+08:00 | 1 |
| tw-invest-suite-publish | Ready | 2026-09-16T21:21:21.0000000+08:00 | 267014 |
| tw-invest-suite-postflight | Running | 2026-09-17T00:05:05.0000000+08:00 | 267009 |

## Scope
- Nightly: analyze pages、watchlist、patterns；日期與 SHA 均由完成標記驗證。
- chips／sectors／concepts 為手動更新頁面，未列為每日更新成功證據。
- FinMind weekly、Weekly Shareholding 1330、cloudflared：保留 PENDING，未宣稱已修復。
