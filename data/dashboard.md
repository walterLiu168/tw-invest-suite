# tw-invest-suite Daily Dashboard
**Generated**: 2026-09-16T15:48:22
**OVERALL**: 🔴 CRITICAL

**Data date**: 2026-09-15
**DB picks**: 24 active; run_id=16
**OHLCV coverage**: 1949 rows ／ 1949 tickers
**Nightly**: 8fc014692c224162a591b2c70052ec29
**Optional degraded**: 0
**Publication**: verified ／ data_date=2026-09-15
**Verified at**: 2026-09-16T15:48:13.782449
**Published commit**: cb00e3b4b0232bb1e0e483e78a86dcc7d6713121

## Action items
- 🟡 48 個股資料不完整，頁面已標示；fresh=1925 ／ rendered=1973
- 🟡 5 個 watchlist ticker 補充資料不完整；各卡片列出失敗來源
- 🟡 4 個股的估值／基本面來源含無效數值，已標為缺漏並在頁面警示
- 🔴 Scheduler query failed
- 🟡 Quarantine 7768: 12 open; PENDING J 需處理，未自動豁免新增列
- 🔴 本次 postflight 未通過

## Cron results
| Task | State | LastRun | RC |
|---|---|---|---|

## Scope
- Nightly: analyze pages、watchlist、patterns；日期與 SHA 均由完成標記驗證。
- chips／sectors／concepts 為手動更新頁面，未列為每日更新成功證據。
- FinMind weekly、Weekly Shareholding 1330、cloudflared：保留 PENDING，未宣稱已修復。
