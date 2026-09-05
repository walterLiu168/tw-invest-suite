# 2026-09-03-03: Manager audit — pipeline truthfulness and UI regressions

> Submitted: 2026-09-03 by ChatGPT
> Status: pending
> Scope: full-project | chips.html | cron | db | scripts

## Context
- Required docs reviewed:
  - `docs/handoff_chatgpt.md`
  - `docs/chatgpt_debug/README.md`
  - `docs/chatgpt_debug/2026-09-03-01-full-project-review.md`
- Additional code reviewed:
  - `public/chips.html`
  - `src/chip_rank.py`
  - `C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\run_daily.ps1`
  - `C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\render_full_watchlist.py`
  - `C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\watchlist.py`
  - `C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\sync_legacy_tables.py`
  - `C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\cross_source_runner.py`
  - `C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\render_only.py`
  - `C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\finmind_batch.py`
  - `C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\yfinance_batch.py`
- Verification performed without changing product code or DB data:
  - Both executable inline scripts in `public/chips.html` passed `node --check`.
  - Read-only DB query on 2026-09-03 found `market_screen_picks.status='active'` count = **0**.
  - Latest three screen runs were dated 2026-09-01, 2026-08-31, and 2026-08-12; each says 24 picks.
  - Both repo and Groove-Lab `watchlist.html` were still titled `Watchlist · 2026-09-02`, with mtime 2026-09-02 15:59:48.
  - `daily_run_20260902.log` recorded margin timeout, watchlist “No active picks” with exit 0, OG failure, ticker-meta timeout, then a successful publish to the old `stock-report` repo and a final “Done”.
- Important source-of-truth observation: `src/chip_rank.py` contains the correct `rows.forEach(...)`, while the currently generated `public/chips.html` contains a no-op function expression. Fix the generator/patch chain and regenerate; do not patch only the generated HTML.

## Review of Mavis F1-F6

| Original | Verdict | Corrected priority | Reason |
|---|---|---:|---|
| F1 D044 may have un-stubbed D032 references | **Disagree with the stated finding** | remove; replace with R3/R4 below | The two real inline scripts parse, the known removed D032 functions are stubbed, and `wiz-sub3a` is dynamically created. No concrete null `addEventListener` failure was established. There are different D044 regressions: sorting is inert and industry choices are empty. |
| F2 wizard recommendations use the first three | **Partly agree** | mid | Insertion order plus `slice(0, 3)` can starve later personas. However, the example saying bullish-long and bullish-short return the same three is incorrect because style tags do filter the list first. This is ranking quality, not data correctness. |
| F3 saved strategy is not auto-applied after reload | **Disagree** | remove; optional low UX enhancement | `saveFilter()` persists `APPLIED` to `tank-akali-filters-v1`, and `loadFilter()` restores both `PENDING` and `APPLIED`. The applied behavior already survives reload. Remembering the strategy's display name is separate and must not duplicate filter state. |
| F4 watchlist may lag one day | **Agree, but diagnosis and fix are incomplete** | **critical** | This is not merely a one-day render lag. There are zero active picks; the renderer exits successfully without output; the nightly flow does not atomically create a new 24-pick run; and the previous artifact is left in place. |
| F5 analyze pages lack D044/D045 D-codes | **Disagree** | remove | D044/D045 are chips-page decisions, not a contract that every ticker HTML must contain those markers. Re-render ticker pages only when their renderer/data contract changes. A full 1,962-page rerender for chips-only UI changes wastes an hour and increases deployment risk. |
| F6 tab counts are not filter-aware | **Disagree / already implemented** | remove | `renderApplied()` updates each `.tab .cnt` from the APPLIED result (`public/chips.html:7897-7915`). Counts should not react to uncommitted `PENDING` state because the UI intentionally separates preview from applied state. |

## Corrected Priority Order

| Order | Finding | Priority | Why first |
|---:|---|---|---|
| 1 | R1 watchlist rotation can leave zero active picks and stale HTML | critical | User-facing 24-pick product is not being produced. |
| 2 | R2 daily batch reports success and publishes after required failures | critical | Scheduler/result labels cannot be trusted and stale/partial artifacts can be published. |
| 3 | R3 chips sorting is inert in the generated page | high | A primary visible control does not perform its advertised action. |
| 4 | R4 industry selection has no options | high | Persona/wizard branches that request an industry cannot actually select one. |
| 5 | R5 redirected child output can deadlock `Run-Stage` | high | Long/noisy jobs can hang before timeout handling can complete reliably. |
| 6 | R6 cross-source provenance and dividend units are unreliable | mid | Verification output can claim a failed DB source and emit false dividend discrepancies. |
| 7 | R7 render-only network policy and partial-result policy are ambiguous | mid | “No yfinance/no news” can still make FinMind calls; per-ticker failures can still become rendered pages. |
| 8 | R8 wizard recommendation ranking is order-dependent | mid | Recommendation quality is not explicitly tied to user intent. |
| 9 | R9 generated HTML and batch diagnostics contain stale/dead code | low | Does not cause the main outage, but makes future debugging misleading. |

## Findings

### R1. Watchlist lifecycle is not an atomic daily rotation
- **Files**:
  - `C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\run_daily.ps1:296-297`
  - `C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\render_full_watchlist.py:1746-1756,1767-1773,1907-1915`
  - `C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\sync_legacy_tables.py:142`
- **Issue**:
  - `render_full_watchlist.py` first loads old rows with `status='active'`; with none, it prints “No active picks” and returns exit 0.
  - Re-running `screen_market()` only supplies fresh `Candidate` details for those old active rows. It does not save a new run or new picks.
  - The legacy sync later closes all active rows. The current DB therefore has zero active picks, while stale HTML remains visible.
  - A partial ticker/horizon match can also silently produce fewer than 24 rendered picks.
- **Implementation steps**:
  1. Pick one canonical daily orchestration point after the required market/legacy data is current. Do not render the watchlist before its input rotation.
  2. In one transaction: run the screen, validate exactly 24 unique picks and required long/short/bucket composition, insert `market_screen_runs`, insert its picks, and only then close the prior active run.
  3. Roll back on any validation/write failure so the last known-good active run remains available.
  4. Pass an explicit `run_id` into performance calculation and rendering. Do not use “all active rows” as an implicit version selector.
  5. Make “no picks”, fewer than 24 matched candidates, or mismatched `run_date` return non-zero and leave existing HTML untouched.
  6. Render once, then copy the same artifact to repo `public/watchlist.html` and `C:\Groove-Lab\watchlist.html`; verify both titles contain the DB latest trading date.
  7. Gate publishing on these postconditions: one active run, 24 active picks, run date = latest valid trading date, repo/Groove artifacts agree.
- **Priority**: critical

### R2. `run_daily.ps1` can publish and report complete after required failures
- **File**: `C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\run_daily.ps1:346-364,375-382`
- **Evidence**: On 2026-09-02, margin scan timed out, watchlist produced no picks, OG generation failed, and ticker-meta timed out. The loop continued, Stage 99 pushed only the old `stock-report` repo, and the script wrote final state `complete/done`.
- **Issue**: Task Scheduler exit 0 and the status file are false-positive completion signals. The separate 23:50 publisher can then push a partial or stale C/Git worktree.
- **Implementation steps**:
  1. Classify stages as required or optional and collect structured results: name, exit code, timeout, duration, and artifact postcondition.
  2. Stop before dependent stages and publishing when any required stage fails. Optional failure may continue but final state must be `degraded`, not `done`.
  3. Return a non-zero process exit code for failed required stages; write a final failure summary listing every failed/skipped stage.
  4. Replace/remove Stage 99 `publish_analyze_ghpages.py` for this pipeline. The canonical site publisher is repo `scripts/publish_ghpages.py`; do not treat publishing the old `stock-report` repo as tw-invest-suite success.
  5. Let the 23:50 publish task require a same-trading-date success marker produced only after all artifact gates pass. If the marker is absent, publish nothing and exit non-zero.
  6. Calculate total stage count dynamically and report each stage's real timeout. Fix elapsed-time calculation with explicit date arithmetic so the one-hour run cannot report `0m0s`.
- **Priority**: critical

### R3. Sort dropdown computes an order but never applies it
- **Files**:
  - `public/chips.html:7610-7652`
  - `src/chip_rank.py:675-680`
- **Issue**: Generated HTML ends the branch with `}(function (r) { grid.appendChild(r); });`. This creates an unused function expression instead of iterating `rows`, so shuffle and all non-default sorts leave DOM order unchanged. The canonical generator currently has the correct `rows.forEach(...)`, proving artifact/patch drift.
- **Implementation steps**:
  1. Identify the post-render patch or copy step that transforms the generator's correct line into the generated no-op; fix that canonical source/order first.
  2. Regenerate `public/chips.html` through the normal pipeline. Do not hand-edit only the 400KB artifact.
  3. Verify on at least two card tabs and the depth table that price ascending, price descending, one score sort, and shuffle visibly change the first rows.
  4. Apply a persona filter and verify the chosen sort remains effective after `renderApplied()` rebuilds cards.
  5. Sync the verified artifact to Groove-Lab only after repo output passes these checks.
- **Priority**: high

### R4. Persona and wizard industry selectors depend on removed D032 UI
- **File**: `public/chips.html:7972,8164-8168,8457-8464`
- **Issue**: `buildIndustryList()` is a stub and `#filter-industry` no longer exists, but both new selectors copy their options from `#filter-industry option`. They therefore contain only “全部產業”. No exception is thrown, so a console-only null check would miss this functional regression.
- **Implementation steps**:
  1. Create one canonical `getIndustryOptions()` source from loaded `TICKER_DATA`/`chips.json` values, normalized and sorted; do not depend on removed filter-panel DOM.
  2. Use it to populate both `persona-industry-sel` and `wiz-ind-sel`.
  3. Disable or defer opening the industry question until `chips.json` has loaded, and show an explicit load/error state.
  4. Verify selecting a real industry changes `PENDING.industry`, the preview count, and the APPLIED card/count results.
- **Priority**: high

### R5. `Run-Stage` waits before draining redirected output
- **File**: `C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\run_daily.ps1:161-186`
- **Issue**: stdout and stderr are redirected, but `WaitForExit()` runs before either stream is drained. A verbose child can fill an OS pipe buffer and block while the parent waits, producing an apparent hang or misleading timeout.
- **Implementation steps**:
  1. Drain stdout and stderr concurrently from process start, using asynchronous handlers/tasks or an equivalent non-blocking pattern.
  2. Preserve line-at-a-time logging and retain both streams until process exit.
  3. On timeout, kill the full child process tree, await stream completion for a bounded interval, and record timeout separately from application exit.
  4. Verify with an existing verbose production stage/log path; do not add a new test script.
- **Priority**: high

### R6. Cross-source provenance and dividend verification can be false
- **Files**:
  - `C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\cross_source_runner.py:97-100,180-200`
  - `C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\render_ticker_full.py` (dividend display normalization)
- **Issue**:
  - `_db_basic()` may return `_db_err`, but `assemble()` unconditionally appends `db` to `_meta.sources`.
  - Cross verification always multiplies yfinance dividend yield by 100, while the renderer already handles both fraction and percentage-shaped values. This inconsistency can generate false >5% discrepancies.
- **Implementation steps**:
  1. Define one internal unit contract for every cross-verified metric; for dividend yield, choose either fraction or percentage points and normalize at each adapter boundary.
  2. Store normalized value plus provider/raw value metadata when needed for diagnosis.
  3. Append a source only after a successful usable response; put provider errors in a separate structured `_meta.errors` list.
  4. Reuse the same normalizer for rendering and verification, including FinMind fallback data.
  5. Make verification log writes safe if `assemble()` is later parallelized, and include provider timestamps so stale-vs-current comparisons are distinguishable.
- **Priority**: mid

### R7. “Render-only” has no explicit offline/cache-only contract
- **Files**:
  - `C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\render_only.py:45-104`
  - `C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\cross_source_runner.py:102-174,208-227`
- **Issue**: `--no-yfinance --no-news` disables only those two calls. `assemble()` still invokes FinMind PE, dividend, financial, and revenue fetchers, which make network calls on stale/missing cache. Per-ticker exceptions are converted to `_err`, but rendering can still count a degraded page as successful.
- **Implementation steps**:
  1. Replace independent booleans with an explicit source policy such as `online`, `cache-preferred`, or `offline`; `offline` must never call a provider.
  2. Return per-source state (`fresh_cache`, `stale_cache`, `live`, `missing`, `error`) and required-field completeness.
  3. In daily render, define an allowed degraded threshold. Fail the stage when failures/missing required fields exceed it; do not report all pages healthy merely because HTML files were written.
  4. Keep FinMind maintenance/fetch in its own stage so API quota, duration, and failure are observable separately from HTML rendering.
- **Priority**: mid

### R8. Wizard recommendation ranking is insertion-order dependent
- **File**: `public/chips.html:8522-8556`
- **Issue**: Direction and style remove candidates, but the final three come from hardcoded object order and `slice(0, 3)`. Adding/reordering personas can silently change recommendations without a product decision.
- **Implementation steps**:
  1. Define an explicit recommendation matrix or score table keyed by `(direction, style, persona)`.
  2. Rank by score, then use one documented deterministic tie-breaker.
  3. Validate every supported direction/style combination returns three unique keys that exist in `PERSONAS`; define a fallback for sparse combinations.
  4. Keep `STYLE_TAGS`, persona definitions, and recommendation metadata in one source of truth so tags and ranking cannot drift.
- **Priority**: mid

### R9. Dead generated HTML and stale batch contracts obscure diagnosis
- **Files**:
  - `public/chips.html:8844-8861`
  - `C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\run_daily.ps1:1-19,126-146,158,219-227`
- **Issue**:
  - Duplicate `sum-reshuffle`/`sum-save` code sits outside `<script>` after line 8842, followed by a stray `</script>`. The valid handlers already exist earlier, so this is dead visible text/markup debris.
  - Batch comments and labels still describe five stages, and weekend `SkipYfinance`/`SkipFinmind` toggles no longer control the current 17-stage list. `Is-TradingDay` is not used as a release gate.
- **Implementation steps**:
  1. Remove the out-of-script duplicate from the canonical template/patch source, then regenerate.
  2. Derive stage count, timeouts, and mode descriptions from the actual stage list.
  3. Remove obsolete switches or wire them to explicit current stages; do not leave no-op operational controls.
  4. Base “current day” release gates on the latest valid TWSE trading date, not Monday-Friday alone.
- **Priority**: low

## Out of Scope
- No implementation, commit, push, deploy, DB mutation, or new test script was performed in this manager review.
- Do not bulk re-render all ticker pages merely to add D044/D045 labels. Establish a renderer/template version and rerender only when that contract changes.
- Move hardcoded DB credentials out of runtime source into one local secret/config mechanism; redact them from logs. This is worthwhile but should not delay R1/R2 recovery.
- Document why the C-path checkout resolves through Git to the E-path top-level on this machine. Treat them as an alias only after verifying the same worktree/HEAD; otherwise root confusion will cause false deployment conclusions.
- Browser regression automation should eventually check visible behavior (sort order, industry options, 24 watchlist picks), but this task explicitly does not add test scripts.
- Google Sites hosting/deployment is separate from this code audit. Preserve the existing layout by serving the static site directly and linking to it rather than rebuilding it inside Google Sites.

---

## Status
*(MiniMax/Mavis should append results only after Walter explicitly approves an implementation batch.)*
