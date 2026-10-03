# Daily Closed-Loop Summary — 2026-10-02

**Status**: ❌ FAIL  
**Execution date**: 2026-10-03  
**Data date**: 2026-10-02  
**Phase**: after_publish  
**Generated at**: 2026-10-04T01:06:40.820614  
**Source commit**: `3cca0eaac5a7d2639bfa4828c61513435dc971fc`  

## DB integrity

- Total rows: **1960**
- Company NULL: **0** (none)
- Open quarantine: **0** (0 distinct ticker(s))

## 24 picks

- run_id: **49**
- picks_count: **24**
- buckets:
  - 100-300: 6
  - 300-1000: 6
  - <100: 6
  - >1000: 6
- tickers:
  - `1326` 台化 (<100)
  - `2409` 友達 (<100)
  - `2883` 凱基金 (<100)
  - `5310` 天剛 (<100)
  - `6158` 禾昌 (<100)
  - `6405` 悅城 (<100)
  - `2059` 川湖 (>1000)
  - `2330` 台積電 (>1000)
  - `3037` 欣興 (>1000)
  - `3081` 聯亞 (>1000)
  - `3443` 創意 (>1000)
  - `6531` 愛普* (>1000)
  - `1303` 南亞 (100-300)
  - `1727` 中華化 (100-300)
  - `2303` 聯電 (100-300)
  - `4904` 遠傳 (100-300)
  - `6505` 台塑化 (100-300)
  - `8091` 翔名 (100-300)
  - `2455` 全新 (300-1000)
  - `2492` 華新科 (300-1000)
  - `3163` 波若威 (300-1000)
  - `3532` 台勝科 (300-1000)
  - `4958` 臻鼎-KY (300-1000)
  - `6213` 聯茂 (300-1000)

## Cron results

| Cron | LastResult | ran_on_target | pass |
|---|---|---|---|
| tw-invest-suite-daily-report | `0` | ✓ | ✓ |
| tw-invest-suite-yfinance | `2` | ✓ | ✗ |
| tw-invest-suite-health-check | `0` | ✓ | ✓ |
| tw-invest-suite-sync-legacy | `0` | ✓ | ✓ |
| tw-invest-suite-company-refresh | `0` | ✓ | ✓ |
| tw-invest-suite-metadata-backfill | `0` | ✓ | ✓ |
| tw-invest-suite-market-screen | `0` | ✓ | ✓ |

## Other checks

- ✗ **completion**: state=failed, reason=nightly is incomplete/failed or marker belongs to another run
- ✓ **market_screen**: run_id=49, picks_count=24, picks_total=24, picks_active=24
- ✓ **company_null**: total=1960, null=0
- ✓ **industry_count**: count=1974
- ✗ **publication**: receipt={'nightly_id': '95196eb46a194638aacf2ab2fdfe144f', 'data_date': '2026-10-02', 'run_id': 49, 'status': 'verified', 'published_commit': '10046389f806fd62c1d5f3bcab726f67208ea1ca', 'verified_paths': ['analyze.html', 'analyze/1303.html', 'analyze/1326.html', 'analyze/1727.html', 'analyze/2059.html', 'analyze/2303.html', 'analyze/2330.html', 'analyze/2409.html', 'analyze/2455.html', 'analyze/2492.html', 'analyze/2883.html', 'analyze/3037.html', 'analyze/3081.html', 'analyze/3163.html', 'analyze/3443.html', 'analyze/3532.html', 'analyze/4904.html', 'analyze/4958.html', 'analyze/5310.html', 'analyze/6158.html', 'analyze/6213.html', 'analyze/6405.html', 'analyze/6505.html', 'analyze/6531.html', 'analyze/8091.html', 'analyze/patterns.html', 'analyze/patterns.json', 'assets/textsize.css', 'assets/textsize.js', 'chips-advanced.html', 'chips-history.html', 'chips.html', 'concepts.html', 'data/chips-advanced.json', 'data/chips-history-index.json', 'data/chips-history/2026-08-20.json', 'data/chips-history/2026-08-21.json', 'data/chips-history/2026-08-24.json', 'data/chips-history/2026-08-25.json', 'data/chips-history/2026-08-26.json', 'data/chips-history/2026-08-27.json', 'data/chips-history/2026-08-28.json', 'data/chips-history/2026-08-31.json', 'data/chips-history/2026-09-01.json', 'data/chips-history/2026-09-02.json', 'data/chips-history/2026-09-03.json', 'data/chips-history/2026-09-04.json', 'data/chips-history/2026-09-07.json', 'data/chips-history/2026-09-08.json', 'data/chips-history/2026-09-09.json', 'data/chips-history/2026-09-10.json', 'data/chips-history/2026-09-11.json', 'data/chips-history/2026-09-14.json', 'data/chips-history/2026-09-15.json', 'data/chips-history/2026-09-16.json', 'data/chips-history/2026-09-17.json', 'data/chips-history/2026-09-18.json', 'data/chips-history/2026-09-21.json', 'data/chips-history/2026-09-22.json', 'data/chips-history/2026-09-23.json', 'data/chips-history/2026-09-24.json', 'data/chips-history/2026-09-29.json', 'data/chips-history/2026-09-30.json', 'data/chips-history/2026-10-01.json', 'data/chips-history/2026-10-02.json', 'data/chips.json', 'data/concept-stocks.json', 'data/og.png', 'data/patterns.json', 'data/publish_manifest_2026-10-02.json', 'data/sectors.json', 'data/tickers.json', 'data/tw-industry.json', 'data/watchlist-full.json', 'deep-dive-prompts-2026-10-02.md', 'manifest.json', 'market-screen-2026-10-02.html', 'market-screen-2026-10-02.md', 'monitor.html', 'patterns.html', 'readme.html', 'sectors.html', 'sw.js', 'watchlist-full-2026-10-02.html', 'watchlist.html'], 'analytical_verified': True, 'report_status': 'pending', 'verified_at': '2026-10-04T01:06:38.599424'}

## Artifacts

| Path | Size | SHA-256 (full) |
|---|---|---|
| `C:\Users\icemo\.claude\skills\tw-invest-suite\reports\market-screen-2026-10-02.md` | 18,040 B | `32304a70dc7c74f415d7cc6a82bfabaa28530a38dca06878cf7f4b1820f53428` |
| `C:\Users\icemo\.claude\skills\tw-invest-suite\reports\market-screen-2026-10-02.html` | 146,349 B | `fb0647042fcb3055ef2647a6bfdd86c6d9a953b6f968b441ca3a312768ff5e89` |
| `C:\Users\icemo\.claude\skills\tw-invest-suite\reports\deep-dive-prompts-2026-10-02.md` | 64,912 B | `90724813da1ba296dbd8f0b3f51d7dc9f31e6f5b479ddcc83b8372fc8c61b61c` |
| `C:\Users\icemo\.claude\skills\tw-invest-suite\reports\watchlist-full-2026-10-02.html` | 2,158,613 B | `f379ca9ca02db401748974f77654b6979adaca952d19c3343599368a06846434` |

## Remote verify (GitHub Pages)

- ✓ **watchlist.html** — https://walterLiu168.github.io/tw-invest-suite/watchlist.html
  - status: `200`
  - content check: date_in_body=True, rows=24
- ✓ **analyze.html** — https://walterLiu168.github.io/tw-invest-suite/analyze.html
  - status: `200`
  - content check: page reachable
- ✓ **analyze/1326.html** — https://walterLiu168.github.io/tw-invest-suite/analyze/1326.html
  - status: `200`
  - content check: first_pick=1326, ticker_in_body=True
- ✓ **publish_manifest.json** — https://walterLiu168.github.io/tw-invest-suite/data/publish_manifest_2026-10-02.json
  - status: `200`
  - content check: manifest_critical_fields_match (data_date, run_id, picks_count, bucket_counts)

---

_Generated by daily_summary.py (D054) on 2026-10-04T01:06:40.820614_
