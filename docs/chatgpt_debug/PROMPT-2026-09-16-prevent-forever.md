# Debug Prompt — Final Hardening Pass (2026-09-16)

**Paste this to ChatGPT (chat.openai.com)** for a final review before the
9/16 22:25 nightly. Goal: identify any remaining failure modes in the
tw-invest-suite daily pipeline and recommend specific hardening — with
priorities for the next 24 hours.

```
=== PROMPT START ===

You are a senior SRE auditing a Taiwan stock analysis pipeline called
tw-invest-suite. Today the pipeline had two cascading failures that left GH
Pages stuck on stale 9/14 data for 12 hours. Recovery just succeeded
(GH Pages now shows 9/15). The user wants this class of bug to never
recur — final hardening pass before tonight's 22:25 nightly.

## Repository state (verified 2026-09-16 15:54 GMT+8)

origin/main = local HEAD = b2e4cf9
4 commits shipped today:
- d64e38d Handle non-finite provider metrics without losing ticker reports
- dab8149 Preserve certified bytes through Git publication
- 2d5b8d8 Keep request details out of public fetch warnings
- f399502 Fix mixed watchlist validation
- fe3e67d Fix daily run certification and verified publication gates
- 8e75847 prevent forever: nightly_health watchdog + cert stderr capture
- b2e4cf9 recovery: 9/15 nightly certified + Stage 6 timeout hardening

## Today's two production incidents (chronological)

### Incident 1: 9/15 22:25 nightly cert silent failure
- All 6 stages ran to completion at 23:36:53 (Stage 6 watchlist OK, exit 0)
- complete() failed with "FATAL: nightly not certified" but stderr was
  DROPPED in PowerShell — no detail about WHICH of the 8 cert checks failed
- Marker never written → 9/16 00:30 publish found no fresh marker → rc=1
- GH Pages stayed on 9/14 data

### Incident 2: 9/16 09:55 nightly PowerShell + python deadlock
- Started 09:55:23, Stage 1 OK 09:55:46, Stage 2 render started
- Stage 2 completed at 10:53:54 (exit sidecar 0 written)
- PowerShell + python wrapper became idle; no Stage 3 started; no
  log updates after Stage 2 OK
- pipeline_run.json stayed at status=running (process died without
  trap-handler firing); mutex held; next cron blocked
- I (Mavis) manually killed PID 25364 + 1856 at 12:13 to recover

### Incident 3 (recovery): 9/16 13:22 nightly Stage 6 timeout
- Manual re-run Mode render after kill
- Stage 6 watchlist TIMEOUT at 10min (Stage 6 timeout=10min in run_daily.ps1)
- Root cause: render_full_watchlist.py:1813 uses ThreadPoolExecutor(workers=4)
  with `for fut in as_completed(futs): fut.result()` — no per-future timeout.
  One slow yfinance/finmind fetch can hang the entire stage.
- Fix applied: Stage 6 timeout bumped 10min → 30min (commit b2e4cf9)

### Incident 4 (recovery): trap race corrupts STATE after complete() success
- After complete() wrote marker+state=ok, the PS orchestrator's "Final
  stats" section (lines 437-449) crashed for unknown reason
- trap handler called `pipeline_state.py fail`, which wrote
  state.status=failed even though marker.status=ok
- publish_ghpages_daily.ps1 → verify_marker() requires BOTH marker.status=ok
  AND state.status=ok → publish refused
- Manual _debug/_fix_state.py recovered by syncing state.status from marker
- Permanent fix NOT YET applied

## Hardening already shipped (today)

1. **scripts/_debug/nightly_health.py** — watchdog. Detects:
   - status=running AND age > 90min → stuck
   - status=running AND no stage log update > 30min → stuck
   - status=running AND owner_pid dead → orphan
   With --kill: force-kill PID + mark state=failed so next cron can run.

2. **tw-invest-suite-nightly-health cron** registered: daily 02:30 / 04:00 / 06:00
   - Detects stuck nightly processes, force-kills and releases mutex
   - Already verified registered; PID list verified earlier

3. **scripts/run_daily.ps1 cert stderr capture** (line 411-432)
   - Now redirects complete() stderr/stdout to _debug/complete_<id>.{log,err}
   - FATAL log line includes the actual reason: `Log-Msg "  reason: $certReason"`
   - Future cert failures will be diagnosable from daily_run_*.log

4. **scripts/run_daily.ps1 Stage 6 timeout** 10min → 30min
   - Tolerates transient network blips during parallel deep-dive fetches

5. **scripts/_debug/_fix_state.py** (gitignored, runtime only)
   - Sync state.status from marker.status when trap corrupted state
   - Used once today (during recovery)

## What I want from you

Final hardening pass. Recommend the TOP 3-5 most impactful changes for the
next 24 hours, in priority order. For each:

1. **Title** (1 line)
2. **Failure mode prevented** (cite the incident or scenario)
3. **File path + specific change** (copy-pasteable diff or new code)
4. **Verification plan** (how do I know it worked?)
5. **Confidence** (HIGH/MEDIUM/LOW)

Specifically I want answers to:

### Q1. The trap race (Incident 4) needs a permanent fix
complete() succeeded → marker written → PS crashes in Final stats → trap
calls fail() → state.status=failed → publish rejects.
What's the cleanest fix?
- Option A: After complete() success, exit 0 immediately (skip Final stats).
- Option B: fail() should refuse to write state.status=failed if marker
  is already ok with version D056-2.
- Option C: run_daily.ps1 should call complete() in a try/catch with the
  trap re-armed only on the pre-cert portion of the script.
Which is least invasive AND most correct?

### Q2. Stage 6 robustness (Incident 3)
Stage 6 timeout=30min is a band-aid. The real fix is per-future timeout
inside render_full_watchlist.py. Show me the exact patch — should be ~10 lines
using `as_completed(timeout=X)` or `fut.result(timeout=X)` with graceful
degradation when one fetch hangs.

### Q3. nightly_health thresholds
Current: STUCK_AFTER_MIN=90, STAGE_LOG_QUIET_MIN=30.
Given that nightly budgets are:
- Stage 2 render: 90min (1,962 tickers × 1.5s = ~50min typical)
- Stages 3-6: ~15min total
- complete() + publish: ~5min
Total nightly budget: ~70min typical, 4h hard cap.
Are the watchdog thresholds optimal? Should nightly_health run more often
(e.g., every 30min during the active nightly window 22:25-02:25)?

### Q4. Recovery artifacts not auto-cleaned
After recovery, _debug/ has stale stage_logs from failed runs (e.g.,
20260916_a110a9e66d4e4adaa557efe08b98d47d_stage3_patterns.log with
log_age=24h+). Should nightly_health or a separate cron clean these?
Or are they useful audit trail? Recommend a retention policy.

### Q5. Anything I missed?
Look at the actual code paths:
- scripts/run_daily.ps1 (the orchestrator)
- scripts/pipeline_state.py (state + complete)
- scripts/_debug/run_stage.py (wrapper)
- scripts/_debug/nightly_health.py (watchdog)
- scripts/render_full_watchlist.py (Stage 6, fetch parallel)

Identify any failure mode that's still unaddressed. Don't restate the
already-fixed items.

## Constraints (unchanged)

- **No new features** — only hardening / fix / defense in depth
- PowerShell 5.1 — no `&&`, no `[ordered]@{}`, no `??` null-coalesce
- All commits local-only until I (Walter) approve `git push origin main`
- runtime scripts/ ↔ git repo scripts/ SHA must match for cron-run files
- DB schema changes need migration plan (avoid this week)

## Output format

For each of Q1-Q5: numbered answer with file path + code + verification.
End with a SHORT list of "things I checked that you didn't mention but
look fine" so I know you read the code, not just the prompt.

Use 繁體中文. No filler.

=== PROMPT END ===
```

---

## What I (Mavis) will do when ChatGPT responds

Per our **3-step workflow** (`docs/chatgpt_debug/HOW-TO-chatgpt-debug.md`):

| Phase | What I do |
|---|---|
| 1. **Cross-reference** | Read each cited file; check ChatGPT's claims against actual code. Common errors to catch: PS 7+ syntax, missing context, recommendations that need admin, things already shipped |
| 2. **Verdict doc** | Write `docs/chatgpt_debug/RESP-2026-09-16-XX-prevent-forever.md` with **Accepted / Rejected / Modified** per recommendation |
| 3. **Implement** | Make changes, sync runtime↔git SHA, run tests, commit local-only |
| 4. **Wait for push** | Tell Walter: "X files ready, push?" |

## Things to remember when ChatGPT responds

ChatGPT doesn't know:

1. **Already-shipped items** (it'll re-recommend these — I'll filter):
   - nightly_health watchdog + cron (✅ shipped in 8e75847)
   - cert stderr capture (✅ shipped in 8e75847)
   - Stage 6 timeout 30min (✅ shipped in b2e4cf9)

2. **PowerShell 5.1 limits** — no `&&`, no `??`, no ternary with `?`:
   ```ps1
   # WRONG (PS 7+ only):
   $value = $foo ?? "default"
   # RIGHT (PS 5.1):
   if ($null -eq $foo) { $value = "default" } else { $value = $foo }
   ```

3. **Trap semantics** — PS trap fires on terminating errors only;
   non-terminating errors don't fire trap. So `trap { fail() }` only
   fires if complete() throws a terminating error.

4. **Cwd behavior** — `Set-Location` in run_daily.ps1 sets cwd to runtime
   scripts/. Any path in the new code should be relative to that or use
   absolute paths.

5. **Cron discipline** — changes to nightly must not break the 4h cron
   limit at 02:25 deadline, and must respect the mutex `Local\TwInvestSuiteDaily`.

6. **D056-2 contract** — manual `--publish` is forbidden per spec:
   > Do not run an ad-hoc --publish as part of a local repair without publication authorization.
   Any "auto-publish on recovery" suggestion should be REJECTED.

---

## The questions I most need ChatGPT to nail

The two highest-priority items I want ChatGPT to give correct answers to:

1. **Q1 — Trap race permanent fix**: this is the most likely recurrence
   bug. If PS orchestrator crashes again post-cert, GH Pages will be stuck
   again until manual repair. Need a clean solution.

2. **Q2 — Stage 6 per-future timeout**: 30min timeout is OK but 30min
   blocking on a stuck fetch is wasteful. Per-future timeout with
   graceful degradation (skip the hung pick) is better.</mm:think>