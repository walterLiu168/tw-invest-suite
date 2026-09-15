# ChatGPT Debug Prompt Template (tw-invest-suite)

**Use case**: Walter pipes this to ChatGPT via visible UI (chat.openai.com or chatgpt.com).
ChatGPT acts as project manager / debugger. The response comes back via the visible UI;
Walter copies it back to Mavis (me) for verification + implementation.

**Workflow**: see `docs/chatgpt_debug/HOW-TO-chatgpt-debug.md`

---

## When to use this template

- New bug / failure (cron rc≠0, DB invariant fail, publish missed, etc.)
- Want a 2nd opinion on a design decision before implementing
- Stuck on a specific issue for > 1 day
- Want to surface risks in the current pipeline

---

## Template (copy from `=== TEMPLATE START ===` to `=== TEMPLATE END ===`)

```
=== TEMPLATE START ===

You are a senior project manager debugging a Taiwan stock analysis pipeline
called tw-invest-suite. Your job: diagnose, propose specific changes (with
file paths and exact code), and rank by impact.

## Project context

- Repo: github.com/walterLiu168/tw-invest-suite (Windows, PowerShell 5.1, Python 3.10/3.14)
- DB: MySQL `tw_elec` on localhost, 238 tables
- Stack: PowerShell + Python + pymysql + yfinance + FinMind + GitHub Pages
- User: Walter Liu (not a coder — wants concise, actionable answers)
- User style preference: 繁體中文, 1-line answers when possible, 「／」not `/`,
  no "希望對你有幫助" boilerplate, no defensive "you can also try..." filler

## Current pipeline (11 crons, daily)

17:35/45/55 OpenAlice OHLCV landing (D:\CODEX\AI-Telegram)
18:10 metadata-backfill (metadata_backfill.py)
18:20 market-screen (market_screen_runner.py → 24 picks)
22:25 daily-report (run_daily.ps1, 5 stages + 1 optional after D056-A)
22:30 yfinance (yfinance_daily.py, 1,962 tickers)
23:00 health-check (check_openalice_health.py --json)
23:25 company-refresh (company_refresh.py)
23:30 sync-legacy (sync_legacy_tables.py)
23:55 marker-watchdog (marker_watchdog.py — NEW D056 P2)
00:05 postflight (postflight_daily.py → build_dashboard.py → daily_summary.py)
00:30 publish (publish_ghpages_daily.ps1 → push public/ to gh-pages branch)

D056-A simplification (just shipped): run_daily.ps1 stages 7-17 removed from
default nightly; advanced stages opt-in via `-IncludeAdvancedStages`. Plus
postflight_daily.py now calls build_dashboard.py to produce a 1-page morning
dashboard.

## Current issue / question

[DESCRIBE THE ISSUE HERE — paste error, paste cron rc, paste log line,
 paste dashboard output, etc. Be specific.]

## State snapshot

- Working tree clean / dirty (paste `git status --short` if relevant)
- Recent commits (paste `git log --oneline -5`)
- Relevant DB rows (paste SELECT output)
- Relevant log lines (paste tail of last_run_*.log)

## Constraints

- **No new features** (feature freeze active since 9/15)
- PowerShell 5.1 `Start-Process -PassThru -RedirectStandardOutput` returns
  empty `$p.ExitCode` — workarounds already in place (Python wrapper +
  sidecar file at scripts/_debug/run_stage.py)
- DB schema changes need ALTER TABLE + backfill plan
- All commits local-only until user (Walter) approves `git push`
- runtime scripts/ ↔ git repo scripts/ SHA must match for cron-run files

## What I want from you

1. **Root cause** (cite specific code or config — not vague)
2. **Specific fix** with file path + exact diff or new code (copy-pasteable)
3. **Verification plan** (how do I know the fix worked?)
4. **Risk callouts** (what else might break)
5. **Rank** among any PENDING items if multiple issues at play

=== TEMPLATE END ===
```

---

## Filling the template (cheat sheet)

| Section | What to paste |
|---|---|
| `## Current issue` | 1-3 sentences: what happened + when + what's the user impact |
| `## State snapshot` | `git log --oneline -5` + `git status --short` + relevant log tail (last 20-30 lines) + DB SELECT if DB-related |
| `## Constraints` | Usually leave as-is. Add if a NEW constraint applies (e.g. "no DB schema changes this week") |

## What ChatGPT should NOT do

- Don't ask me to install packages or run setup commands
- Don't suggest "let me see more logs" — Walter is the only one with logs
- Don't propose new tools / dependencies
- Don't write essays — bullet points + exact code only

---

## Example: filled template for a publish failure

```
## Current issue

00:30 publish cron pushed to gh-pages successfully but dashboard.md
shows OVERALL: 🟡 WARNING with quarantine=11. User said this is
"noisy, want it to not be yellow".

## State snapshot

git log --oneline -3:
  f2ee743 docs: pipeline reference
  d0814be public/: 9/14 nightly + 9/15 manual repair artifacts
  b7c30a3 docs: 7 postmortem reports

dashboard.md (relevant section):
  ## DB integrity
  - Quarantine open: **11** (1 distinct ticker)
  ## ⚠ Action items
  - 🟡 [WARNING] quarantine open=11 (PENDING J: 7768)
  **OVERALL**: 🟡 WARNING — review action items

DB:
  SELECT * FROM metadata_quarantine WHERE resolved_at IS NULL;
  → 11 rows, all ticker=7768, dates 9/3-9/12

## Constraints

- 7768 問題已 PENDING J (PM 9/6: 需要 TWSE 官方分類才能 close)
- Walter 不想要 noisy dashboard
```

---

## After ChatGPT responds

Walter pastes ChatGPT's response to me. I will:
1. **Cross-reference**: check ChatGPT's claims against actual repo state (read
   files, run greps, query DB). Don't blindly trust.
2. **Identify factual errors** in ChatGPT's response (it WILL make some —
   it doesn't have live access to your machine).
3. **Implement** with scoped git staging (NO `git add -A`).
4. **Commit + tell Walter** — wait for explicit push approval.

See `HOW-TO-chatgpt-debug.md` for full protocol.