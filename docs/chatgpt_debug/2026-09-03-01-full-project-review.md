# 2026-09-03-01: Full project review (D042-D048)

> Submitted: 2026-09-03 by ChatGPT
> Status: pending
> Scope: full-project

## Context
- Reviewed all D042-D048 commits (chips.html 4-step wizard → 3-step wizard + persona reorder + 風格標籤 → 拿掉我的篩選 + 加強 store UI → backfill 9/1 → cron 23:30 sync_legacy → cron 22:30 yfinance + 23:50 publish_ghpages)
- Live at https://walterliu168.github.io/tw-invest-suite/ + https://groovelab.dev/
- 16 persona cards (D043) + 3-step wizard + store UI (D044) all live

## Findings

### F1. chips.html D044 may have un-stubbed D032 references
- **File**: `public/chips.html`
- **Issue**: D044 removed 4 filter panel HTML rows, but only stubbed 5 D032 JS functions. Other D032 elements (`fchip`, `fchip[data-tag="concept"]`, `fchip[data-preset]`, `mode-toggle`, `adv-cond`) may still be referenced by addEventListener calls in code I haven't seen.
- **Suggested fix**: Run `python -m http.server` on public/ and open chips.html in a headless browser (Playwright). Capture all `Cannot read property 'addEventListener' of null` errors in console. Add stubs for any remaining.
- **Priority**: high

### F2. Wizard Step 3 (recommend) — pick 3 may not match user's intent
- **File**: `public/chips.html` renderWizardStep recommend branch
- **Issue**: `getRecommendedPersonas(direction, style)` returns first 3 from a hardcoded `pMap`. If user picks 「看多 + 長期」, they get same 3 as 「看多 + 短線」 filtered by tag, but AQR/法人鎖碼 are tagged `[波][長]` so they show up. User may want NEW 3 推薦 per combination, not the top 3 of the master list.
- **Suggested fix**: Add a `score` per persona per (direction, style) combo in pMap, e.g. ws_moat scores higher for (long, long), ws_jt scores higher for (long, short).
- **Priority**: mid

### F3. store UI doesn't persist "last filter" across reloads
- **File**: `public/chips.html` loadSavedStrategy
- **Issue**: Clicking 套用 on a saved strategy works, but on page reload user has to click 📂 我的策略 → pick again. No auto-apply on load.
- **Suggested fix**: Store `tank-akali-last-applied-strategy` in localStorage, on page load if it's set, auto-apply.
- **Priority**: mid

### F4. watchlist.html data date may lag by 1 day
- **File**: `public/watchlist.html` + cron
- **Issue**: `render_watchlist_html.py` uses `latest_date("daily_data2_full")` but doesn't refresh on 22:25 daily run. Manual re-render is needed. The new 23:50 publish cron will push stale 24 picks.
- **Suggested fix**: Add a stage in `run_daily.ps1` to re-render watchlist.html after market_screen update. Or add a `watchlist_render` cron at 22:30.
- **Priority**: high

### F5. analyze/ 1,961 HTML pages don't have D044/D045 D-codes
- **File**: `public/analyze/0001.html` to `9999.html`
- **Issue**: D044 changes (no 我的篩選 + store UI on chips.html) don't propagate to individual stock analysis pages. Each analyze page is server-rendered with old HTML.
- **Suggested fix**: Re-render analyze/*.html after chips.html D-codes change. Add a stage to `run_daily.ps1` or run `render_ticker_db_only.py` for all 1,962 tickers.
- **Priority**: low (low impact since main chips.html works)

### F6. chips.html tabs count is not PENDING-filtered
- **File**: `public/chips.html` buildCard
- **Issue**: Tab counts (全部買超 1000, 同買 34, etc) are static numbers from chips.json, not reflecting the current PENDING filter state. After user picks persona and filter, tab counts don't change.
- **Suggested fix**: Move tab count to a JS function that recomputes from current APPLIED filter.
- **Priority**: low (UX, not data)

## Out of Scope
- 1,961 analyze/ HTML files (low impact)
- FinMind PE/News cache 0% (workaround via yfinance cron already in place)

---

## Status
*(Mavis will append when done)*
