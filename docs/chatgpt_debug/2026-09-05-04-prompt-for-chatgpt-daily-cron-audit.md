# ChatGPT review request: new tw-invest-suite daily cron schedule (3 new crons added 2026-09-05)

> **For**: ChatGPT (via Codex visible UI or web chatgpt.com)
> **From**: Walter Liu (via Mavis desktop)
> **Date**: 2026-09-05
> **Status**: pending
> **Coding preflight**: REUSE — read-only audit of new cron scripts + 3 MDs. No code change unless Walter approves.

---

## 📋 PROMPT (copy this into ChatGPT)

```
You are reviewing 3 NEW Task Scheduler crons added 2026-09-05 to a
Taiwan stock analysis platform (tw-invest-suite, 1,962 tickers, MySQL
tw_elec, GitHub Pages).

The 3 new crons fill gaps in the daily routine. Each script + its MD
lives at:
  C:\Users\icemo\Projects\tw-invest-suite\scripts\<script>.py
  C:\Users\icemo\Projects\tw-invest-suite\scripts\<script>_daily.ps1
  C:\Users\icemo\Projects\tw-invest-suite\scripts\_register_<cron>.xml
  C:\Users\icemo\Projects\tw-invest-suite\docs\chatgpt_debug\2026-09-05-NN-impl-*.md

NEW CRONS:

1. \\tw-invest-suite-market-screen, daily 18:00, 30min timeout
   Calls run_market_screen.py (existing 10KB script in runtime dir).
   Closes prior picks, generates 24 new picks, writes to
   market_screen_runs + market_screen_picks. This closes a 23-day
   gap (8/12 was the last auto run).
   MD: docs/chatgpt_debug/2026-09-05-03-impl-d052g-market-screen-cron.md

2. \\tw-invest-suite-metadata-backfill, daily 18:05, 10min timeout
   Calls metadata_backfill.py. First scans daily_data2_full latest
   date for tickers missing from industry_type, then runs with
   --batch=<missing list>. Per-event fingerprint dedup prevents
   quarantine accumulation.
   MD: docs/chatgpt_debug/2026-09-05-02-impl-d052d-metadata-backfill-cron.md

3. \\tw-invest-suite-company-refresh, daily 23:25, 15min timeout
   Calls company_refresh.py. UPDATE JOIN from industry_type.company
   to daily_data2_full.company. --days=7 (last week). This closes a
   4-month gap where daily_data2_full.company was 100% NULL on
   9/2-9/4.
   MD: docs/chatgpt_debug/2026-09-05-01-impl-d052f-company-refresh.md

FULL DAILY SCHEDULE (after these 3 additions):

  17:35 + 17:55  OpenAlice         OHLCV landing
  18:00          market-screen     generate 24 picks       (NEW D052g)
  18:05          metadata-backfill add newly listed        (NEW D052d)
  22:25          daily-report      render watchlist + analyze HTML
  23:00          health-check      self-check
  23:25          company-refresh   refresh company col     (NEW D052f)
  23:30          sync-legacy       4 legacy tables
  23:50          publish           push GitHub Pages

QUESTIONS for you:

1. **Race conditions**: market-screen runs 18:00, metadata-backfill
   runs 18:05. If metadata-backfill adds new tickers to industry_type
   between 18:00 and 18:05, those tickers won't be in the 18:00 screen
   but will be in the 22:25 daily-report. Is this a real problem?
   Should the order be reversed (18:00 backfill → 18:05 screen)?

2. **company-refresh timing**: 23:25 is AFTER sync-legacy (23:30).
   Wait — re-check the order. If sync-legacy is at 23:30 and
   company-refresh at 23:25, then company-refresh runs BEFORE
   sync-legacy. So the refreshed company DOES flow into daily_data,
   daily_data2, chip_daily. Is this order correct or should they swap?

3. **Error handling**: each script's PS1 wrapper exits 1 on error.
   If market-screen fails at 18:00, what is the impact on 22:25
   daily-report? Will watchlist show stale 9/1 picks forever, or
   is there a fallback?

4. **Idempotency / recovery**: if a cron is missed (machine sleep,
   power outage), does the system self-heal on next run? Or do we
   need a "catch up" pass? Specifically:
   - market-screen missed one day → next day's picks are based on
     2-day-stale universe. OK or problem?
   - metadata-backfill missed → newly-listed tickers not in
     industry_type. Will next day's metadata-backfill catch them?
   - company-refresh missed → company col still NULL. Next day
     covers it.

5. **22:25 daily-report stage ordering**: 22:25 reads industry_type
   for analyze HTML rendering. If metadata-backfill at 18:05 added
   a new ticker, will 22:25 see it? (industry_type is shared DB state,
   so YES — but verify by checking render_full_watchlist.py and
   render_ticker_db_only.py for any caching that might use a stale
   industry_type snapshot.)

6. **Stock-profile divergence**: market_screen uses what data sources
   for picking? Does it read daily_data2_full.company? (per the
   order: market_screen 18:00, company-refresh 23:25 → company
   values used by market_screen are from PREVIOUS day's refresh.)

7. **What I might be missing**: any race, deadlock, or ordering
   issue with the 3 new crons + the existing 5 that I haven't thought
   of?

FILES TO REVIEW (read all):

  docs/handoff_chatgpt.md                                       (general context)
  docs/chatgpt_debug/2026-09-05-01-impl-d052f-company-refresh.md
  docs/chatgpt_debug/2026-09-05-02-impl-d052d-metadata-backfill-cron.md
  docs/chatgpt_debug/2026-09-05-03-impl-d052g-market-screen-cron.md
  scripts/company_refresh.py
  scripts/company_refresh_daily.ps1
  scripts/_register_company_refresh.xml
  scripts/metadata_backfill.py
  scripts/metadata_backfill_daily.ps1
  scripts/_register_metadata_backfill.xml
  scripts/market_screen_daily.ps1
  scripts/_register_market_screen.xml
  C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\run_market_screen.py
  C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\market_screen.py
  C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\run_daily.ps1

OUTPUT FORMAT (return markdown only, no preamble):

  # <short title>
  > Submitted: 2026-09-05 by ChatGPT (visible UI)
  > Target: 3 new daily crons + 5 existing
  > Status: pending
  > Scope: cron | scripts

  ## Review of Mavis cron schedule
  ...

  ## Findings
  ### F1. <title>
  - File: <path>:<line>
  - Issue: ...
  - Suggested fix: ...
  - Priority: high | mid | low

  ## Out of Scope
  ...

  ## Questions back to Mavis
  ...

  ## Status
  *(Mavis will append implementation results)*
```

---

## 📂 Supporting context

If ChatGPT wants full project context: `docs/handoff_chatgpt.md` (13.9KB, 15 sections).

## 📂 Project conventions (for ChatGPT)

- Language: 繁體中文 only
- Output filenames: 「／」 not `/`
- Volume: 1 張 = 1,000 股, use `Math.ceil(shares/1000)` when displaying
- FinMind sponsor token at `~/.finmind_token`, ~0.4s/call
- DB: localhost / root / 1234 / tw_elec
- MySQL convention: NULL → None in Python; 0/負值 → None for ratios
- Color convention: 紅=漲, 綠=跌 (Taiwan, opposite of US)
- Coding preflight: REUSE — only modify existing patterns, don't invent

## 🔄 Workflow reminder

1. You (Walter) copy the **PROMPT** block into ChatGPT
2. ChatGPT responds with the structured markdown review
3. You paste the response into a new file: `docs/chatgpt_debug/2026-09-05-NN-response-from-chatgpt-daily-cron.md`
4. Mavis reads the response and implements findings (per your approval)
5. Mavis appends "Status" section to track what was implemented

**Timing**: tonight 18:00 is the first fire of the new crons. ChatGPT review before then would let us catch any issues before data gets written.
