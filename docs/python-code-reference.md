# Python Code Reference

版本：2026-09-21
範圍：`scripts/*.py` 54 個 production-facing modules、`src/**/*.py` 20 個 non-underscore modules。底線開頭的 patch/debug modules 不在 production inventory，另列於最後。

## 1. 入口與編排

| 檔案 | 主要責任 | 常用介面 |
|---|---|---|
| `scripts/pipeline_state.py` | run identity、source hash、marker、certification、verify/watchdog | `begin`, `finalize-inputs`, `complete`, `verify`, `watchdog`, `fail` |
| `scripts/run_stage.py` | stage subprocess、timeout、sidecar exit code、log capture | `--label --out --err --exit-code-file --timeout script args...` |
| `scripts/check_openalice_health.py` | Scheduler/DB/file/AI-Telegram health | `--date`, `--json` |
| `scripts/nightly_health.py` | heartbeat deadline、owner identity、bounded recovery | `--kill`, `--json` |
| `scripts/postflight_daily.py` | post-publication checks | `--after-publish` |
| `scripts/build_dashboard.py` | 認證與遠端證據組合成 dashboard | no required CLI |
| `scripts/daily_summary.py` | 每日摘要、artifact/remote metadata | no required CLI |

## 2. 資料層與 API clients

| 檔案 | 主要責任 | 關鍵符號 |
|---|---|---|
| `scripts/db_client.py` | MySQL connection、dated snapshot、history/features | `query_date`, `report_date`, `latest_date`, `market_snapshot`, `ticker_history`, `ticker_features`, `chip_features` |
| `scripts/cache_manager.py` | per-dataset per-ticker disk TTL cache | `load`, `save`, `get_fresh`, `put`, `needs_refresh`, `stats` |
| `scripts/finmind_client.py` | FinMind HTTP client與dataset wrappers | `query`, `stock_info`, `stock_price`, `stock_per`, `stock_dividend`, `stock_institutional`, `stock_margin` |
| `scripts/finmind_batch.py` | PE/dividend/financial/month/news batches與rate limit | `fetch_pe`, `fetch_dividend`, `fetch_financials`, `fetch_month_revenue`, `fetch_news`, `batch_fetch` |
| `scripts/yfinance_batch.py` | yfinance batch、fallback、dead-state | `refresh_market_map`, `batch_fetch`, `is_dead`, `reset` |
| `scripts/yfinance_daily.py` | certified valuation cache refresh | `cache_coverage`, `refresh`, `main` |
| `scripts/finlab_client.py` | optional/historical FinLab adapter | `roe`, `monthly_revenue`, `price_history`, `broker_transactions_raw` |
| `scripts/twse_client.py` | TWSE OpenAPI adapter | `fetch_month`, `stock_price_history` |
| `scripts/tpex_client.py` | TPEx OpenAPI adapter | `fetch_day`, `stock_price_history` |
| `scripts/market_calendar.py` | verified TWSE closures、session calculation | `is_session`, `expected_session`, `verify_calendar` |
| `scripts/metadata_backfill.py` | missing industry metadata backfill | `--batch`, `--dry-run`, `--run-id` |
| `scripts/company_refresh.py` | recent company name/industry repair | `--days`, `--all`, `--date`, `--dry-run` |
| `scripts/sync_legacy_tables.py` | canonical-to-legacy cohort sync | `sync_one`, `verify_cohort` |

### Batch and one-time utilities

| 檔案 | 主要責任 | 狀態 |
|---|---|---|
| `scripts/batch_finmind_news.py` | 舊式全市場 FinMind news cache batch | legacy/manual；不取代 canonical nightly |
| `scripts/batch_finmind_only.py` | 舊式 FinMind-only cache batch | legacy/manual；受 rate limit 約束 |
| `scripts/batch_yfinance_only.py` | 舊式 yfinance-only cache batch | legacy/manual；不取代 `yfinance_daily.py` |
| `scripts/cross_source_runner.py` | 單股/批次跨來源組裝與來源差異記錄 | library/legacy render dependency |
| `scripts/demo_partial.py` | 2330 demo，其他區段使用 mock | demo only；不可作為 production evidence |
| `scripts/resolve_7768_official.py` | 官方 metadata 一次性修復，保留 quarantine rows | one-time migration；只有明確 `--apply` 才寫入 |

## 3. Market screen、watchlist 與 research

| 檔案 | 主要責任 | 關鍵符號/介面 |
|---|---|---|
| `scripts/market_screen.py` | candidate scoring與 long/short selection | `screen_market`, `pick_long_term`, `pick_short_term` |
| `scripts/market_screen_runner.py` | dated/idempotent run persistence與 artifact repair | `--force`, `--data-date`, `--refresh-existing` |
| `scripts/run_market_screen.py` | legacy/simple master runner | no required CLI |
| `scripts/market_report.py` | market screen Markdown renderer | `render_report`, `save_report` |
| `scripts/market_report_html.py` | market screen HTML renderer | `render_html`, `save_html` |
| `scripts/watchlist.py` | active picks、performance與 reports | `save_run`, `save_picks`, `get_active_picks`, `update_daily_performance` |
| `scripts/bounded_deep_dive.py` | bounded supplemental fetches for committed picks | `--worker`, `--out` |
| `scripts/deep_dive_prompts.py` | research prompts for picks | `build_news_block`, `pick_template`, `render_prompt` |
| `scripts/analyze_stock.py` | single-stock deep dive / Markdown | positional `stock_id`, `--out`, `--no-save` |
| `scripts/zen_analyzer.py` | simplified Chanlun structural analyzer | positional `ticker`, `--days` |
| `scripts/chatgpt_browser_reviewer.py` | optional browser review of changes | `get_diff`, `run_with_chrome` |

## 4. Rendering與公開輸出

| 檔案 | 主要責任 | 關鍵介面 |
|---|---|---|
| `scripts/render_only.py` | cache-only complete rendering chain | `--no-news`, `--no-yfinance` |
| `scripts/render_ticker_full.py` | cross-source single ticker renderer | section functions + `main` |
| `scripts/render_ticker_db_only.py` | DB-only fallback renderer | `render_ticker_html_db_only` |
| `scripts/render_ticker_html.py` | standalone single-ticker HTML | positional `ticker`, `--out`, `--no-save` |
| `scripts/render_full_watchlist.py` | full deep-dive watchlist page | `main` |
| `scripts/render_watchlist_html.py` | watchlist page renderer | `main` |
| `scripts/daily_full_tickers.py` | historical full-ticker cross-source renderer | `--limit`, `--ticker`, `--skip-render`, `--workers`, `--no-yfinance` |
| `scripts/daily_all_tickers.py` | DB-only all-ticker renderer | `--workers`, `--limit`, `--out` |
| `scripts/build_patterns_html.py` | patterns HTML | `main` |
| `scripts/pattern_classifier.py` | pattern predicates、returns、backtests | `classify_all`, `pattern_stats`, `backtest_pattern` |
| `scripts/publish_manifest.py` | artifact SHA manifest | `--date`, `--write-to`, `--verify-only` |
| `scripts/publish_ghpages.py` | immutable staging、GitHub push、remote verify | `--publish`, `--prepare-only` |
| `scripts/publish_analyze_ghpages.py` | historical/simple analyzer publisher | `main` |
| `scripts/publish_html.py` | optional local/cloudflared publisher | `main` |
| `scripts/publish_html_bg.py` | background local/cloudflared publisher | `main` |
| `scripts/stop_publish.py` | stop optional publisher processes | `main` |
| `scripts/sync_groove_release.py` | certified stock paths to Groove | `verify_paths`, `deploy`, `sync_verified` |

## 5. Report source modules (`src/`)

| 檔案 | 主要責任 |
|---|---|
| `src/report_inputs.py` | all-report dated canonical input loader/validators |
| `src/all_reports.py` | sectors、chips、advanced chips、concepts、history、metadata、OG 全報告 |
| `src/chip_rank.py` | 基礎籌碼排名與 HTML/JSON |
| `src/chip_advanced.py` | 20 日 advanced features |
| `src/chip_history.py` | 30 日 chips history |
| `src/chip_push.py` | certified Telegram chips delivery + idempotency ledger |
| `src/sector_aggregate.py` | industry_type-based sector aggregation |
| `src/concept_stocks.py` | concept stock data |
| `src/render_concepts.py` | concepts HTML |
| `src/render_chips_advanced.py` | advanced chips HTML |
| `src/build_ticker_meta.py` | yfinance cache -> tickers/history index |
| `src/fetch_tw_industry.py` | FinMind TaiwanStockInfo industry cache |
| `src/industry_zh.py` | Chinese industry/name normalization |
| `src/generate_og.py` | 1200x630 OG card generation |
| `src/margin_rebound/finmind_maint.py` | full-market margin maintenance receipt |
| `src/margin_rebound/scan.py` | optional seven-dimension rebound scan; `--threshold`, `--top`, `--out`, `--no-save` |
| `src/commentary/daily_commentary.py` | optional LLM commentary for current picks |
| `src/ml/features.py` | feature engineering from daily_data2_full |
| `src/ml/xgb_predictor.py` | walk-forward XGBoost predictor |
| `src/ml/lstm_predictor.py` | optional LSTM skeleton; not nightly gate |

## 6. PowerShell wrappers that invoke Python

| Wrapper | Python target |
|---|---|
| `scripts/run_daily.ps1` | `pipeline_state.py`, valuation, maintenance, market screen, render, patterns, watchlist, all_reports |
| `scripts/publish_ghpages_daily.ps1` | `pipeline_state.py verify`, `publish_ghpages.py` |
| `scripts/publish_verified_sites.ps1` | GitHub wrapper, `sync_groove_release.py`, `src/chip_push.py` |
| `scripts/marker_watchdog_daily.ps1` | `pipeline_state.py watchdog` |
| `scripts/nightly_health_daily.ps1` | `nightly_health.py` |
| `scripts/postflight_daily.ps1` | `postflight_daily.py` |
| `scripts/daily_status_check.ps1` | local status summary |
| `scripts/check_openalice_health.py` | direct Python health entrypoint |
| `scripts/market_screen_daily.ps1` | `market_screen_runner.py` |
| `scripts/company_refresh_daily.ps1` | `company_refresh.py` |
| `scripts/metadata_backfill_daily.ps1` | `metadata_backfill.py` |
| `scripts/sync_legacy_tables_runner.ps1` | `sync_legacy_tables.py` |
| `scripts/groove_service_watch.ps1` | Groove origin/tunnel supervision |
| `scripts/process_lifecycle.ps1` | process creation identity helpers |

## 7. Deliberately excluded from production inventory

`scripts/_debug/**`、`src/_*.py`、repo root `_*.py`、`src/__*`、temporary `_audit*`/`_d05*` files are diagnostic or historical. They may be useful for incident evidence, but:

- 不得加入 Scheduler action。
- 不得被 publisher 當成 source。
- 不得在 public package 內當成 supported API。
- 若要重用，先移入 canonical module、補測試、補文件與 source hash contract。

## 8. 驗證命令

```powershell
Set-Location 'C:\Users\icemo\Projects\tw-invest-suite'
C:\Python314\python.exe -m compileall -q scripts src
C:\Python314\python.exe scripts\pipeline_state.py verify
C:\Python314\python.exe scripts\_debug\final_acceptance_summary.py
C:\Python314\python.exe -m unittest discover -s tests -p 'test_*.py' -v
```

`compileall` 對底線 scratch 可能輸出非致命 SyntaxWarning；正式判斷以 return code、canonical modules 與 acceptance tests 為準。
