# D056-3 DB and manual trigger audit

Checked: 2026-09-17 around 14:33–14:40 Asia/Taipei. Read-only DB/API checks; no DB updates, Scheduler mutations, source fixes or Telegram sends in this audit.

## Confirmed

- Certificate UUID `ced12fa357764e81a2f9e5e035ef0b23`, data date 2026-09-16 remains valid: 65 source hashes, 2035 artifacts, 50 all-report artifacts, 1974 rendered tickers, 1926 fresh quotes, 30 history dates, no degraded stages.
- Latest daily table: 1949 rows, no empty/corrupted company names, issued-share coverage 1949/1949, no negative volumes/margin balances, no out-of-range foreign ownership ratios. Buy minus sell matches each institutional net, and their sum matches ThreeNet. Positive-close, positive-volume rows have no OHLC interval violations.
- Aug05–Sep16 history: 58743 rows across 30 dates, no duplicate ticker/date groups, no missing foreign/trust/dealer net fields. Latest five sessions each contain 1949 rows.
- Canonical margin-maintenance table: latest trade date 2026-09-16, 2046 rows. Registry has 10 dataset entries targeting daily_data2_full and finmind_taiwan_margin_maintenance. Database contains 240 tables; this audit does not establish correctness of all legacy/experimental tables.
- 7768 quarantine: 13 retained events, zero open.
- Actual daily-report task: S4U, WakeToRun and StartWhenAvailable enabled, last result 0, next scheduled run Sep17 22:25. Publisher: same settings, last result 1, next Sep18 00:30. Groove recovery is running, origin/tunnel healthy, but its older origin has not loaded the stock header patch.
- Existing manual report/publish entries and their installed Scheduler actions are present. They have already been executed in the recovered daily run; no new manual trigger was issued during this audit. Starting the pair regenerates the latest landed DB data, not every independent downloader.

## New DB/source discrepancy requiring resolution

One bounded FinMind TaiwanStockPrice request for Sep16 returned 46849 market/instrument rows. All 23 DB zero-close tickers matched provider zero closes; 21 also matched volume. Two did not:

| Ticker | DB volume (shares) | FinMind volume (shares) | TWSE STOCK_DAY volume (shares) | Official OHLC |
|---|---:|---:|---:|---|
| 1423 | 347 | 10347 | 10347 | -- / -- / -- / -- |
| 1541 | 0 | 8000 | 8000 | -- / -- / -- / -- |

Both official monthly responses were HTTP200/stat OK with the exact `115/09/16` row. Default Python certificate validation failed for these TWSE requests; the final successful read used the project's existing TWSE transport. No transport/source code was changed.

Official sources:

- [TWSE 1423 September data](https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date=20260901&stockNo=1423)
- [TWSE 1541 September data](https://www.twse.com.tw/exchangeReport/STOCK_DAY?response=json&date=20260901&stockNo=1541)
- [TWSE trading system](https://www.twse.com.tw/zh/products/system/trading.html): odd-lot execution prices do not establish the daily regular-session OHLC. This explains why positive share volume alone does not prove a missing regular close is a parser defect; it does not establish the trade types of each exception.

Trace the existing normal writer (`strategy_lab/_fetch_today.py` → `strategy_lab.finmind_batch_update`, price phase) and competing writers/revision timing before repair. The existing price upsert updates OHLC and volume together. Do not invent a closing price or perform an unaudited direct SQL patch. Repair through the approved normal entrypoint, verify date/ticker/count/source values, then regenerate and recertify affected reports before publishing a repaired snapshot. The previous assumption that no report rerun would be needed applies only to the response-header repair, not to a DB repair.

## Remaining acceptance

1. Resolve and revalidate the two DB/source volume discrepancies; audit remaining canonical data lanes separately from unregistered legacy tables.
2. Explicit authorization to reopen the canceled Windows UAC origin reload, followed by actual local no-transform header and Groove remote raw-SHA equality.
3. Formal publisher result0 with matching GitHub Pages/Groove/postflight receipts and actual Telegram API ok/message_id/matching configured chat. Telegram is still unsent.
4. Full remote route/feature acceptance and precise wake evidence; physical sleep wake remains untested.

Do not mark the overall goal complete from the still-valid older report certificate or canonical-only postflight.
