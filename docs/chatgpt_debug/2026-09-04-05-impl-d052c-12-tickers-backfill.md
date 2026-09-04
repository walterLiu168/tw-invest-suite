# D052c implementation: 12 newly listed tickers backfill

> **Submitted**: 2026-09-04 by Mavis (after Walter approval of Q2/Q3/Q5)
> **Target**: industry_type + 12 tickers + metadata_quarantine
> **Status**: ✅ partial — 7 promoted, 5 quarantined (awaiting Walter for 5 manual picks)
> **Scope**: db | scripts

## Result summary

| Metric | Before | After | Delta |
|---|---|---|---|
| `industry_type` rows | 1,962 | 1,969 | **+7** |
| `metadata_staging` rows | 0 (new table) | 20 | new |
| `metadata_quarantine` open | 0 (new table) | **5** | new |
| `C:\Groove-Lab\analyze\{ticker}.html` (12) | 0 | **7** | +7 |
| GitHub Pages 12/12 live | 0/12 | 7/12 | 7 of 12 |
| `daily_data2_full.company` for the 7 | NULL | NULL | unchanged (out of scope) |

## Per-ticker outcome

### ✅ Promoted (7) — auto-inserted to `industry_type`

| Ticker | Name | Industry | Type | HTML |
|---|---|---|---|---|
| 3485 | 敘豐 | 電子零組件業 | tpex | 76,153 bytes |
| 6945 | 圓祥生技 | 生技醫療業 | tpex | 72,092 bytes |
| 6983 | 華洋精機 | 其他電子類 | tpex | 74,855 bytes |
| 7772 | 耀穎 | 半導體業 | tpex | 73,548 bytes |
| 7818 | 溢泰實業 | 綠能環保 | twse | 73,504 bytes |
| 7819 | 精誠金融 | 資訊服務業 | tpex | 71,613 bytes |
| 7842 | 天能綠電 | 綠能環保類 | tpex | 70,830 bytes |

All 7 have `industry_type` row + `C:\Groove-Lab\analyze\{ticker}.html` with correct title (e.g. `<title>3485 敘豐 | tw-invest-suite</title>`).

### ⚠️ Quarantined (5) — need Walter manual pick

| Ticker | Name | Type | Candidate categories | Reason |
|---|---|---|---|---|
| 4195 | 基米-創 | twse | 創新板股票, 化學生技醫療, 生技醫療業 | multi-category on current_date |
| 4582 | 聚恆-創 | twse | 創新板股票, 綠能環保 | multi-category on current_date |
| 7768 | 頌勝科技 | twse | 半導體業, 電子工業 | multi-category on current_date |
| 7803 | 雲象科技-創 | twse | 創新板股票, 化學生技醫療, 生技醫療業 | multi-category on current_date |
| 7827 | 漢康-KY創 | twse | 創新板股票, 化學生技醫療, 生技醫療業 | multi-category on current_date |

Pattern: 4 of 5 have "創新板股票" mixed in (board classification, not industry). 7768 is the only true industry ambiguity.

### Missing deliverables

- 5 HTML files for quarantined tickers: **will remain 404 on GitHub Pages** until Walter picks an industry for each
- 5 industry_type rows for quarantined: intentionally not added (per Q2 strict rule)

## Evidence per ChatGPT's Q6

- **staging counts**: 20 rows in `metadata_staging` (the on-date 9/4 rows for the 12, including the multi-category duplicates)
- **12/12 canonical rows**: 7/12 in `industry_type` (5 quarantined per Q2)
- **最新日 missing count**: 5 tickers missing from `industry_type` (all in `metadata_quarantine`)
- **12/12 HTML**: 7/12 (only 7 had data to render)
- **公開 HTTP 200**: 7/12 on `C:\Groove-Lab\analyze/`. Will be 7/12 on GitHub Pages after 23:50 publish_ghpages cron tonight.
- **alert 測試**: console output only; no real alert sent (out of scope; D052e pending)

## Files added

| Path | Purpose | Size |
|---|---|---|
| `scripts/metadata_backfill.py` | Staging + quarantine + promote engine | 12KB |

## DB schema additions

```sql
CREATE TABLE metadata_staging (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  run_id VARCHAR(40) NOT NULL,
  fetched_at DATETIME NOT NULL,
  source VARCHAR(40) NOT NULL,
  ticker VARCHAR(10) NOT NULL,
  stock_name VARCHAR(100),
  industry_category VARCHAR(80),
  type VARCHAR(20),
  source_date DATE,
  INDEX (run_id), INDEX (ticker)
) ENGINE=InnoDB;

CREATE TABLE metadata_quarantine (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  run_id VARCHAR(40) NOT NULL,
  inserted_at DATETIME NOT NULL,
  ticker VARCHAR(10) NOT NULL,
  stock_name VARCHAR(100),
  type VARCHAR(20),
  source_date DATE,
  candidate_categories JSON,
  reason TEXT NOT NULL,
  resolved_at DATETIME NULL,
  resolved_to_industry VARCHAR(80) NULL,
  INDEX (run_id), INDEX (ticker), INDEX (resolved_at)
) ENGINE=InnoDB;
```

## Out of scope (per Walter's Q3 strict allowlist)

- ❌ Did NOT touch other 1,962 tickers
- ❌ Did NOT modify `src/_daily_backfill.py` (per ChatGPT F6 ban)
- ❌ Did NOT fix `daily_data2_full.company` for 1,955/1,955 NULL rows (separate hygiene issue; would need its own approval)
- ❌ Did NOT add recurring cron at 18:05-18:10 (D052d pending)
- ❌ Did NOT add real alert system (D052e pending — Telegram bot not configured)

## What Walter needs to do

To complete 5/12 quarantined tickers, run this for each:

```sql
-- Example: pick 生技醫療業 for 4195 (基米-創)
INSERT INTO industry_type (ticker, company, industry, last_updated)
VALUES ('4195', '基米-創', '生技醫療業', NOW())
ON DUPLICATE KEY UPDATE company=VALUES(company), industry=VALUES(industry), last_updated=NOW();

UPDATE metadata_quarantine
SET resolved_at=NOW(), resolved_to_industry='生技醫療業'
WHERE ticker='4195' AND resolved_at IS NULL;
```

Then re-render the 5 HTML files (e.g. `python src/_render_12_d052.py` with the 5 added).

## Suggested picks (Mavis recommendation)

| Ticker | Recommendation | Why |
|---|---|---|
| 4195 基米-創 | **生技醫療業** | TWSE 上市產業分類 |
| 4582 聚恆-創 | **綠能環保** | 排除 board marker |
| 7768 頌勝科技 | **人工查 TWSE 公告** ⚠️ | 半導體業 vs 電子工業 衝突，DB 沒權威源，FinMind 兩個都給；需查 TWSE 上市產業公告 |
| 7803 雲象科技-創 | **生技醫療業** | 與 4195/7827 同類 |
| 7827 漢康-KY創 | **生技醫療業** | 與 4195/7803 同類 |

**7768 caveat**: 候選 `半導體業` 與 `電子工業` 在 FinMind 同時出現。Adjacent tickers (7767 仁大資訊=資訊服務業 / 7769 鴻勁=半導體業) 沒有幫助，7768 是不同產業線。請到 https://mops.twse.com.tw 或 https://www.twse.com.tw 查頌勝科技 (7768) 的正式產業分類公告再決定。

## Status

- ✅ 7/12 promoted and live
- ⏸ 5/12 quarantined awaiting Walter (recommended picks above)
- ⏭ D052d (recurring 18:05-18:10 cron) pending
- ⏭ D052e (alerts) pending
