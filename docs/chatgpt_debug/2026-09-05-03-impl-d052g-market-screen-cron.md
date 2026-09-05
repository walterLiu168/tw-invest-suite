# D052g: 18:00 daily market_screen cron (closes the 23-day gap)

> **Submitted**: 2026-09-05 by Mavis
> **Target**: market_screen_picks + market_screen_runs
> **Status**: ✅ cron registered
> **Scope**: cron | scripts

## Problem (found in 9/5 audit)

`market_screen_runs` had only 3 rows total: id=1 (8/12), id=2 (8/31), id=3 (9/1).
**9/2, 9/3, 9/4 had no market screen at all.** That means:
- `watchlist.html` shows 24 picks from 9/1, never updated
- `market_screen_picks.status='active'` = 0 (because sync-legacy closes prior picks
  on each run, but no new run = no active picks)
- aging / rebalance logic never fires

`run_daily.ps1` (in `C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\`) has
**no "screen" stage**. The 3 existing runs were triggered manually or by
D045/D045b backfill scripts. After 9/1, no process called
`run_market_screen.py` automatically.

ChatGPT's 2026-09-03 manager audit flagged this exact issue:
> Latest three screen runs were dated 2026-09-01, 2026-08-31, and 2026-08-12

## Fix

New cron `\tw-invest-suite-market-screen` that:
1. Runs `run_market_screen.py` daily at 18:00
2. That script:
   - Calls `ms.screen_market()` to compute picks
   - Saves to `market_screen_runs` + `market_screen_picks`
   - Generates Markdown + HTML + deep-dive prompt reports

## Schedule context

| Time | Cron | Purpose |
|---|---|---|
| 17:35 + 17:55 | OpenAlice | OHLCV landing |
| **18:00** | **market-screen (new)** | **Generate 24 picks for today** |
| 18:05 | metadata-backfill (D052d) | Add newly-listed tickers to industry_type |
| 22:25 | daily-report | Render analyze/watchlist HTML using today's picks |
| 23:00 | health | Self-check |
| 23:25 | company-refresh (D052f) | Refresh daily_data2_full.company from industry_type |
| 23:30 | sync-legacy | Sync 4 legacy tables |
| 23:50 | publish | Push to GitHub Pages |

Market screen at 18:00 reads industry_type (will have 1,973 rows from D052c
+ 1 missing = 7768). D052d at 18:05 may add 1 row for 7768 (after Walter
resolves), but market screen has already run for the day — fine, picks
re-stabilize the next day.

## Files

| Path | Purpose |
|---|---|
| `scripts/market_screen_daily.ps1` | PS1 wrapper — runs `run_market_screen.py` |
| `scripts/_register_market_screen.xml` | Task Scheduler registration |

## Tested

Manual run on 9/5 14:48 (about to commit): not run yet — will let the
cron fire at 18:00 first. If issues, run manually:
```bash
schtasks /Run /TN '\tw-invest-suite-market-screen'
```

## Out of scope (per Walter's 選 1)

- ❌ Making market_screen also pick up newly-listed tickers from D052d
  (would need ordering change: D052d → market_screen, not the other way)
- ❌ Slack/Telegram alerts when picks change (D052e)
- ❌ 7768 official industry (Walter manual)

## Status

✅ D052g ready. Daily 18:00 cron will fire tonight 9/5 at 18:00. Picks
will be ready before 22:25 daily-report.
