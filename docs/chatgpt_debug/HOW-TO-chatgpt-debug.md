# HOW-TO: ChatGPT Debug Workflow

**Goal**: Use ChatGPT as a second pair of eyes / project manager for the
tw-invest-suite daily pipeline, while keeping Mavis (me) as the executor.

## When to use this workflow

- ✅ Bug or failure that's hard to diagnose
- ✅ Want a second opinion before implementing a design change
- ✅ Stuck on something for > 1 day
- ✅ Audit before a major commit/push
- ❌ Quick tactical fixes (just ask Mavis directly)
- ❌ Routine cron status checks (Mavis already knows)

---

## The 3-step workflow

### Step 1 — Walter: pick or fill a prompt

Two options:

**A. Use the reusable template** (`PROMPT-debug-template.md`):
- Open `C:\Users\icemo\Projects\tw-invest-suite\docs\chatgpt_debug\PROMPT-debug-template.md`
- Copy from `=== TEMPLATE START ===` to `=== TEMPLATE END ===`
- Fill in `## Current issue`, `## State snapshot`, optionally `## Constraints`

**B. Use a session-specific prompt** (when one exists):
- e.g. `PROMPT-2026-09-15-d056-a-audit.md` is the current "what to ask ChatGPT
  about right now" prompt
- Just paste it to ChatGPT

### Step 2 — Walter: pipe to ChatGPT

1. Open `chat.openai.com` (or chatgpt.com) in your browser
2. Paste the prompt (or template + filled sections)
3. Send. Wait for response. **Don't edit ChatGPT's response** — paste it raw back to Mavis.

### Step 3 — Walter: paste ChatGPT's response to Mavis

Just paste the raw ChatGPT response in the next chat turn. Like:

> "ChatGPT 說：[paste response here]"

That's it. Mavis will handle the rest.

---

## What Mavis does after ChatGPT responds

(Mavis = me, the agent in this session.)

### Phase 1 — Cross-reference (5 min)

For each claim in ChatGPT's response:
1. Read the cited file
2. Verify the file actually has the issue ChatGPT described
3. Check if the fix ChatGPT proposed would actually work given the actual code
4. Check for conflicts with existing code (Walter's discipline: don't add new
   dependencies, don't break PowerShell 5.1 quirks)

**Common ChatGPT errors I'll catch**:
- Recommends packages we don't have installed
- Suggests PowerShell 7+ syntax (we have 5.1)
- Proposes features (against feature freeze)
- Doesn't know about PowerShell `$p.ExitCode` bug we already worked around
- Hallucinates file paths that don't exist

### Phase 2 — Verdict document (2 min)

I'll write `docs/chatgpt_debug/RESP-YYYY-MM-DD-XX-<topic>.md` capturing:

- **Accepted** (X recommendations we'll implement)
- **Rejected** (Y recommendations with reason — usually "we already have this",
  "ChatGPT doesn't know about X", "out of scope")
- **Modified** (Z recommendations where I'll tweak the proposed code)
- **Action items** (specific file changes with diffs)

### Phase 3 — Implement (10-30 min per item)

For each accepted item:
1. Read current file state (already done in phase 1)
2. Make edit (scoped, no `git add -A`)
3. Verify (run unit test, smoke test, or check syntax)
4. Sync runtime ↔ git SHA if cron-relevant
5. Stage + commit locally

### Phase 4 — Wait for Walter's push approval

Per discipline: all commits local-only. I tell Walter: "X files ready, push?".
Walter says "yes" or "no, also do Y". Repeat.

---

## What Mavis will NOT do

- ❌ Blindly implement ChatGPT's recommendations without cross-reference
- ❌ Push to origin/main without Walter's explicit approval
- ❌ Add features during feature freeze
- ❌ Break runtime↔git SHA match for cron-run files
- ❌ Suggest changing the prompt back to ChatGPT — that's circular

---

## Artifacts in `docs/chatgpt_debug/`

Naming convention:
- `PROMPT-debug-template.md` — reusable template (rarely changes)
- `PROMPT-YYYY-MM-DD-<topic>.md` — session-specific prompt (when needed)
- `RESP-YYYY-MM-DD-XX-<topic>.md` — Mavis's verdict on a ChatGPT response
- `YYYY-MM-DD-NN-<topic>.md` — older postmortem / implementation reports

Files Walter should know:
- `README.md` — overview
- `HOW-TO-chatgpt-debug.md` — this file
- `PROMPT-debug-template.md` — the template

---

## Example: full workflow trace

```
Walter: "ChatGPT 說：
[ChatGPT response about marker-watchdog interval being too short,
recommends adding a 2nd watchdog at 00:15]

請處理"

Mavis (this turn):
  Phase 1: Read marker_watchdog.py + marker_watchdog_daily.ps1
            Verify ChatGPT's claim about interval being too short
            (actually: the cron is at 23:55, publish at 00:30 — 35 min gap
            is fine. ChatGPT wrong.)
  Phase 2: Write RESP-2026-09-15-01-marker-watchdog-second-watchdog.md
           - Rejected: ChatGPT's claim that current interval is too short
           - Reason: 23:55 → 00:30 = 35 min, plenty of time
           - Modified: ChatGPT's idea of a 2nd watchdog IS good defensive
             measure. Suggest 00:10 (5 min after postflight, before publish)
  Phase 3: Add 2nd watchdog at 00:10
  Phase 4: Tell Walter "1 file ready, push?"

Walter: "push"

Mavis:
  git push origin main
  Confirmed
```

---

## When to skip Mavis entirely

If the ChatGPT response is trivial and you just want it done:
- Tell me: "implement ChatGPT's recommendations, skip the verdict doc"
- I'll still cross-reference but won't write the RESP file
- Use sparingly — the RESP file is the audit trail

---

## Quick reference

| Action | File / Command |
|---|---|
| Get the template | Read `docs/chatgpt_debug/PROMPT-debug-template.md` |
| See last ChatGPT session | `docs/chatgpt_debug/RESP-*.md` (newest first) |
| See all postmortems | `docs/chatgpt_debug/YYYY-MM-DD-NN-*.md` |
| Tell me ChatGPT responded | Just paste response in chat |
| Bypass verdict doc | "implement, skip verdict" |