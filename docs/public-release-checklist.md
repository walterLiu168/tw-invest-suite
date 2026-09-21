# Public Release Checklist

版本：2026-09-21
Release owner：Project Manager
目前判定：**Operationally certified；source release ready after final verification**

## A. 已完成的營運驗收

- [x] `daily_data2_full` full-table null/negative/duplicate audit passed。
- [x] Latest certified date has 1,958 rows / 1,958 distinct tickers。
- [x] `nightly_id=51fa87e75ca748b28f3bc4921901bae4`、`data_date=2026-09-18`、`run_id=25` recorded。
- [x] Required stages and all reports certified。
- [x] GitHub remote SHA and status commit verified。
- [x] Groove remote verified `2038/2038`。
- [x] Telegram chips delivery verified with positive `message_id=1397` and idempotent retry。
- [x] Scheduler tasks read back with WakeToRun/StartWhenAvailable enabled。
- [x] `pipeline_state.py verify`、acceptance summary、compile audit passed。

## B. Public release blockers

### B1. Secret and credential scrub

- [x] Remove hardcoded local DB password defaults from production Python and replace with environment/Credential Manager resolution.
- [x] Sanitize tracked historical docs and audit files; repository-wide secret scan is required again immediately before push.
- [x] Verify no Telegram bot token, chat id, FinMind token, LLM key, GitHub credential or local config is tracked (tracked-file scanner: zero hits).
- [x] Rotate the legacy DB credential that appeared in the public source history; the new value is stored only in protected user environment variables.

### B2. Reproducible installation

- [x] Add public core and optional dependency requirement files for Python 3.14-compatible packages.
- [x] Document MySQL schema installation and non-secret configuration.
- [x] Separate optional private AI-Telegram/OpenAlice integration from the public core package and describe its environment boundary.
- [ ] Replace private absolute paths with configuration or fail-fast setup checks.
- [ ] Add a clean-machine smoke test that renders a small ticker sample without private caches.

### B3. Public legal/product boundary

- [x] Record upstream notices for yfinance and Chart.js; document that FinMind/data redistribution remains plan-dependent.
- [x] Add a visible “research only / not financial advice / no order execution” notice.
- [x] Document data-provider attribution and rate limits.
- [ ] Decide whether public releases include historical raw data, only generated artifacts, or neither.

### B4. Operational release gate

- [ ] Run one fresh scheduled cycle after the public commit.
- [ ] Verify the public URL from an external network and check cache headers.
- [ ] Verify Telegram delivery in the new release without sending duplicate content.
- [ ] Archive the exact marker, manifest, remote commits, postflight and scheduler readback.
- [ ] Obtain explicit release approval from the owner after the above blockers are cleared.

## C. Release procedure after blockers clear

```text
1. Freeze source and record git diff.
2. Run secret scan and dependency/license audit.
3. Run compileall + unit tests + prepare-only publication.
4. Run a clean-machine smoke test.
5. Commit only reviewed source/docs/config templates.
6. Publish GitHub Pages and verify remote SHA/manifest.
7. Sync Groove stock paths and verify all remote hashes.
8. Run postflight.
9. Send one dated Telegram summary through the existing idempotent sender.
10. Save release evidence and publish the release notes.
```

## D. Rollback criteria

Rollback or stop publication immediately if any of these occurs:

- secret scan finds a credential;
- source hash differs during a nightly;
- data date is stale, future, or disagrees with expected session;
- selected picks or report artifacts do not match the certified UUID;
- remote SHA verification fails;
- Telegram response is uncertain or targets a different chat;
- a public build requires private files that are not documented as optional.

## E. Evidence files

- `.codex-work-state/data-code-integrity-audit-20260919.md`
- `.codex-work-state/self-complete-status.md`
- `_debug/last_completed.json`
- `_debug/publication_result.json`
- `_debug/postflight_latest.json`
- `analyze/render_receipt.json`
- `public/data/publish_manifest_2026-09-18.json`

These files prove the current local deployment. They do not replace a clean public-release rehearsal.
