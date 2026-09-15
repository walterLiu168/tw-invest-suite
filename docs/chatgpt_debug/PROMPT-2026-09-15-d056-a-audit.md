# Debug Prompt — D056-A End State Audit (2026-09-15)

**Paste this to ChatGPT (chat.openai.com)** to get a second opinion on the
Option A pipeline before tomorrow morning's first nightly.

```
=== PROMPT START ===

You are a senior project manager auditing a Taiwan stock analysis pipeline
called tw-invest-suite. I just shipped D056-A Option A simplification
(砍掉複雜度, 只留一條 nightly cron + 一個人早上看 1 分鐘 dashboard).
I want your pre-flight audit BEFORE tomorrow's first hardened nightly run.

## Project context

- Repo: github.com/walterLiu168/tw-invest-suite
- User: Walter Liu, GitHub: walterLiu168, frustrating with debugging basic pipeline
- Stack: Windows PowerShell 5.1, Python 3.10/3.14, MySQL `tw_elec` (238 tables),
  GitHub Pages, Cloudflare Tunnel (groovelab.dev, secondary)
- User style: 繁體中文, concise, no boilerplate, 「／」not `/`

## What I just shipped (D056-A, 4 commits on origin/main)

1. c5bab73 D056 P1+ — PowerShell Start-Process ExitCode bug fix
   (Python wrapper `_debug/run_stage.py` writes sidecar exit code file;
    Run-Stage in run_daily.ps1 reads sidecar instead of $p.ExitCode)
2. 5e705bb D056-A Option A — simplify + dashboard
   - run_daily.ps1: removed Stages 7-17 (D027/D029 advanced) from default nightly;
     added -IncludeAdvancedStages switch for opt-in restore
   - postflight_daily.py: tail-calls build_dashboard.py via subprocess
     (best-effort, separate process boundary, doesn't fail postflight)
   - daily_summary.py: regex fix from earlier audit (never committed)
   - public/data/dashboard.md: first generated artifact
3. b7c30a3 docs: 7 postmortem reports for ChatGPT PM review
4. d0814be public/: 9/14 nightly + 9/15 manual repair artifacts (regenerated)
5. f2ee743 docs/pipeline-reference.md (full cron + per-file purpose reference)

Plus: marker_watchdog cron at 23:55 daily (D056 P2) — if completion marker
missing/stale, regenerate from latest DB picks. Backup defense.

## Current nightly schedule (after D056-A)

22:25  daily-report  run_daily.ps1 (5 stages + 1 optional, was 17)
22:30  yfinance      yfinance_daily.py (1,962 tickers, ~30-50 min)
23:00  health-check  check_openalice_health.py --json
23:25  company-refresh
23:30  sync-legacy
23:55  marker-watchdog (NEW)
00:05  postflight    verify 8 cron + 5 DB invariant + write daily_summary + dashboard
00:30  publish       push public/ → gh-pages branch

## Current dashboard output (last manual run)

OVERALL: 🟢 OK
DB picks: 24 (active=24)
Marker: data_date=2026-09-14 run_id=15 status=ok
OHLCV latest: 2026-09-14 (1d ago)
GitHub Pages: all 6 key pages 200 ✓
Cron results: daily-report ✓, publish ✓, marker-watchdog (NeverRun yet — first run tonight),
             health-check ✗ (known: 2 finmind BEHIND), postflight ✗ (known: 9/14 false-positive)
Quarantine: 11 open (1 distinct ticker — 7768, PENDING J)

## PENDING list (feature freeze active since 9/15)

| 代號 | 項目 |
|---|---|
| J | 7768 quarantine (11 rows accumulating 9/3-9/12) — needs TWSE official classification |
| Weekly Shareholding 1330 | D052h-era exit code 2 |
| FinMind weekly | `finmind_taiwan_total_margin_daily` stuck at 2026-08-18 (structural weekly cadence) |
| cloudflared 1033 | groovelab.dev returning 1033 |
| Slack/Telegram notifier | not implemented |
| runtime↔git split | single source of truth issue |
| 7768 manual close-out | quarantine accumulating |

## What I want from you

Pre-flight audit of the D056-A Option A design. Specifically:

1. **What's the biggest remaining failure risk** in tonight's 22:25 nightly?
   (I'm worried about silent failures — cron rc=0 but actual data stale.)
   Cite specific code path or config.

2. **Is the marker-watchdog at 23:55 sufficient defense** for the
   "completion marker missing → 00:30 publish pushes yesterday's data"
   failure mode? Or should I add a second watchdog?

3. **Dashboard noise reduction**: should I suppress "known PENDING" items
   from the 🟡 WARNING level so a clean run shows 🟢 OK? Trade-off:
   honest vs signal-to-noise.

4. **Single most impactful hardening change** I should add THIS WEEK
   (before next weekend). Pick one. With file path + 5-line code change.

5. **Any obvious bugs** in my D056-A commit that I missed? (run_daily.ps1
   simplified, postflight_daily.py dashboard integration.)

## What you DON'T have access to

- My live DB state (use the snapshot I gave you)
- My cron LastResult history
- PowerShell 5.1 specific quirks (mention if relevant)
- The 11 D-code history (D001-D056 in docs/chatgpt_debug/)

## Constraints

- **Feature freeze** — no new features, only hardening/fixes
- PowerShell 5.1 — no `&&`, use `;`. `Start-Process $p.ExitCode` is
  unreliable when redirected (already worked around with Python wrapper)
- All commits local-only until I (Walter) approve `git push`
- runtime scripts/ ↔ git repo scripts/ SHA must match for cron-run files
- DB schema changes need migration plan (avoid this week)

Format your response as:

1. **Top risk** (1-2 sentences + cite)
2. **Specific recommendations** (numbered, each with file path + code)
3. **Verification plan** for each recommendation
4. **One thing you'd skip** (lessons-learned from past debugging)
5. **Confidence level**: HIGH / MEDIUM / LOW on each recommendation

Use 繁體中文. No boilerplate. No "希望對你有幫助".

=== PROMPT END ===
```

---

## Expected ChatGPT response shape

ChatGPT will likely return:
- 1 paragraph summary
- Numbered recommendations with code
- Some suggestions that DON'T apply (filter these)
- Some factual errors about repo state (I'll cross-reference)

## After ChatGPT responds

1. **Paste ChatGPT's response** to me (Mavis)
2. I will cross-reference each claim against actual repo state
3. I'll write a `RESP-2026-09-15-XX-chatgpt-d056-a-audit.md` file in
   `docs/chatgpt_debug/` capturing: what was right, what was wrong,
   what we'll implement
4. If actionable: I'll implement + commit (local only)
5. Wait for Walter's `git push origin main` approval