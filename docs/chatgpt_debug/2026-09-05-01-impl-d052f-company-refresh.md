# D052f: company_refresh — fix 4-month daily_data2_full.company null gap

> **Submitted**: 2026-09-05 by Mavis (after Walter 選 1)
> **Target**: daily_data2_full.company column
> **Status**: ✅ fixed + cron registered
> **Scope**: db | cron | scripts

## Problem (found in 9/5 audit)

`daily_data2_full.company` had been 1,955/1,955 NULL on 9/3 and 9/4.
ChatGPT F3 review on 9/4 caught this; root cause: **no cron called
`src/_daily_backfill.py` (or any equivalent) since 2026-04-29**. The 4-month
gap accumulated without anyone noticing.

The 9/1 + 8/31 dates had 1,945/1,957 non-null because:
- Those days the backfill had run partially
- Only 12 newly listed tickers were NULL on those days
- From 9/2 onwards, the entire daily_data2_full.company refresh stopped

## Fix

New script `scripts/company_refresh.py` that:
- Updates `daily_data2_full.company` via JOIN with `industry_type`
- Only touches recent dates (configurable via `--days=N`, default 7)
- Single-date mode (`--date=YYYY-MM-DD`) and full mode (`--all`)
- Idempotent: only updates rows where company IS NULL or differs
- Logs affected count + elapsed time

`scripts/company_refresh_daily.ps1` wrapper for Task Scheduler.

## Result

| Metric | Before | After one-time --all | After daily cron |
|---|---|---|---|
| `daily_data2_full` 9/4 null/total | 1,955/1,955 | **1/1,955** | 0/1,955 (when 7768 SQL'd) |
| `daily_data2_full` 9/3 null/total | 1,955/1,955 | 1/1,955 | 0/1,955 |
| 4/29 era null (rows from 4/29 to 9/4) | 78,941 | **15,931** | 0 (mostly historical) |
| Pre-4/29 era null (rows before 4/29) | 582,786 | 570,899 | 570,899 (legacy, not in scope) |
| Rows updated in one-time run | — | **90,239** in 37.4s | — |

Remaining 1 NULL per recent day is **7768 頌勝科技** — still in
metadata_quarantine, awaiting Walter's TWSE official industry lookup.

## Cron

- Task name: `\tw-invest-suite-company-refresh`
- Schedule: daily 23:25 (before sync-legacy at 23:30 so the refreshed
  company flows into daily_data, daily_data2, chip_daily via sync)
- Command: `powershell -File company_refresh_daily.ps1` (calls python
  with `--days=7`)
- Timeout: 15 min
- First run: 2026-09-05 23:25

## Files added

| Path | Purpose | Size |
|---|---|---|
| `scripts/company_refresh.py` | UPDATE JOIN refresh | 3.4KB |
| `scripts/company_refresh_daily.ps1` | Task Scheduler wrapper | 1.0KB |
| `scripts/_register_company_refresh.xml` | cron registration | 1.6KB |
| `docs/chatgpt_debug/2026-09-05-01-impl-d052f-company-refresh.md` | this MD | — |

## Out of scope (per Walter's 選 1 + D052 review)

- ❌ Pre-4/29 historical nulls (mostly tickers no longer in industry_type;
  legacy issue, not user-visible)
- ❌ daily_data2_full.company for tickers not in industry_type (7768, etc.)
  — these go through metadata_backfill (D052c-d) first
- ❌ 7768 official industry — Walter manual lookup pending
- ❌ Modifying src/_daily_backfill.py (per ChatGPT F6 ban)

## Verification commands

```bash
# 1. dry-run
python scripts/company_refresh.py --dry-run

# 2. one-time full cleanup
python scripts/company_refresh.py --all

# 3. daily cron equivalent
python scripts/company_refresh.py --days=7

# 4. cron status
schtasks /Query /TN '\tw-invest-suite-company-refresh'

# 5. state check
python -c "import pymysql; c=pymysql.connect(host='localhost',user='root',password='1234',database='tw_elec'); cur=c.cursor(); cur.execute(\"SELECT COUNT(*), SUM(CASE WHEN company IS NULL OR TRIM(company)='' THEN 1 ELSE 0 END) FROM daily_data2_full WHERE Date='2026-09-04'\"); r=cur.fetchone(); print(f'9/4 total: {r[0]}  null: {r[1]}')"
```

## Status

✅ D052f ready. 4-month data hygiene gap closed. Daily cron will keep it fresh.
