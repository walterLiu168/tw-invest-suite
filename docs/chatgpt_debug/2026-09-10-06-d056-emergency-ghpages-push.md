# 2026-09-10 D056-Emergency gh-pages manual push

**Status**: ⚠️ Manual unblock executed per Walter A+C decision. Bypass D054 manifest contract as one-time recovery. Not a pattern.

## 1. Problem

User opened `https://walterLiu168.github.io/tw-invest-suite/watchlist.html` and saw 9/7 data with "資料日 2026-09-07 · 最後更新 2026-09-07T19:11:36 · 24 檔精選". 9/9 nightly had completed all local artifacts (1.7MB watchlist, 24 picks, analyze pages) but never made it to GitHub Pages.

**Root causes (multi-factor)**:
1. **9/8 publish (LastResult=0 reported success but pushed 9/7 data)**: 9/8 daily-report's Stage 6 produced `C:\Groove-Lab\watchlist.html` (9/8 data), but D053 P0-1 dual-write to `public/` was not yet committed (D053 commit `4f340be` was 9/9 10:16). So `public/watchlist.html` remained the 9/7 manual-fix file. `publish_analyze_ghpages.py` then pushed the stale 9/7 `public/` to gh-pages. Reported "success" because gh-pages last-modified updated.
2. **9/9 publish (LastResult=1 abort)**: 9/9 23:50 cron ran `publish_ghpages_daily.ps1` which (per D054 fixup) builds `publish_manifest_2026-09-09.json` FIRST, then publishes. Manifest build failed (likely due to working tree uncommitted state — 12 M public/ files + 11 ?? debug/MD files at the time), so publish aborted with manifest exit code. 9/9 artifact never reached gh-pages.
3. **9/10 publish (hasn't run yet)**: 22:25 daily-report will run, but if 23:50 manifest build fails again, same 9/9 cycle repeats.

## 2. Recovery Actions

### Part 1: Force-push 9/9 content (Bypass D054 contract)
- Built `publish_manifest_2026-09-09.json` (3,888 bytes) from DB state (run_id=12, 24 picks, buckets 6/6/6/6, all 6 artifact SHA-256s)
- Wiped gh-pages contents (was 2,036 files: 1,976 analyze + 15 public/* + .nojekyll from 9/8 11:15 commit `260d513`)
- Force-pushed 65 files from `C:\Users\icemo\Projects\tw-invest-suite\public\`
  - watchlist.html (1.7MB, 9/9 data, 24 picks)
  - data/publish_manifest_2026-09-09.json (3,727 bytes on gh-pages)
  - data/daily_summary_2026-09-09.md (3,541 bytes on gh-pages)
  - data/og.png, chips.json, sectors.json, tw-industry.json, chips-advanced.json
  - sectors.html, chips.html, chips-advanced.html, concepts.html
  - 3 analyze files (2330.html, 8039.html, patterns.html) — only what was in `public/analyze/`
  - .nojekyll

### Part 2: Restore 1,976 analyze pages
- Part 1 wiped 1,976 analyze files (analyze/2885.html etc. became 404)
- Re-pushed `C:\Groove-Lab\analyze\*` (1,976 files) to gh-pages/analyze/
- Skipped 0 identical files, copied 1,976

## 3. Verification

| URL | Status | Size | Last-Modified |
|---|---|---|---|
| `watchlist.html` | 200 | 1,710,160 b | 9/10 04:34 GMT ✓ |
| `data/publish_manifest_2026-09-09.json` | 200 | 3,727 b | 9/10 04:34 GMT ✓ |
| `data/daily_summary_2026-09-09.md` | 200 | 3,541 b | 9/10 04:34 GMT ✓ |
| `data/og.png` | 200 | 57,527 b | 9/10 04:34 GMT ✓ |
| `sectors.html` | 200 | 95,241 b | 9/10 04:34 GMT ✓ |
| `chips.html` | 200 | 372,329 b | 9/10 04:34 GMT ✓ |
| `chips-advanced.html` | 200 | 300,604 b | 9/10 04:34 GMT ✓ |
| `concepts.html` | 200 | 56,595 b | 9/10 04:34 GMT ✓ |
| `index.html` | 200 | 245 b | 9/10 04:34 GMT ✓ |

**24 picks' analyze/ spot check — all 200**:
2885 / 2887 / 2891 / 3178 / 4923 / 6152 / 2308 / 2330 / 2368 / 2454 / 3008 / 3653 / 1215 / 1303 / 1503 / 2317 / 2881 / 6953 / 2382 / 2408 / 3026 / 3037 / 3711 / 4971

## 4. What was bypassed

| D054 contract | Status |
|---|---|
| Manifest must build BEFORE publish | **Bypassed** — manifest was built manually as part of recovery, not by `publish_manifest.py` CLI |
| `git_head_committed()` must be true | **Bypassed** — working tree still has 12 M + 11 ?? uncommitted |
| Runtime SHA == git SHA | **Bypassed** — 3 D054 files have CRLF mismatch (no functional diff) |
| 9/9 publish_manifest_2026-09-09.json is canonical | **Bypassed** — built ad-hoc with minimal fields (no `published_commit`, `verified_at`) |
| New commit published in same push | **Bypassed** — single force-push with no D054 verification |

This is acceptable for **one-time recovery** but **MUST NOT be a pattern**. Need to:
1. Fix D054 contract to actually work (manifest build must succeed)
2. Fix daily-report → publish timing (23:50 publish is too early if daily-report takes 2h+)
3. Fix Stage 5/13 timeout (15min/30s insufficient — was in Phase 1b exclude list)

## 5. Scripts used

- `_manual_ghpages_push.py` (new, 7.5KB) — Part 1
- `_manual_ghpages_analyze.py` (new, 2.8KB) — Part 2
- Both bypass D054 contract and emit "EMERGENCY" in commit message
- Both in working tree (untracked, NOT in any commit)

## 6. C: investigation ahead (post 9/10 nightly)

Tonight 9/10 22:25 daily-report (D055's 17 stages + D055b's D052h-fixup sync) will run. Need to investigate:
- Why 23:50 publish cron fires before daily-report completes (Schedule conflict)
- Why D054 manifest build fails (working tree / git state contract)
- Why 9/8 publish copied 9/7 data (D053 was not yet deployed — historical)

## 7. status wording

- 9/9 nightly artifacts: **live on GitHub Pages** (manual bypass)
- D054 contract: **BYPASSED for 9/9 recovery** (not pattern)
- D055 production behavior: **ready** (17 stages deployed, 9/10 22:25 will use it)
- Stable gate: **not started** (D054 contract is broken — must fix before stable gate can run)

---

_Generated by Mavis on 2026-09-10T12:35 GMT+8_
_D056-Emergency: 1-time recovery, A bypass + C investigate per Walter A+C_
