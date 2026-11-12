# RESP-2026-11-12-01 重訓裁定：根因是 train/serve skew，不是權重過期

**日期**：2026-11-12
**對象**：production XGBoost bundle `daily2_xgboost_20260620182039`
**狀態**：未重訓、未換 bundle、未改線上策略
**前置**：`docs/RESP-2026-11-11-01-model-health-and-retrain-verdict.md`（量測修復與第一輪診斷）

---

## 0. 裁定（改判）

**2026-11-11 的「NO-GO」改判為「條件式 GO」——但重訓不是第一步。**

11-11 的 NO-GO 建立在「證據量不足（29 個可用日期）」與「四項 GO 條件全 FAIL」之上。
12 日的解剖顯示真正的原因不在權重，而在**特徵來源的訓練／服務分布錯配（train/serve skew）**：

- 模型在 **chip 特徵只有 11.4% 覆蓋率**的資料上訓練與驗證，
- 卻在 **99% 覆蓋率**下上線——**上線日是覆蓋率暴增後的第 6 天**。

這不是「權重過期」，所以**單純重訓不會修好它**；但把覆蓋率修好並回填歷史之後，
**重訓就變成必要且合理的一步**。

順序是：**修特徵管線 → 回填歷史 → 加覆蓋率守門 → 重訓 → 閘門改版 → 新鮮前瞻驗證 → 才推廣。**

---

## 1. 根因一：chip 特徵家族的 train/serve skew（這才是主因）

### 1.1 精確時序

| 日期 | `stock_chip_features_daily` 覆蓋 ticker 數 | `data_source` | 事件 |
|---|---|---|---|
| 2020-01-02 ～ 2026-06-11 | **271（佔宇宙 11.4%）** | `daily_data2` | legacy 殘表 |
| **2026-06-12** | **2,377（99.1%）** | `daily_data2_full` | **來源表切換** |
| 2026-06-17 | 2,364 | `daily_data2_full` | 模型訓練資料最後一天 |
| **2026-06-18** | 2,356 | `daily_data2_full` | **模型上線（切換後第 6 天）** |
| 2026-06-20 18:20 | — | — | 模型訓練完成 |

`daily_data2` 只有 271 檔／日（510,607 列／6.5 年）；`daily_data2_full` 有 2,000～2,400 檔／日
（3,691,674 列）。**chip 特徵建置器整段歷史都讀錯來源表，2026-06-12 才換表，歷史從未回填。**

### 1.2 四個視窗的覆蓋率（同一張表）

| 視窗 | 交易日 | 有 chip 列的日子 | 平均 chip ticker / 宇宙 | 覆蓋率 |
|---|---|---|---|---|
| **TRAIN** 2025-01-01~12-31 | 243 | 243/243 | 270 / 2,362 | **11.4%** |
| **VALIDATION** 2026-01-01~03-31 | 55 | 55/55 | 271 / 2,389 | **11.3%** |
| **PLAYBACK** 2026-04-01~06-17 | 53 | 53/53 | 426 / 2,400 | **17.7%**（切換就在此視窗內） |
| **LIVE** 2026-06-18~11-12 | 92 | **55/92** | 1,171 / 1,973 | **59.3%** |

模型的訓練與驗證都在 11.3～11.4%；上線後是 59.3%，而且逐日可以是 99% 也可以是 **0%**。
**chip 家族 30+ 個欄位的輸入分布在訓練與服務之間完全不同。**

### 1.3 這就是閘門震盪的機制

XGBoost 對 NaN 有原生處理，缺失方向是「學到的」。所以「某整族特徵從 11% 覆蓋變成 99% 覆蓋」
不是漸變，是**全帳的輸出分布整體位移**。實測對應：

| 日期 | chip 覆蓋 | 品質收據 | ADD 佔比 | `big_loss20` 地板 |
|---|---|---|---|---|
| 2026-07-31 | **0%**（整表無列） | 正常 | **86.0%** | 0.087 |
| 2026-10-28 | 98.7% | **缺 41 個新聞特徵** | **83.1%** | 0.038 |
| 2026-11-02 | 98.2% | **缺 41 個新聞特徵** | **95.3%** | 0.032 |
| 34 個乾淨日 | ~98.8% | 正常 | 平均 24.3% | 平均 0.133 |

相關性：`chip_cov ↔ ADD佔比` Spearman **−0.626**；`品質收據缺特徵數 ↔ ADD佔比` Pearson **+0.499**。

**管線故障 → 閘門全開 → 發出極度看多的清單 → 在最糟的日子造成最大損失。**
這是最惡劣的失效模式，而且它是**可以在發佈前被擋掉的**。

### 1.4 為什麼只訓練不出現

因為訓練與驗證的覆蓋率一致（11.3～11.4%），**模型在訓練時看到的就是「大部分股票沒有 chip 特徵」的世界**。
當它第一次看到 99% 覆蓋的世界（2026-06-18），它並沒有學到「如何用 chip 特徵」，只學到「沒有 chip 時怎麼預測」。
所以正確的修法不是重訓，而是：**先把覆蓋率拉平，再重訓**。

---

## 2. 根因二：模型本質是「市場計時器」，不是選股器

直接解剖凍結 bundle（`models_daily2_macro_institutional_playbook_bull_2025_2026`）：

| head | 市場狀態特徵佔 gain | Top-1 特徵（gain 佔比） |
|---|---|---|
| `win20_net` | 23.2% | **`breadth_above_sma54`** 5.35% |
| `win20_net_1pct` | 24.3% | **`breadth_above_sma54`** 5.25% |
| `win20_net_2pct` | 26.0% | **`breadth_above_sma54`** 4.68% |
| `big_loss20` | 19.8% | `market_vol_20d` 4.35% |
| `net_return_20d` | **29.6%** | `us_anchor_nvda_vol_5d` 5.46% |
| `target_before_stop` | 22.5% | `us_risk_on_score` 3.29% |
| `stop_before_target` | 22.0% | `market_vol_20d` 4.00% |

- 三個 `p_win` head 的 **Top-1 都是 `breadth_above_sma54`**——全市場廣度，同一天對所有股票相同。
  這種特徵只能整天升降全帳分數，**無法區分個股**。這正是 ADD 佔比能在 1.4%～95.3% 之間跳動的機制。
- 七個 head 的特徵集合重疊度 **Jaccard 0.78～0.85** → 它們不是七個獨立訊號，是同一個模型換七個輸出。
- `breadth_above_sma54` 同時是「模型有沒有 edge」最強的因子（與超額報酬相關 **+0.647**）。
  **模型在市場廣度最低時開最大，而超額報酬在廣度最高時最好——方向是反的。**

### 2.1 模型本身的量測品質

| 指標 | 值 |
|---|---|
| validation AUC（win20_net，2026Q1） | 0.5439 |
| playback AUC（win20_net，2026-04~06-17） | **0.5214** |
| 推廣依據的組合回測 | **40 筆交易**、ROI +58.87%、Sharpe 8.5、MDD −2.82% |
| 推廣時的閘門 | `min_win_prob=0.25`（訓練腳本） |
| 實際上線的閘門 | `min_win_prob=0.50`（`data_policy.json`） |

**AUC 0.52 的模型，靠 40 筆交易的回測被推上架。** n=40 的 ROI 是雜訊；
而報告績效的窗口同時是模型選拔的窗口（`leak_guard` 擋的是欄位名 token，擋不了這層選拔偏誤）。

**所以「重訓能帶來多少 alpha」的答案是：有限。** 重訓能帶來的是**穩定性**，
不是橫截面選股能力。若產品是「每日選股清單」，必須正視這件事。

---

## 3. 根因三：上游 feed 的硬性 outage

| 表 | 缺漏的交易日 | 區段 |
|---|---|---|
| `stock_chip_features_daily` | **37 天** | 2026-07-15~07-17、07-21~08-07、08-12~08-13、08-17~09-16 |
| `us_anchor_features_daily` | **58 天** | 2026-06（7/21）、07（13/17）、08（20/20）、09（18/20） |

chip 的缺漏區段（7/15～9/16）**完全落在模型推論停擺區段（7/8～9/24）之內** →
chip feed 與每日推論共用同一個上游斷線，這也解釋了為什麼 50 天的量測空洞與 chip 覆蓋率翻轉是同一件事。

`us_anchor_features_daily` 2026-08 是 **20/20 全月缺漏**，而 `us_anchor` 佔 `net_return_20d` head 的
最大特徵（5.46%）與多個市場狀態特徵。

---

## 4. 兩個機制的分工（區分清楚，不要混為一談）

| | 機制 | 證據 | 範圍 |
|---|---|---|---|
| **A. 特徵可得性** | 覆蓋率變動 → 全帳輸出位移 | 07-31（chip 0% → ADD 86%）、10-28／11-02（缺 41 特徵 → ADD 83/95%） | 解釋**極端值** |
| **B. 市場狀態關係翻轉** | 廣度→方向的關係在 2025 學到、2026 反轉 | 完整覆蓋的日子裡 `big_loss20` 地板仍在 0.031～0.419 擺動；breadth54 ↔ ADD% −0.509、↔ 超額 +0.647 | 解釋**整體擺動** |

**A 與 B 同時成立。** A 可以用覆蓋率守門擋掉；B 只能用「閘門市場相對化」或重訓來處理。

---

## 5. 重訓裁定與條件

### 5.1 必要前置（沒有這些，重訓只是重複同一個缺陷）

| # | 動作 | 說明 |
|---|---|---|
| P1 | **修 chip 特徵建置器的來源表** | 整段歷史用 `daily_data2_full` 重建。2026-06-12 已經證明這個來源表能產出 99% 覆蓋 |
| P2 | **回填 2020-01～2026-06-11 的 `stock_chip_features_daily`** | 讓訓練視窗的覆蓋率與推論一致（≥95%） |
| P3 | **修 `us_anchor_features_daily` 的缺日** | 2026-06～09 有 58 天沒有列，2026-08 整月空白 |
| P4 | **覆蓋率守門（fail-closed）** | 推論當日若任一來源表的覆蓋率偏離訓練基準（例如 chip < 95%），**不發布 ADD 訊號**，只記錄 |

> P1～P3 是資料管線工程，不是模型工程。**在它們完成前重訓是浪費。**

### 5.2 重訓規格（到時候照這份跑）

```powershell
cd D:\CODEX\AI-Telegram
C:\Python314\python.exe taiwan_stock_report\train_daily2_swing_ai.py `
  --source-table daily_data2_full --universe core_stock `
  --feature-set all_layer12_layer13_institutional_playbook --model xgboost --require-gpu `
  --models-dir <NEW_DIR> --outdir <NEW_OUTDIR> `
  --train-start 2023-01-01 --train-end 2026-03-31 `
  --validation-start 2026-04-01 --validation-end 2026-06-17 `
  --playback-start 2026-06-18 --playback-end 2026-11-12 `
  --hold-days 20 --roundtrip-cost 0.0078 --big-loss-threshold -0.08 `
  --target-pct 0.08 --stop-pct -0.05 --top-k 20 --capital 1000000 --max-pos 20 `
  --min-win-prob 0.50 --max-loss-prob 0.98 `
  --portfolio-score p_win20_net_1pct --portfolio-exit-mode fixed
```

- 新的 `model_version`、自己的 SHA256、舊 bundle 保留為 rollback reference。
- **不要**沿用 2026-04~06-17 當推廣依據（已被 06-20 的選拔用過）。
- 訓練視窗必須先通過 P2 的覆蓋率檢查，否則特徵分布還是錯配的。

### 5.3 推廣門檻（把 40 筆交易的門檻換掉）

| 條件 | 門檻 |
|---|---|
| 連續量測 | ≥ 60 個有預測的交易日，且覆蓋缺口已宣告 |
| purged walk-forward OOS | 贏過**同日宇宙**（市場相對），且勝率 +≥3pp 或平均報酬 +≥0.5% |
| 贏過自己的 HOLD 基準 | 必須贏（現在輸 4.4pp） |
| 橫截面訊號 | AUC ≥ 0.56（現在 playback 0.52） |
| 組合指標 | **交易數 ≥ 200**（現在 40），且 ROI 需在 ≥2 個不重疊視窗皆為正 |
| 穩定性 | 閘門寬度日變動（`big_loss20` 地板）≤ 訓練期水準；退化日不發布 |
| **新鮮前瞻驗證** | 設計凍結後累積 **≥ 40 個新交易日**的連續 ledger，門檻同上 |

### 5.4 與權重無關、但必須一起做的閘門改版

1. **縮減發佈廣度**（每日 ~50 檔，而非 300～990）
2. **退化日保護**（品質收據報缺特徵 → 縮減或停止發佈）
3. **閘門市場相對化**（綁定 breadth，不再讓單一 head 的絕對機率決定全帳）
4. **移除／反轉 `pred_net_return ≥ 0`**（該頭在 ADD 書內反向：最高五分位 −4.03% vs 中段 −1.75%）

---

## 6. 與 2026-11-11 裁定的關係

11-11 的 NO-GO **沒有錯在結論方向，而是錯在「可行動性」**：當時只知道證據量不足、
不知道錯配在哪。12 日的解剖把「為什麼會這樣」定位到具體機制，因此：

| 11-11 | 12-12 |
|---|---|
| NO-GO（證據不足、四項條件全 FAIL） | **條件式 GO**（先修管線 → 再重訓） |
| 建議：縮減廣度、退化日保護、閘門市場相對 | 同上，且**新增 P1～P4 資料管線前置** |
| 「重訓是雜訊上做決策」 | 「重訓必要，但必須在覆蓋率拉平之後，且驗證門檻要換掉 40 筆交易那一套」 |

---

## 7. 這份文件沒有回答的問題

- **沒有實際跑重訓**，因為在 P1～P3 完成前跑出來只會是同一個錯配的複製品。
- **沒有量化「覆蓋率拉平」後 AUC 會到多少**——那是重訓後才知道的事。
- **2020-01～2023-12 的 chip 回填是否可行**尚未驗證（需看 `daily_data2_full` 的法人欄位歷史完整度）。
- **`us_anchor_features_daily` 2026-06～09 缺 58 天能否補齊**尚未驗證（需看美股錨點原始資料的保留期限）。
- **`daily_data2` 與 `daily_data2_full` 以外**是否還有其他特徵表有同樣的來源表問題，未逐一稽核。

---

## 8. 重現方式

```powershell
C:\Python314\python.exe <workspace>\scripts\_debug\_bundle_anatomy.py        # 各 head 的 gain 結構
C:\Python314\python.exe <workspace>\scripts\_debug\_feature_mismatch.py     # 各來源表覆蓋率
C:\Python314\python.exe <workspace>\scripts\_debug\_coverage_transition.py  # 轉換點與缺口
C:\Python314\python.exe <workspace>\scripts\_debug\_coverage_vs_gate.py     # 覆蓋率 vs 閘門寬度
C:\Python314\python.exe <workspace>\scripts\_debug\_phase1_diagnosis.py      # 11-11 的診斷
C:\Python314\python.exe <workspace>\scripts\_debug\_rule_comparison.py      # 規則比較 + split-half
```

**證據來源**

- bundle：`D:\CODEX\AI-Telegram\taiwan_stock_report\models_daily2_macro_institutional_playbook_bull_2025_2026\`
- 特徵表：`stock_chip_features_daily`（`data_source` 欄位）、`daily_data2` vs `daily_data2_full`
- ledger：`D:\CODEX\AI-Telegram\output\forward_validation\forward_validation_log.csv`
- 訓練設定：`taiwan_stock_report\output\daily2_macro_institutional_playbook_bull_2025_2026\metrics.json`
