# D052d: 18:05 recurring metadata_backfill cron

> **Submitted**: 2026-09-05 by Mavis
> **Target**: scripts/metadata_backfill.py + Task Scheduler
> **Status**: ✅ cron registered + tested
> **Scope**: cron | scripts

## What

Daily 18:05 cron that:
1. Scans `daily_data2_full` latest date for tickers missing from `industry_type`
2. If any, calls `metadata_backfill.py --batch=<missing tickers>` with the list
3. If none, exits cleanly

This is the recurring version of D052c. Per-event fingerprint dedup
(added in D052c-fixup2) ensures the same ticker+source_date+reason
won't be re-inserted into `metadata_quarantine` on a no-change re-run.

## Why 18:05 (per ChatGPT F7)

- 17:35 + 17:55: OpenAlice Daily OHLCV landing
- **18:05**: metadata backfill (this cron)
- 22:25: daily-report (renders HTML for the now-in-industry_type tickers)

So newly listed tickers get a row in `industry_type` 4 hours before
the daily run picks them up to render.

## Files

| Path | Purpose |
|---|---|
| `scripts/metadata_backfill.py` | (D052c) stage + promote + quarantine engine |
| `scripts/metadata_backfill_daily.ps1` | (D052d) PS1 wrapper — scans DB, calls python |
| `scripts/_register_metadata_backfill.xml` | Task Scheduler registration XML |

## Cron

- Task name: `\tw-invest-suite-metadata-backfill`
- Schedule: daily 18:05
- Timeout: 10 min
- First run: 2026-09-05 18:05

## Tested manually

Test run on 2026-09-05 14:47:
- Scanned DB, found 7768 missing
- Called metadata_backfill.py --batch=7768
- 7768 → quarantine (multi-category 半導體業 vs 電子工業)
- metadata_staging +2 audit rows
- open quarantine: 1 → 2 (1 new for 9/5, 1 existing for 9/4)

## Design notes

- **Path strategy**: this .ps1 lives in BOTH git repo and runtime
  (`C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\`). Used
  absolute path to git repo for the python script so the cron works
  without manual file copy.
- **Per-day new event**: 7768 will get a new quarantine row per day
  (different `source_date`). When Walter resolves one, all open rows
  for 7768 stay open. Future improvement: a "dedup by ticker across
  recent days" pass, but not in this scope.
- **Skip-when-empty**: if no missing tickers, exits with code 0 and a
  log line, no python invocation.

## Out of scope (per Walter's 選 1 + D052 review)

- ❌ Auto-resolution of 7768 (Walter manual)
- ❌ Auto-render of new tickers' HTML (relies on 22:25 daily-report)
- ❌ Slack/Telegram alerts (D052e)
- ❌ 1,955 historical NULL company rows in pre-4/29 era (D052f does last 4 months)

## Verification

```bash
# 1. check cron
schtasks /Query /TN '\tw-invest-suite-metadata-backfill'

# 2. test manually
C:\Users\icemo\Projects\tw-invest-suite\scripts\metadata_backfill_daily.ps1

# 3. state check
python -c "import pymysql; c=pymysql.connect(host='localhost',user='root',password='1234',database='tw_elec'); cur=c.cursor(); cur.execute('SELECT COUNT(*) FROM industry_type'); print('industry_type:', cur.fetchone()[0]); cur.execute('SELECT COUNT(*) FROM metadata_quarantine WHERE resolved_at IS NULL'); print('open quarantine:', cur.fetchone()[0])"
```

## Status

✅ D052d ready. Next: nightly 18:05 cron will run automatically. Pending
D052e (alerts) and Walter's 7768 lookup.
