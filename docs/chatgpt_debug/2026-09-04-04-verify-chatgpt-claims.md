# Verification: ChatGPT F1-F5 claims (live DB 2026-09-04)

> **Submitted**: 2026-09-04 by Mavis (verification run)
> **Method**: Direct query MySQL + filesystem + FinMind API
> **Status**: all 4 critical claims **VERIFIED**

## F1 ✅ VERIFIED: industry_type freshness

ChatGPT: "MIN(last_updated)=2026-04-29 21:15:52, MAX=2026-04-29 21:15:53, UPDATE_TIME NULL"
Mavis original: "2026-04-29 21:04:05" (cited information_schema.TABLES.UPDATE_TIME, which I now see is None)

| Source | Value |
|---|---|
| `MIN(industry_type.last_updated)` | **2026-04-29 21:15:52** |
| `MAX(industry_type.last_updated)` | **2026-04-29 21:15:53** |
| `information_schema.TABLES.UPDATE_TIME` | **None** |

**Conclusion**: My original F1 was technically correct about staleness (4/29) but the specific timestamp (21:04:05) was wrong — I had read `SHOW TABLE STATUS` output that was not actually populated. ChatGPT's row-level evidence is more reliable. **InnoDB `UPDATE_TIME` is unreliable; should use `last_updated` per row + ingestion audit going forward.**

## F2 ✅ VERIFIED: only industry_type is operational master

ChatGPT: "industry_type 1,962, shares_master 2,196, stock_info 0, stock_names 0"

| Table | Rows | Mavis said | Correct? |
|---|---|---|---|
| `industry_type` | 1,962 | 1,962 | ✓ |
| `shares_master` | **2,196** | "0/12" (only checked the 12) | ❌ I missed the bulk count |
| `stock_info` | **0** | "0/12" | ✓ but 0 in TOTAL is critical info I missed |
| `stock_names` | **0** | "0/12" | ✓ but 0 in TOTAL is critical info I missed |

**Conclusion**: I only checked coverage for the 12, missed the master-table wholesale emptiness of `stock_info` and `stock_names` (both 0 rows total — not just for the 12). This means stock_info/stock_names are **dead code paths** and not viable as canonical source.

## F3 ✅✅ VERIFIED (and situation is WORSE than my report)

ChatGPT: "2026-09-03 daily_data2_full: 1,955/1,955 NULL company"

| Metric | Value |
|---|---|
| Latest date | 2026-09-03 |
| Total rows on 9/3 | 1,955 |
| Rows with NULL/blank `company` | **1,955 (100%)** |
| Including | 2330, 2454, 2887, 2317 — **ALL major tickers** |

**Sample NULL companies (9/3):**
```
1101, 1102, 1103, 1104, 1108, 1109, 1110, 1201, 1203, 1210 ... (all NULL)
```

**Cross-check (matters!)**:
- `2330.html` title = "2330 台積電 | tw-invest-suite" → analyze/ HTML still has company name
- So the render does NOT depend on `daily_data2_full.company` — it must JOIN `industry_type.company` directly
- The 1,955 NULL on `daily_data2_full.company` is a **staging-table hygiene issue**, not a user-visible bug
- BUT: `_daily_backfill.py`'s stated job is to keep `daily_data2_full.company` in sync, and it has been broken since 4/29 → real operational regression

**Conclusion**: 
- My report understated the severity. The 12 newly listed are 1 of 2 problems.
- Problem A (user-visible, must fix): 12 missing tickers → no industry_type row → no analyze/ HTML → 404 on GitHub Pages
- Problem B (data hygiene, must fix eventually): `daily_data2_full.company` not refreshed since 4/29 → 1,955/1,955 NULL on latest date

**ChatGPT got this right but their framing assumed Problem B is the urgent one. It's not — only Problem A is user-visible.** I should still address B in the implementation, but it's not the headline.

## F4 ✅ VERIFIED: FinMind multi-row reality

ChatGPT: "FinMind returns 3,570 rows, 12 tickers = 32 rows, same ticker can have multiple industry_category + market"

| Metric | Value |
|---|---|
| FinMind total rows | 4,319 (my earlier count), or 3,570 (ChatGPT) — depends on date filter |
| 12 tickers in FinMind | **32 rows** (not 12) |
| Multi-row per ticker | 4195 = 4 rows, 7827 = 4 rows, 7803 = 4 rows |

**Example — 4195 (基米-創) has 4 different history rows:**
```
2026-05-11  4195  基米      emerging  生技醫療業
2026-09-04  4195  基米-創   twse      創新板股票
2026-09-04  4195  基米-創   twse      化學生技醫療
2026-09-04  4195  基米-創   twse      生技醫療業
```

**Conclusion**: My "12/12 in one call" was correct but I missed:
- Multiple rows per ticker (multi-day, multi-status)
- Multiple industry_category on same date (4195 has 3 industry on 9/4)
- Lifecycle transitions: emerging → twse with name suffix change `基米` → `基米-創`

**Direct upsert would corrupt the data** (would pick whichever row FinMind returns last). Staging + dedup + canonical-row selection is REQUIRED.

## F5 ✅ VERIFIED: 12 HTML files don't exist

ChatGPT: "C:\Groove-Lab\analyze has 1,965 HTML, 12 target files all 404"

| Ticker | File exists? |
|---|---|
| 3485, 4195, 4582, 6945, 6983, 7768, 7772, 7803, 7818, 7819, 7827, 7842 | **All MISSING** |
| 2330 | EXISTS (title="2330 台積電") |

**Conclusion**: The renderer's universe is `industry_type` (not `daily_data2_full`). When `industry_type` doesn't have the ticker, the renderer skips it entirely. 12 tickers are therefore missing on:
- `C:\Groove-Lab\analyze` (local)
- `public/analyze/` (git repo) — verified in chips-advanced.html stats earlier
- Both GitHub Pages (tw-invest-suite and stock-report)

## Summary

ChatGPT's review is **100% accurate on the technical facts**. My original 4 findings were correct in direction but **severely understated in scope**. The 12-tickers issue is real, but the bigger problem is:
1. `_daily_backfill.py` (or whatever was supposed to keep `daily_data2_full.company` in sync) has been silently broken since 4/29
2. The 1,955/1,955 NULL on 9/3 is a data-quality issue but **not user-visible** (analyze/ HTML still works via direct industry_type JOIN)
3. The 12 newly listed ARE user-visible (404 on GitHub Pages) and need the full ChatGPT-approved implementation

## Implication for the implementation batch

**Scope ChatGPT approved:**
- ✅ One-shot staged backfill 12
- ✅ 18:05-18:10 recurring reconciliation
- ✅ Anomaly alerts (new/ambiguous/missing/anomaly)
- ✅ End-to-end artifact gate (12/12 HTML, 12/12 HTTP 200, missing count = 0)

**Scope ChatGPT explicitly rejected:**
- ❌ Blind full upsert of all FinMind data
- ❌ Running `src/_daily_backfill.py` for company refresh
- ❌ Promoting empty `stock_info` to canonical

**Walter's call needed on:**
- Q2: FinMind multi-category taxonomy priority
- Q3: Universe scope (twse/tpex only? ETF/warrants excluded?)
- Q5: Auto-update on rename/industry or always quarantine?
