# Daily Closed-Loop Summary — 2026-09-21

**Status**: ❌ FAIL  
**Execution date**: 2026-09-21  
**Data date**: 2026-09-21  
**Phase**: after_publish  
**Generated at**: 2026-09-22T08:29:03.366065  
**Source commit**: `3cca0eaac5a7d2639bfa4828c61513435dc971fc`  

## DB integrity

- Total rows: **1964**
- Company NULL: **0** (none)
- Open quarantine: **0** (0 distinct ticker(s))

## 24 picks

- run_id: **28**
- picks_count: **24**
- buckets:
  - 100-300: 6
  - 300-1000: 6
  - <100: 6
  - >1000: 6
- tickers:
  - `2885` 元大金 (<100)
  - `2887` 台新新光金 (<100)
  - `2891` 中信金 (<100)
  - `3219` 倚強科 (<100)
  - `3339` 泰谷 (<100)
  - `4590` 富田-創 (<100)
  - `2308` 台達電 (>1000)
  - `2330` 台積電 (>1000)
  - `2330` 台積電 (>1000)
  - `2360` 致茂 (>1000)
  - `2454` 聯發科 (>1000)
  - `3653` 健策 (>1000)
  - `1303` 南亞 (100-300)
  - `2303` 聯電 (100-300)
  - `2317` 鴻海 (100-300)
  - `2881` 富邦金 (100-300)
  - `3035` 智原 (100-300)
  - `8150` 南茂 (100-300)
  - `2376` 技嘉 (300-1000)
  - `2382` 廣達 (300-1000)
  - `2408` 南亞科 (300-1000)
  - `2449` 京元電子 (300-1000)
  - `3711` 日月光投控 (300-1000)
  - `3711` 日月光投控 (300-1000)

## Cron results

| Cron | LastResult | ran_on_target | pass |
|---|---|---|---|
| tw-invest-suite-daily-report | `1` | ✓ | ✗ |
| tw-invest-suite-yfinance | `0` | ✓ | ✓ |
| tw-invest-suite-health-check | `0` | ✗ | ✗ |
| tw-invest-suite-sync-legacy | `0` | ✓ | ✓ |
| tw-invest-suite-company-refresh | `0` | ✓ | ✓ |
| tw-invest-suite-metadata-backfill | `0` | ✗ | ✗ |
| tw-invest-suite-market-screen | `0` | ✗ | ✗ |

## Other checks

- ✗ **completion**: state=failed, reason=marker/source SHA mismatch
- ✓ **market_screen**: run_id=28, picks_count=24, picks_total=24, picks_active=24
- ✓ **company_null**: total=1964, null=0
- ✓ **industry_count**: count=1974
- ✗ **publication**: receipt={'nightly_id': '486ad0d0d69b41ec9da2434a9c9f0bd8', 'data_date': '2026-09-21', 'run_id': 28, 'status': 'verified', 'published_commit': '8e1aaf65b341ef581b39abd3e112a3bff10eb8c3', 'verified_paths': ['analyze.html', 'analyze/1303.html', 'analyze/2303.html', 'analyze/2308.html', 'analyze/2317.html', 'analyze/2330.html', 'analyze/2360.html', 'analyze/2376.html', 'analyze/2382.html', 'analyze/2408.html', 'analyze/2449.html', 'analyze/2454.html', 'analyze/2881.html', 'analyze/2885.html', 'analyze/2887.html', 'analyze/2891.html', 'analyze/3035.html', 'analyze/3219.html', 'analyze/3339.html', 'analyze/3653.html', 'analyze/3711.html', 'analyze/4590.html', 'analyze/8150.html', 'analyze/patterns.html', 'analyze/patterns.json', 'assets/textsize.css', 'assets/textsize.js', 'chips-advanced.html', 'chips-history.html', 'chips.html', 'concepts.html', 'data/chips-advanced.json', 'data/chips-history-index.json', 'data/chips-history/2026-08-11.json', 'data/chips-history/2026-08-12.json', 'data/chips-history/2026-08-13.json', 'data/chips-history/2026-08-14.json', 'data/chips-history/2026-08-17.json', 'data/chips-history/2026-08-18.json', 'data/chips-history/2026-08-19.json', 'data/chips-history/2026-08-20.json', 'data/chips-history/2026-08-21.json', 'data/chips-history/2026-08-24.json', 'data/chips-history/2026-08-25.json', 'data/chips-history/2026-08-26.json', 'data/chips-history/2026-08-27.json', 'data/chips-history/2026-08-28.json', 'data/chips-history/2026-08-31.json', 'data/chips-history/2026-09-01.json', 'data/chips-history/2026-09-02.json', 'data/chips-history/2026-09-03.json', 'data/chips-history/2026-09-04.json', 'data/chips-history/2026-09-07.json', 'data/chips-history/2026-09-08.json', 'data/chips-history/2026-09-09.json', 'data/chips-history/2026-09-10.json', 'data/chips-history/2026-09-11.json', 'data/chips-history/2026-09-14.json', 'data/chips-history/2026-09-15.json', 'data/chips-history/2026-09-16.json', 'data/chips-history/2026-09-17.json', 'data/chips-history/2026-09-18.json', 'data/chips-history/2026-09-21.json', 'data/chips.json', 'data/concept-stocks.json', 'data/og.png', 'data/patterns.json', 'data/publish_manifest_2026-09-21.json', 'data/sectors.json', 'data/tickers.json', 'data/tw-industry.json', 'data/watchlist-full.json', 'deep-dive-prompts-2026-09-21.md', 'manifest.json', 'market-screen-2026-09-21.html', 'market-screen-2026-09-21.md', 'monitor.html', 'patterns.html', 'readme.html', 'sectors.html', 'sw.js', 'watchlist-full-2026-09-21.html', 'watchlist.html'], 'analytical_verified': True, 'report_status': 'verified', 'verified_at': '2026-09-22T08:22:17.191057', 'status_commit': 'e0151b5aafcd6124fcc575bae5da909060d5c5e7', 'verified_report_paths': ['data/daily_summary_2026-09-21.md', 'data/dashboard.md'], 'postflight_exit': 0, 'reports_verified_at': '2026-09-22T08:23:43.421069'}

## Artifacts

| Path | Size | SHA-256 (full) |
|---|---|---|
| `C:\Users\icemo\.claude\skills\tw-invest-suite\reports\market-screen-2026-09-21.md` | 16,189 B | `a9b205708c0e57f0c90c59fe69859991c109808f63f68d4a24097b583d50fe37` |
| `C:\Users\icemo\.claude\skills\tw-invest-suite\reports\market-screen-2026-09-21.html` | 140,086 B | `367263ae651426a9aeff011bcf0ac81460eb574f0b4a7219075294f2c37981e2` |
| `C:\Users\icemo\.claude\skills\tw-invest-suite\reports\deep-dive-prompts-2026-09-21.md` | 64,246 B | `123c85b2b775313d3d31624def23235f91d5e6d173661a86f1eba50431c7200a` |
| `C:\Users\icemo\.claude\skills\tw-invest-suite\reports\watchlist-full-2026-09-21.html` | 2,145,865 B | `46e5c03cbcf771ff38b8ebdb86b7b465ea41310214ce88882204d8958f682ea8` |

## Remote verify (GitHub Pages)

- ✓ **watchlist.html** — https://walterLiu168.github.io/tw-invest-suite/watchlist.html
  - status: `200`
  - content check: date_in_body=True, rows=24
- ✓ **analyze.html** — https://walterLiu168.github.io/tw-invest-suite/analyze.html
  - status: `200`
  - content check: page reachable
- ✓ **analyze/2885.html** — https://walterLiu168.github.io/tw-invest-suite/analyze/2885.html
  - status: `200`
  - content check: first_pick=2885, ticker_in_body=True
- ✓ **publish_manifest.json** — https://walterLiu168.github.io/tw-invest-suite/data/publish_manifest_2026-09-21.json
  - status: `200`
  - content check: manifest_critical_fields_match (data_date, run_id, picks_count, bucket_counts)

---

_Generated by daily_summary.py (D054) on 2026-09-22T08:29:03.366065_
