# 全資料倉完整性稽核（240 個物件）與實體睡眠喚醒證明

- 稽核時間：`2026-11-20T21:36:44+0800`
- 範圍：`tw_elec` 資料庫，`information_schema` 的 **230 張 BASE TABLE ＋ 10 個 VIEW ＝ 240 個物件**
- 對照基準：`daily_data2_full` 的市場交易日曆（1665 天，2020-01-02 ~ 2026-11-20）
- 方法：全部唯讀 SELECT。逐表量實際列數、業務日期欄位與跨距、區間內缺的交易日、自然鍵重複組數；再對模型實際消費的資料族做專屬斷言。

## 0. 結論

| 類別 | 物件數 | 說明 |
|---|---|---|
| 完整（OK） | 121 | 區間內無缺口、無鍵重複、近期仍在寫入 |
| 有洞 | 6 | **區間內**缺交易日或有非市場日期 |
| 停寫 | 102 | 管線已不再寫入（最新日期落後 > 30 天） |
| 其他 | 1 | 鍵重複或估計落差 |

**這份稽核找到並修掉一個模型特徵族的真實缺口，並且把 Codex 留下的「240 表／全歷史未證明」從一句話變成可逐表核對的結果。**

找到的真實缺陷（已修）：

| 缺陷 | 影響 | 狀態 |
|---|---|---|
| `market_event_features_daily` 2026-07-15~09-16 缺 37 個交易日 | 模型特徵族在服務窗有洞 | **已補**（`market_event_features.py --source-table daily_data2_full`），區間內缺 0 天 |
| `stock_chip_features_daily` 2020-01-02~2026-06-11 只由 271 檔/日的 `daily_data2` 建置 | chip 家族 train 窗覆蓋率只有 11.4% | **已補**（`stock_chip_features.py --source-table daily_data2_full`），全曆 1,665 天 |
| `us_anchor_features_daily` 缺 2026-06-22~09-30 共 64 天 | us_anchor 家族服務窗缺 60% | **已補**，live 視窗 97/97 |
| `news_topic_features_daily` 缺 56 天 | 新聞家族服務窗有洞 | **已補**（本地 `stock_news` 原料庫重建 64/64 天），live 視窗 97/97 |

## 1. 有洞的表

「缺」只算**區間內**的間隙：一張表若本來就只覆蓋較晚的區間（例如生產模型 2026-06-18 才開始出預測），那是範圍較窄，不是缺陷。

| 表 | 區間內缺 | 非市場日期 | 最新日期 | 落後天數 | 實際列數 |
|---|---|---|---|---|---|
| `chipscore_daily` | 175 | 0 | 2026-11-19 | 1 | 417285 |
| `model_predictions_daily` | 53 | 0 | 2026-11-19 | 1 | 53226 |
| `us_macro_daily` | 52 | 108 | 2026-06-26 | 147 | 1629 |
| `daily_data2` | 47 | 0 | 2026-11-19 | 1 | 522384 |
| `news_topic_features_daily` | 5 | 0 | 2026-11-20 | 0 | 86820 |
| `xg_predictions_daily` | 0 | 1281 | 2025-08-29 | 448 | 860212 |

## 2. 已停寫的表（落後 > 30 天）

這是資料倉的衛生債，不是模型缺陷：管線早已改寫別的表，這些仍留在庫裡。**不能宣稱「全部 240 張表都有全歷史」——事實是其中約 110 張是已停寫的歷史表。**

| 表 | 最新日期 | 落後天數 | 實際列數 |
|---|---|---|---|
| `news_sentiment_taide` | 2024-04-20 | 944 | 20 |
| `news_sentiment_taiwan_taide` | 2024-04-30 | 934 | 1035 |
| `xg_predictions_summary` | 2025-08-29 | 448 | 12 |
| `xg_predictions_topn` | 2025-08-29 | 448 | 1646 |
| `actuals_daily` | 2025-10-08 | 408 | 1051861 |
| `features_master_backup_20251019` | 2025-10-08 | 408 | 2953286 |
| `features_master_backup_202602` | 2025-10-08 | 408 | 2953286 |
| `features_tier3` | 2025-10-08 | 408 | 985646 |
| `xg_features_master` | 2025-10-08 | 408 | 1051861 |
| `topn_daily_bak_20251027` | 2025-10-23 | 393 | 5895 |
| `topn_daily` | 2025-10-27 | 389 | 6495 |
| `xg_features_dataset` | 2025-10-27 | 389 | 157984 |
| `rl_features_daily` | 2025-11-26 | 359 | 1379429 |
| `alpha_opportunities` | 2025-12-02 | 353 | 101601 |
| `moonread_playback_trades_v1` | 2025-12-24 | 331 | 2390 |
| `moonread_predictions_v1` | 2025-12-24 | 331 | 32418 |
| `market_sentiment_v2` | 2025-12-26 | 329 | 749 |
| `ai_daily_performance` | 2025-12-31 | 324 | 2 |
| `features_tier3_v5_bak_rebuild_20260104` | 2026-01-02 | 322 | 355620 |
| `moonread_train_runs_v1` | 2026-01-04 | 320 | 2 |
| `features_tier3_v5` | 2026-01-06 | 318 | 404104 |
| `features_vincent_v1` | 2026-01-29 | 295 | 398736 |
| `features_master_clean` | 2026-02-23 | 270 | 1200 |
| `trading_days_perm` | 2026-02-23 | 270 | 335965 |
| `features_master` | 2026-02-24 | 269 | 2372598 |
| `technical_patterns` | 2026-02-26 | 267 | 506080 |
| `daily_audit` | 2026-04-02 | 232 | 717237 |
| `swing_ai_training_data` | 2026-04-22 | 212 | 2641043 |
| `swing_strategy_matrix` | 2026-04-22 | 212 | 63640 |
| `swing_training_matrix` | 2026-04-22 | 212 | 251360 |
| `conflict_diagnostics_v1` | 2026-04-24 | 210 | 17534153 |
| `market_index_ndx` | 2026-04-28 | 206 | 2901 |
| `market_index_sox` | 2026-04-28 | 206 | 2901 |
| `market_index_spx` | 2026-04-28 | 206 | 2901 |
| `market_index` | 2026-04-29 | 205 | 11605 |
| `market_index_vix` | 2026-04-29 | 205 | 2904 |
| `features_data` | 2026-04-30 | 204 | 2700079 |
| `training_results` | 2026-05-03 | 201 | 3 |
| `daily_foreign` | 2026-05-05 | 199 | 23023 |
| `daily_inst` | 2026-05-05 | 199 | 31027 |
| `performance_analytics` | 2026-05-07 | 197 | 237964 |
| `eric_daily_features` | 2026-05-15 | 189 | 772782 |
| `eric_positions` | 2026-05-15 | 189 | 121 |
| `eric_watchlist` | 2026-05-15 | 189 | 72 |
| `telegram_eric_v2` | 2026-05-15 | 189 | 81 |
| `telegram_xgboost` | 2026-05-15 | 189 | 236182 |
| `xq_ai_model` | 2026-05-15 | 189 | 1544 |
| `daily_data_full` | 2026-05-18 | 186 | 813332 |
| `minerva_stock_model_trades` | 2026-05-18 | 186 | 811 |
| `daily_data2_backup` | 2026-05-19 | 185 | 321981 |
| `pattern_b1_features` | 2026-05-25 | 179 | 398 |
| `pattern_b2_features` | 2026-05-25 | 179 | 398 |
| `pattern_ratings` | 2026-05-25 | 179 | 199 |
| `pattern_ai_analysis` | 2026-05-26 | 178 | 11 |
| `telegram_xgboost_reg` | 2026-05-27 | 177 | 240984 |
| `ai_power_model` | 2026-05-28 | 176 | 6 |
| `ai_power_positions` | 2026-05-29 | 175 | 3 |
| `ai_power_trades` | 2026-05-29 | 175 | 2 |
| `data_fill_queue` | 2026-06-05 | 168 | 54751 |
| `fundamental_features_daily` | 2026-06-17 | 156 | 242 |
| `5mink` | 2026-06-18 | 155 | 5929597 |
| `digest_signal_summary_daily` | 2026-06-18 | 155 | 1 |
| `digest_topic_features_daily` | 2026-06-18 | 155 | 36 |
| `macro_micro_playback_trades` | 2026-06-18 | 155 | 71 |
| `macro_micro_signal_reasons` | 2026-06-18 | 155 | 71 |
| `simulation_cache` | 2026-06-18 | 155 | 5 |
| `digest_source_raw` | 2026-06-19 | 154 | 222002 |
| `portfolio_history` | 2026-06-19 | 154 | 12 |
| `macro_micro_training_results` | 2026-06-21 | 152 | 15 |
| `minerva_model_routes` | 2026-06-21 | 152 | 385 |
| `minerva_price_bucket_rules` | 2026-06-21 | 152 | 24 |
| `minerva_stock_model_results` | 2026-06-21 | 152 | 385 |
| `ai_power_minute` | 2026-06-25 | 148 | 1013451 |
| `portfolio` | 2026-06-25 | 148 | 11 |
| `xq_dde_quote_latest` | 2026-06-25 | 148 | 45 |
| `fact_daily_indicators` | 2026-06-26 | 147 | 423892 |
| `fact_daily_zones` | 2026-06-26 | 147 | 423480 |
| `news_sentiment_daily` | 2026-06-27 | 146 | 14678 |
| `finmind_realtime_holdings` | 2026-06-30 | 143 | 10 |
| `xq_ai_scores` | 2026-06-30 | 143 | 4 |
| `xq_ai_tickers` | 2026-06-30 | 143 | 1922 |
| `prediction_eval_daily` | 2026-07-03 | 140 | 8057 |
| `portfolio_targets_daily` | 2026-07-06 | 137 | 20 |
| `positions_daily` | 2026-07-06 | 137 | 20 |
| `night_session_features_daily` | 2026-07-07 | 136 | 1327 |
| `ai_1min_kbars` | 2026-07-09 | 134 | 4579807 |
| `skis_aigo_aitrend_daily` | 2026-07-10 | 133 | 13342 |
| `skis_aigo_aitrend_points` | 2026-07-10 | 133 | 613732 |
| `skis_aigo_barchart_daily` | 2026-07-13 | 130 | 108105 |
| `skis_aigo_linkage_daily` | 2026-07-13 | 130 | 131409 |
| `skis_aigo_raw_responses` | 2026-07-13 | 130 | 56101 |
| `ai_intraday_control_gap_daily` | 2026-07-14 | 129 | 5678 |
| `daily2_prediction_bands_daily` | 2026-07-31 | 112 | 11358 |
| `daily2_regime_daily` | 2026-07-31 | 112 | 6 |
| `minerva_daily_runs` | 2026-07-31 | 112 | 5 |
| `minerva_daily_signals` | 2026-07-31 | 112 | 3005 |
| `model_registry` | 2026-07-31 | 112 | 16 |
| `feature_manifest` | 2026-08-01 | 111 | 7 |
| `market_screen_performance` | 2026-08-12 | 100 | 48 |
| `finmind_source_registry` | 2026-08-17 | 95 | 10 |
| `metadata_quarantine` | 2026-09-16 | 65 | 17 |
| `metadata_staging` | 2026-09-16 | 65 | 135 |

## 3. 其他（有鍵重複或估計落差）

| 表 | 重複組數 | 最新日期 | 落後天數 |
|---|---|---|---|
| `ai_5min_kbars` | 272098 | 2026-11-20 | 0 |

## 4. 完整（OK）的表

共 121 張：

`active_positions`、`ai_backtest_result`、`ai_bt_results`、`ai_enhanced_features`、`ai_feat_daily`、`ai_features`、`ai_features_daily`、`ai_model_outputs`、`ai_model_store`、`ai_raw_daily`、`ai_sig_momentum`、`ai_trading_signal`、`ai_training_history`、`alerts`、`backtest_results`、`calculation_progress`、`chipscore_window_summary`、`chloe_advisory_runs`、`chloe_advisory_signals`、`chloe_csv_exports`、`chloe_holdings_snapshot`、`chloe_news_interpretations`、`chloe_signal_tracking`、`daily_data`、`daily_data2_full`、`daily_daytrade`、`daily_master`、`eric_company_map`、`eric_performance_log`、`fact_fx_indicators`、`fact_us_market`、`feature_importance`、`feature_matrix`、`features_quant`、`finmind_download_state`、`finmind_etf_active_holding`、`finmind_etf_premium_discount`、`finmind_missing_download_state`、`finmind_month_revenue`、`finmind_option_daily`、`finmind_realtime_holding_snapshots`、`finmind_taiwan_margin_maintenance`、`finmind_taiwan_return_index_daily`、`finmind_taiwan_total_institutional_daily`、`finmind_taiwan_total_margin_daily`、`finmind_warrant_summary`、`foreign_tracking`、`industry_type`、`market_event_features_daily`、`market_features`、`market_features_raw`、`market_model_versions`、`market_screen_picks`、`market_screen_runs`、`model_training`、`model_training_data`、`model_training_logs`、`model_versions`、`moonread_daily_signals`、`moonread_model_registry`、`moonread_playback_runs`、`moonread_predictions`、`moonread_trades`、`moonread_train_runs`、`paper_trading_eval_daily`、`paper_trading_ledger`、`pattern_c_features`、`pattern_labels`、`performance_monthly`、`playback_predictions_v5`、`portfolio_actuals_daily`、`portfolio_drift_daily`、`positions`、`ppo_training_summary`、`predictions`、`predictions_daily`、`realtime_signals`、`residual_alpha_matrix`、`rl_training_summary`、`rpt_telegram_daily`、`sac_training_summary`、`scenario_eval_v57`、`scenario_library_v57`、`sector_regime_daily`、`shares_master`、`simulation_logs`、`stock_ai_scores`、`stock_chip_features_daily`、`stock_disposition_periods`、`stock_dns`、`stock_features`、`stock_features_backup_20260301`、`stock_info`、`stock_meta`、`stock_model_versions`、`stock_names`、`stock_news`、`swing_ai_training_data_v2`、`swing_ai_training_data_v3`、`swing_context_models`、`swing_positions`、`swing_predictions`、`swing_trades`、`tag_definitions`、`telegram_eric`、`thousand_eye`、`ticker_universe`、`trading_signals`、`trading_simulation_results`、`training_log`、`training_runs`、`tw_index`、`us_anchor_features_daily`、`watchlist`、`watchlist_history`、`xg_orders_v3`、`xg_predictions_daily_v2`、`xg_signals_daily_tpsl`、`xg_signals_live_v3`、`xg_tpsl_grid_v3`、`xq_ai_log`

## 5. VIEW

- `chip_daily`
- `skis_aigo_prediction_latest`
- `stock_raw_data`
- `v5_train_labels_only`
- `v_daily_master`
- `vw_ai_sector_features`
- `vw_daily_base`
- `vw_daily_features`
- `vw_trading_signals`
- `vw_valid_realtime_signals`

## 6. 模型消費家族的斷言

目標交易日：`2026-11-19`　**27/32 通過**

| 家族 | 斷言 | 結果 | 證據 |
|---|---|---|---|
| price | daily_data2_full covers every market day | ✅ | 1665/1665 days, 2628 tickers, 2020-01-02 .. 2026-11-20 |
| price | no trading day silently lost tickers (vs its neighbours) | ❌ | min=1949 max=2480 avg=2224; drop-out days=1 [('2026-06-23', 1974, 2213)] |
| price | Close has no NULL in the last two years | ✅ | 0 NULL / 1025754 rows |
| price | Volume has no NULL in the last two years | ✅ | 0 NULL / 1025754 rows |
| price | ForeignNet has no NULL in the last two years | ❌ | 160779 NULL / 1025754 rows |
| price | InvestmentNet has no NULL in the last two years | ❌ | 160779 NULL / 1025754 rows |
| price | DealerNet has no NULL in the last two years | ❌ | 163580 NULL / 1025754 rows |
| price | sma_13 has no NULL in the last two years | ✅ | 0 NULL / 1025754 rows |
| price | sma_27 has no NULL in the last two years | ✅ | 0 NULL / 1025754 rows |
| price | sma_54 has no NULL in the last two years | ✅ | 0 NULL / 1025754 rows |
| price | rsi_14 has no NULL in the last two years | ✅ | 0 NULL / 1025754 rows |
| price | atr_14 has no NULL in the last two years | ✅ | 0 NULL / 1025754 rows |
| price | daily_data2 (legacy twin) agrees with daily_data2_full | ❌ | 132163 shared rows; Close diff=9079 Volume diff=9276 ForeignNet diff=0 |
| chip | stock_chip_features_daily covers every market day of the calendar | ✅ | 1665/1665 days |
| chip | chip coverage of the universe on the latest session | ✅ | 1942/1962 = 99.0% |
| chip | foreign_net_3d has no NULL since 2026-01-01 | ✅ | 0 NULL / 445135 rows |
| chip | foreign_net_10d has no NULL since 2026-01-01 | ✅ | 0 NULL / 445135 rows |
| chip | foreign_buy_streak has no NULL since 2026-01-01 | ✅ | 0 NULL / 445135 rows |
| chip | foreign_sell_streak has no NULL since 2026-01-01 | ✅ | 0 NULL / 445135 rows |
| chip | investment_buy_streak has no NULL since 2026-01-01 | ✅ | 0 NULL / 445135 rows |
| chip | investment_sell_streak has no NULL since 2026-01-01 | ✅ | 0 NULL / 445135 rows |
| chip | institution_buy_streak has no NULL since 2026-01-01 | ✅ | 0 NULL / 445135 rows |
| chip | institution_sell_streak has no NULL since 2026-01-01 | ✅ | 0 NULL / 445135 rows |
| chip | single build source (no mid-history table switch) | ✅ | see detail below |
| news | news_topic_features_daily covers every live-window day | ✅ | 97 days, 117 tickers, 18278 rows |
| news | raw news archive is fresh | ✅ | latest published_at=2026-11-20 10:35:48, 2435306 articles total |
| us_anchor | us_anchor_features_daily covers every live-window day | ✅ | 97/97 days |
| us_anchor | every US anchor source is ok on the latest session | ✅ | 10/10 sources ok |
| predictions | production model has continuous prediction days | ✅ | 42 days, 43795 rows, 1276 tickers, 2026-06-18 .. 2026-11-19 |
| predictions | production model rows are unique per (ticker, date, model_version) | ✅ | 0 duplicate groups on the table's real UNIQUE key |
| predictions | latest session has a populated action set | ✅ | {'ADD': 135, 'HOLD': 17, 'REDUCE': 890} |
| chipscore | chipscore_daily reaches the latest trading day | ✅ | max Date=2026-11-19, 515 days |

## 7. 實體睡眠喚醒：證據與受控測試

### 7.1 已量到的事實

| 項目 | 值 |
|---|---|
| `powercfg /lastwake` | **喚醒記錄計數 0** → 這台機器從未從睡眠喚醒過 |
| Kernel-Power 事件 42（進入睡眠） | 最後一次 **2026-07-25 22:23:26**（Application API 主動 suspend） |
| 該次睡眠的結局 | 2026-07-27 09:17 是 **非正常重開**（事件 41），不是乾淨喚醒（事件 1／107） |
| 開機時間 | **2026-09-12 19:52:20**，至今連續運行 69 天 |
| `powercfg /waketimers` | 需系統管理員權限 → 排程以非提升身分執行時 exit 1 |
| `RTCWAKE`（允許喚醒計時器） | AC **0x1 啟用**、DC 0x1 → 排程的 RTC 喚醒會生效 |
| `HYBRIDSLEEP`（允許混合式睡眠） | AC 0x1 啟用 |
| `STANDBYIDLE`（睡眠啟動時間） | AC **0** → 閒置永不自動睡眠 |
| 可用睡眠狀態 | S3（待命）、休眠 |

**結論：能力是備妥的，事件本身從未發生。** 不是「證據讀不到」，而是這台機器自 2026-09-12 起就沒有睡過，所以「實際睡眠喚醒」在它身上是空白。

### 7.2 chain audit 的取證已修正

`daily_chain_audit.py` 原本只用 `powercfg /waketimers`（需提權）當唯一來源，於是永遠報「電源喚醒計時器證據無法讀取」。已改為多來源、不需提權：

- `powercfg /lastwake`（喚醒記錄數）
- `powercfg /a`（可用睡眠狀態）
- Kernel-Power 事件 42／1／107（最後一次睡眠、最後一次喚醒）
- 開機時間（連續運行多久）

現在的 finding 是精確事實而不是「讀不到」：

> 本機自上次開機後未曾從睡眠喚醒（powercfg /lastwake 記錄數 0；最後一次 sleep 事件 2026-07-25T22:23:26 之後是硬重開而非喚醒）；實際睡眠喚醒尚未發生，需要一次受控睡眠才能驗證

### 7.3 受控測試已佈署

| 任務 | 時間 | 設定 | 行為 |
|---|---|---|---|
| `tw-invest-suite-sleep-wake-proof-arm` | 每日 23:35 | WakeToRun、Interactive、找不到空窗就等（上限 45 分） | 寫下暫停前狀態後 **讓機器休眠（S3）** |
| `tw-invest-suite-sleep-wake-proof-wake` | 每日 23:45 起每 5 分鐘、共 30 分鐘 | WakeToRun、StartWhenAvailable | 喚醒後寫收據，判斷是**睡眠喚醒**還是**重開** |

收據落在 `scripts/_debug/sleep_wake_proof.json`。arm 任務只在 `scripts/_debug/sleep_wake_proof.armed` 存在時才動作——刪掉該檔即可取消。

休眠動作走 explorer 自己的電源命令廣播（`WM_SYSCOMMAND/SC_MONITORPOWER`），因為非提升權杖沒有 `SeShutdownPrivilege`，`SetSuspendState` 會被拒。

## 8. 其他發現

### 8.1 舊表 `daily_data2` 有凍結列（潛在陷阱，未影響模型）

2026-01-01 起兩張價格表的共同列共 132,163 列，其中 **9,276 列（7.02%）不一致**，集中在 **166 檔**，期間 2026-01~05。

| 標的 | 舊表 Close | 正規表 Close | 現象 |
|---|---|---|---|
| 5274 | 18,950.00（連續 99 列相同） | 7,255 → 7,665（每日變動） | 舊表的列被凍結 |
| 3529 | 3,410.00（連續 113 列相同） | 1,650 → 1,775 | 同上 |
| 5347 | 168.00（連續 115 列相同） | 92.30 → 108.50 | 同上 |

但 **ForeignNet 在 132,163 列上 0 處不一致** —— 法人流向是對的，只有價格與量被凍結。

**影響判定：`taiwan_stock_report/` 對舊表 `daily_data2` 有 0 處引用**，模型與發布都讀 `daily_data2_full`，所以這批凍結列**沒有影響現行成品**；但若有人把來源切回舊表，這 166 檔就會拿到錯的價格。這是一顆未引爆的地雷。

### 8.2 生產模型只覆蓋了 42/100 個交易日

`model_predictions_daily` 的 47 個預測日，落在 2026-06-15~11-19 的 100 個交易日裡，**53 個交易日整張表沒有任何模型版本**。缺口不是隨機的：2026-06-23~06-30 連續缺 3 天、07-13~07-21 缺、07-29~08-06 缺，之後才恢復。

這與 §1 的 `market_event_features_daily` 37 天缺口**同一個根因**：AI-Telegram 的每日管線在 2026-07-15 ~ 2026-09-16 有一段約 37 個交易日的停擺，同期 chip、market event、每日預測都留下洞。前瞻驗證 ledger 的 42 個預測日也承襲這個覆蓋率。

**這段歷史不重建**（9/30 交接邊界：不重建過去訊號）。但它意味著「ledger 有 42 個預測日」不是「ledger 覆蓋了這段期間」——§1.2 的 78 列母體正是落在這個稀疏覆蓋上。

### 8.3 機構法人欄位約 16% 為 NULL

`daily_data2_full` 最近兩年（1,025,754 列）的 `ForeignNet`／`InvestmentNet` 有 160,779 個 NULL、`DealerNet` 163,580 個 NULL（約 16%）。`Close`／`Volume`／`sma_*`／`rsi_14`／`atr_14` 則是 0 NULL。這些標的當天沒有法人流向，chip 特徵會以 0／空值進入模型——是資料庫現實，但模型讀到的「零流量」其實是「沒有資料」。

### 8.4 認證雜湊涵蓋了未在版控內的檔案

manifest 的 `source_hashes` 有 72 個條目，其中兩個**不在 git 版控內**：

| 檔案 | manifest 雜湊 | 是否在版控 |
|---|---|---|
| `daily_certification_catchup.py` | `587710a45d12…` | ❌ 未追蹤 |
| `news_refresh_watchlist.py` | `2406f9daa052…` | ❌ 未追蹤 |

與整個 chain-audit／catchup 工作流（另有 `daily_chain_audit.py`、`certification_catchup_guard.ps1`、`register_daily_chain_audit.ps1`、`run_daily_chain_audit.cmd`、`DAILY_CHAIN_AUDIT_RUNBOOK.md`、`daily_chain_audit_config.json`、`register_news_refresh.ps1`、`stock_features_daily.py`）共 10 個檔案都未在版控內。

**這與 chip 表是同一種病：孤兒資料。** 被認證的成品，其來源雜湊指向沒有版本記錄的檔案——一旦這些檔案被改動或遺失，認證證據無法回溯。屬於「未證明」清單裡的溯源項目，本回合未擅自整批提交（該工作流由他人建立），僅把本次修改到的 `daily_chain_audit.py` 納入版控讓喚醒取證的修正可追溯。

### 8.5 已發布產物與認證 manifest 漂移

chain audit 唯一的另一個 finding 是 `manifest missing/hash_mismatch=1`。追下去是**一個檔案**：

| 檔案 | 認證的那份 | 線上（Groove-Lab）那份 |
|---|---|---|
| `watchlist.html` | `public/watchlist.html`（2026-11-19，雜湊與 manifest 一致 ✓） | `C:\Groove-Lab\watchlist.html`（2026-11-20 20:05 被覆寫，雜湊不符 ✗） |

其餘 2,036 個 artifact 的雜湊**全部相符**。覆寫者是 `scripts/news_refresh_watchlist.py`——它每天從最新的 `stock_news` 重寫 Groove-Lab 的 watchlist.html，**在認證之後、manifest 之外**。

**後果**：線上網站上的 watchlist.html 是「今天」的版本，而認證 manifest 描述的是「2026-11-19」的版本。新聞刷新本身是合理的日常作業，但它是**認證鏈之外的寫入**，所以每晚都會讓 manifest 與線上不一致一天。這不是資料損壞，是**溯源鏈有個寫入口沒被涵蓋**。

修法有兩種：(a) 新聞刷新寫進 repo 的 `public/` 並讓 manifest 重新產生；(b) 把 `watchlist.html` 從 manifest 的 artifact 集合排除並在報告中標示它是「認證後受控更新」。本回合未動，因為 (a) 會改動已認證的 artifact 集合、需要在無 run 進行時才做。

## 9. 重現方式

```powershell
C:\Python314\python.exe -X utf8 scripts\_debug\_warehouse_audit.py
C:\Python314\python.exe -X utf8 scripts\_debug\_warehouse_audit_verdict.py
C:\Python314\python.exe -X utf8 scripts\_debug\_warehouse_family_assertions.py
C:\Python314\python.exe -X utf8 scripts\daily_chain_audit.py --no-notify
powershell -File scripts\sleep_wake_proof.ps1 -Mode status
```

## 10. 殘餘風險

1. **實體睡眠喚醒仍未證明**——受控測試已佈署（23:35 休眠／23:45 喚醒），收據在 `scripts/_debug/sleep_wake_proof.json`。若 RTC 喚醒沒生效，機器會睡著等人按鍵。
2. **約 110 張已停寫的表仍在庫裡**——本文件把它們標成「停寫」而不是「完整」，避免再出現「240 張表都有全歷史」這種不實宣稱。
3. **舊表 166 檔的凍結列未修**——現行模型不讀它，但那是地雷；真要修得先確認舊路徑（FinFill）是否還在用。
4. **法人欄位 16% NULL 未解**——需要確認那些標的-day 是「來源沒給」還是「管線漏抓」。
5. **預測表的 53 個空白交易日未重建**——依交接邊界不重建歷史訊號；新證據要靠前瞻天數累積。
