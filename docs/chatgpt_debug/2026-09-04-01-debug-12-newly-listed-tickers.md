# Debug: 12 個新上市 ticker 在 `industry_type` 缺資料

> **Submitted**: 2026-09-04 by Mavis (debug run on user request)
> **Target**: industry_type, stock_info, stock_names, shares_master, daily_data2_full
> **Status**: pending (awaiting ChatGPT review / fix decision)
> **Scope**: db

## Context

User flagged that 12 newly listed tickers are missing company names in `analyze/<ticker>.html` pages. Trace back:

- `analyze/<ticker>.html` reads `daily_data2_full.company` → `industry_type.company` via JOIN
- `daily_data2_full.company` is filled by `_daily_backfill.py` from `industry_type.company`
- 12 tickers were silently skipped because they are NOT in `industry_type`

The 12 tickers: `3485 敘豐 / 4195 基米-創 / 4582 聚恆-創 / 6945 圓祥生技 / 6983 華洋精機 / 7768 頌勝科技 / 7772 耀穎 / 7803 雲象科技-創 / 7818 溢泰實業 / 7819 精誠金融 / 7827 漢康-KY創 / 7842 天能綠電`

## Findings

### F1. `industry_type` is stale — last updated 2026-04-29 21:04
- File: `industry_type` table (1,962 rows, range 1101..9962)
- Evidence: `SHOW TABLE STATUS` → `Update_time = 2026-04-29 21:04:05`
- Adjacent ticker gap check shows the 12 are cleanly between existing rows (e.g. 3483/3484 neighbors but 3485 missing, 4581/4583 neighbors but 4582 missing, 7820/7821 neighbors but 7818/7819/7827 missing, 7842 has no neighbors at all — likely the newest).
- This means these 12 are real newly-listed tickers since 2026-04-29, not bad data.

### F2. All 3 local "master" tables also missing the 12
Coverage test (12/12 expected, found N):
| Table | Has the 12? | Has `Ticker`? | Has `Name`? | Has `Industry`? | Has `ListedDate`? |
|---|---|---|---|---|---|
| `industry_type` | 0/12 | ✓ | ✓ | ✓ | ✗ (no col) |
| `stock_info` | 0/12 | ✓ | ✓ | ✓ | ✓ |
| `stock_names` | 0/12 | ✓ | ✓ | ✓ | ✓ |
| `shares_master` | 0/12 | ✓ | ✓ | ✗ | ✗ (only shares) |

Implication: NO local source can supply the 12 names. Must fetch externally.

### F3. `daily_data2_full` HAS the 12 (latest = 9/3 close)
All 12 hit on every trading day from 8/27 → 9/3 (6 days, 12 hits each). They are real, actively trading, OHLCV in DB. Only the metadata is missing.

### F4. FinMind `TaiwanStockInfo` returns 12/12 (verified live)
Single API call (`https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockInfo&token=...`, sponsor tier, 0.4s response, 4,319 rows total):

| ticker | name | industry_category |
|---|---|---|
| 3485 | 敘豐 | 電子零組件業 |
| 4195 | 基米-創 | 生技醫療業 |
| 4582 | 聚恆-創 | 綠能環保 |
| 6945 | 圓祥生技 | 生技醫療業 |
| 6983 | 華洋精機 | 其他電子類 |
| 7768 | 頌勝科技 | 電子工業 |
| 7772 | 耀穎 | 半導體業 |
| 7803 | 雲象科技-創 | 生技醫療業 |
| 7818 | 溢泰實業 | 綠能環保 |
| 7819 | 精誠金融 | 資訊服務業 |
| 7827 | 漢康-KY創 | 生技醫療業 |
| 7842 | 天能綠電 | 綠能環保類 |

All 12 confirmed trade (type: `tpex` or `twse`).

## Out of Scope
- Not investigating the other 2,628 tickers in `daily_data2_full` (all presumably already in `industry_type`).
- Not investigating why `industry_type` last_updated is 2026-04-29 (could be: no auto-backfill cron, manual refresh skipped, etc.).
- Not testing TWSE/TPEx OpenAPI directly — SSL cert verify fails on this Windows Python (`Missing Subject Key Identifier`). FinMind is the only verified-working source.

## Proposed Fix (for ChatGPT to review)

1. **Backfill the 12 into `industry_type`** (immediate):
   - INSERT INTO industry_type (ticker, company, industry, last_updated) VALUES (...) with FinMind `TaiwanStockInfo` rows for the 12
   - Run `python src/_daily_backfill.py` to re-fill `daily_data2_full.company` for these 12
   - Re-render `analyze/<ticker>.html` for the 12 tickers

2. **Add a recurring backfill** (prevent recurrence):
   - New cron: `tw-invest-suite-industry-backfill` at 17:30 (after OpenAlice 17:25 daily close)
   - Pulls full `TaiwanStockInfo` from FinMind (~4,319 rows, <1s)
   - INSERT...ON DUPLICATE KEY UPDATE for industry_type (idempotent)
   - Then triggers `daily_data2_full.company` re-fill for newly added tickers
   - Should also detect: "ticker in daily_data2_full but not in industry_type" → alert

3. **Optionally fix the 3 other tables** (stock_info, stock_names, shares_master):
   - Decide which is the master; rest mirror from it
   - For now, only `industry_type` matters for the analyze/ HTML rendering pipeline

## Questions for ChatGPT

1. Should the new cron go at 17:30 (right after daily close) or earlier (e.g. 09:00 before market opens)?
2. Should we add a Slack/Telegram alert when a new ticker is detected in `daily_data2_full` but missing from `industry_type`?
3. Is `industry_type` the right master, or should we promote `stock_info` (which has ListedDate) to be the canonical table?
4. Should the recurring backfill be "full refresh" (4,319 rows) or "diff only" (last 7 days of `TaiwanStockInfo.date`)?

## Status

*(Mavis will append implementation after ChatGPT review)*
