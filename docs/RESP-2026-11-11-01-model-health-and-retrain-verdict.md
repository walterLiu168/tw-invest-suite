# RESP-2026-11-11-01 模型健康度與「是否重訓」裁定

**日期**：2026-11-11
**範圍**：`tw-invest-suite`（呈現層）＋ `AI-Telegram`（模型與 ledger）
**對象**：production XGBoost bundle `daily2_xgboost_20260620182039`
**狀態**：分析完成，未重訓、未換 bundle、未改線上策略

---

## 0. 裁定

**不重訓（NO-GO）。** 在 Phase 0 之前就寫死的四項 GO 條件全部 FAIL。

但真正的結論比「不重訓」更有用：**模型不是壞掉，是發佈廣度壞掉。** 同一個模型在同一天，
取 50 檔等權組合比全宇宙好 +1.08%，但把它每天 300～990 檔全發出去，就比全宇宙差 1.22pp。
而且閘門開得最大的日子，恰好是市場廣度最低的日子。

---

## 1. 模型本體（事實，全部來自 bundle 本身，不是 CHANGELOG 轉述）

| 項目 | 值 |
|---|---|
| model_version | `daily2_xgboost_20260620182039` |
| 訓練完成 | 2026-06-20 18:20:39 |
| feature_set | `all_layer12_layer13_institutional_playbook`，353 個特徵 |
| splits | train `2025-01-01~2025-12-31`／validation `2026-01-01~2026-03-31`／playback `2026-04-01~2026-06-17` |
| universe / source | `core_stock`／`daily_data2_full` + market_event + stock_chip + news_topic + us_anchor |
| 訓練入口 | `D:\CODEX\AI-Telegram\taiwan_stock_report\train_daily2_swing_ai.py` |
| production gate | `min_win_prob=0.50`、`max_loss_prob=0.98`、`reduce_loss_prob=0.65`、`min_return=0.0` |

**訓練資料只有 2025 一年。** 模型從沒看過 2026。

---

## 2. Phase 0：先把量測修好（這是本次的前置工程，沒有它一切無從談）

原本的 forward-validation ledger 有四個靜默缺陷，導致「5 個月的 OOS 證據」其實只有 23～26 個訊號日：

1. 只追蹤 `ADD`，`REDUCE`／`HOLD` 完全沒有驗證資料
2. 每天只寫「最新」預測日 → 被跳過的日期從證據基礎消失
3. 品質退化的列被**靜默丟棄** → 整個日期從證據基礎消失
4. `ledger_origin` 每列都寫成 `stored_db_signal_backfill` → 這個欄位沒有任何資訊

### 2.1 修好之後

| 項目 | 修好前 | 修好後 |
|---|---|---|
| ledger 列數 | 8,160 | **36,522** |
| 有預測的日期 | 23～26（有效回報） | 35（有預測）／31（有 5 日回報）／29（品質合格且有回報） |
| 動作 | ADD only | ADD 10,118／REDUCE 15,310／HOLD 11,094 |
| `ledger_origin` | 全是 backfill | published_signal 22,073／stored_db_signal_backfill 14,449／無空白 |
| 覆蓋缺口 | 無人知道 | `coverage.missing_prediction_date_ranges` 明確宣告 |
| 退化日 | 靜默消失 | 記錄並標記（10-28、11-02） |

### 2.2 覆蓋缺口（不重建，只宣告）

`model_predictions_daily` 在以下區段完全沒有任何列：

| 起 | 迄 | 交易日數 |
|---|---|---|
| 2026-06-23 | 2026-06-25 | 3 |
| 2026-06-29 | 2026-07-01 | 3 |
| 2026-07-08 | 2026-07-30 | 11 |
| 2026-08-03 | 2026-09-24 | 38 |

**這些日期沒有重建。** 重跑歷史推論等於製造從未發布過的前瞻證據，違反
`docs/MINIMAX_P0_HANDOVER_2026-09-30.md` 的治理邊界。缺口被宣告，不被填補。

### 2.3 工程驗證

- 20 個測試通過（既有 7 + 新增 13）
- 向量化 outcome 更新 vs 原本逐列實作：5,207 列 × 8 欄 **cell-by-cell 0 差異**
- 重建驗收：原有 8,160 列 0 遺失、0 訊號或已完成報酬被改寫
- 冪等：連續兩次 `--backfill-all` 產出 byte-identical CSV
- 效能：日常 7.5 秒、全量回填 10.3 秒（原本 143 秒，超過 cron 的 120 秒預算 → 已修）
- 既有 summary 頂層語意未變：ADD 品質合格子集；06:30 audit 讀的三個欄位全部未變

---

## 3. Phase 1：證據

### 3.1 GO／NO-GO（條件在 Phase 0 之前寫死）

| 條件 | 結果 | 實測 |
|---|---|---|
| 連續量測 ≥ 60 個交易日 | **FAIL** | 35 個預測日（29 個品質合格且有回報） |
| purged OOS：ADD 勝率贏過同日宇宙 ≥ +3pp | **FAIL** | −5.65pp |
| purged OOS：ADD 平均報酬贏過宇宙 ≥ +0.5% | **FAIL** | −1.23% |
| purged OOS：ADD 贏過模型自己的 HOLD 基準 | **FAIL** | ADD 0.212 vs HOLD 0.256 |

### 3.2 兩種加權，講的是兩件事

| 視角 | 問題 | ADD | 宇宙 | 差 |
|---|---|---|---|---|
| **列加權**（每則推薦算一票） | 「照整份清單做，會不會輸大盤？」 | −4.50% | −3.28% | **−1.22pp（輸）** |
| **日期加權**（每天等權 50 檔） | 「同一天挑 50 檔，會不會贏大盤？」 | −1.26% | −2.34% | **+1.08pp（贏），72.4% 的日子贏** |

purged（非重疊 5 日視窗）後仍然成立。

**這兩件事不矛盾：** 閘門開得大的日子，它發出的清單幾乎就是整個宇宙（沒有選到東西），
而那種日子正是虧損的來源。**模型的 edge 只存在於它「有話要說」的日子。**

### 3.3 閘門寬度

| 閘門寬度 | 天數 | 平均 ADD 佔比 | ADD 平均報酬 | 對宇宙超額 |
|---|---|---|---|---|
| 廣（≥50%） | 7 | 83.1% | −4.23% | **−0.15%** |
| 中（15–50%） | 9 | 26.4% | −0.97% | +0.89% |
| 窄（<15%） | 15 | 7.3% | −0.98% | **+1.65%** |

**閘門越寬，模型越沒有價值。**

### 3.4 市場狀態 → 閘門（最重要的單一發現）

| 特徵 | 與 ADD 佔比相關 | 與 big_loss 地板相關 | 與「ADD−宇宙超額」相關 |
|---|---|---|---|
| `breadth_above_sma54` | **−0.509** | +0.253 | **+0.647** |
| `breadth_above_sma27` | −0.495 | +0.165 | +0.620 |
| `breadth_above_sma13` | −0.451 | +0.023 | +0.519 |
| `event_risk_score` | −0.562 | +0.163 | +0.346 |
| `advance_ratio` | +0.077 | −0.144 | +0.081 |

**閘門在市場廣度最低時開得最大，而模型的超額報酬恰好在廣度最高時最好。**
`breadth_above_sma54` 是「模型有沒有 edge」最強的單一預測因子（+0.647）。

### 3.5 退化日（缺 41 個新聞特徵）

| | 天數 | ADD 勝率 | ADD 平均 | 宇宙平均 | 超額 |
|---|---|---|---|---|---|
| 退化 | 2 | 0.059 | −8.27% | −8.54% | **+0.27%** |
| 品質合格 | 29 | 0.359 | −1.26% | −2.34% | **+1.08%** |

**模型的 edge 幾乎完全來自新聞／籌碼特徵。** 缺了它，edge 歸零——而閘門同時把 ADD 灌到 89.2%。
**管線故障會變成「極度看多」的訊號書**，這是最糟的失效模式。

同一批退化日上，各規則的超額：EV top-50 **+3.45%**、p_win top-50 +1.93%、
p_win top-50 & p_big_loss<0.65 **+2.85%**、現行全清單 **+0.26%**。
→ 退化日只要**縮減發佈**，傷害就大幅下降。

### 3.6 排序輸入：哪一個 head 是反的

| 輸入 | 前 400 名 | 後 400 名 | 差距 |
|---|---|---|---|
| `p_win20_net_1pct` | hit 0.790／**+5.18%** | hit 0.228／−5.50% | **+10.68pp** |
| `expected_value_score` | hit 0.323／−2.25% | hit 0.190／−7.71% | +5.46pp |
| `pred_net_return` | hit 0.282／−4.98% | hit 0.182／−7.24% | +2.26pp |

`p_win` 這個 head 分得出尾巴。但**在 ADD 書之內**，`pred_net_return` 的最高五分位最差：

| `pred_net_return` 五分位 | 勝率 | 平均報酬 |
|---|---|---|
| Q1（+0.0000~+0.0069） | 0.315 | −2.12% |
| Q2（+0.0070~+0.0132） | 0.377 | −1.75% |
| Q3（+0.0132~+0.0195） | 0.373 | −1.75% |
| Q4（+0.0195~+0.0278） | 0.321 | −2.77% |
| **Q5（+0.0278~+0.1938）** | **0.256** | **−4.03%** |

而 production gate 的 `min_return=0.0` 條件正是「pred_net_return ≥ 0」→
**閘門用的那個排序頭，在它自己挑出來的書裡是反的。**
佐證：HOLD 書中 `p_win ≥ 0.60` 的 138 列，平均 **+7.08%**（勝率 0.688）——
**閘門把模型最有把握的標的直接丟進了 HOLD。**

### 3.7 沒有任何替代規則穩健地贏

split-half（前半選規則、後半驗證）：

- 用 A 選 → `top20 p_win`；在 B 上 −3.65%（宇宙 −4.09%，**現行 ADD −3.22%**）
- 用 B 選 → `top20 p_win`；在 A 上 −0.08%（宇宙 −0.70%，**現行 ADD +0.57%**）

**兩個方向都輸給現行 ADD。** → 換排序規則沒用。修的是廣度與閘門，不是排序。

### 3.8 可交易性

只有 **50.3%** 的 ADD 列在預測當天就存在於 `model_predictions_daily`（`signal_lag_days = 0`），
其餘是事後寫入。若要主張「當天就能下單」，只能用 `published_signal` 子集。

---

## 4. 診斷

1. **模型本身接近 beta，沒有穩定 edge。** 這不是「過期」的問題——訓練資料只有 2025，
   但重訓成 2023–2026 大概率只是把同樣的結構性耦合烤進新 bundle。
2. **`pred_net_return` head 在 ADD 書內反向**，而 production gate 正是用它篩選。
3. **閘門在市場廣度最低時開最大**（`breadth54 ↔ ADD% = −0.509`），方向是反的。
4. **發佈廣度是價值的破壞者**：整份清單輸大盤 1.22pp，縮到 50–100 檔就贏 0.7–1.4pp。
5. **輸入品質退化會同時消滅 edge 並把閘門打開** → 管線故障的失效模式最惡劣。

---

## 5. 建議動作

### A. 不重訓（最高優先）

四項 GO 條件全 FAIL。**現在重訓是把 26 天的雜訊當成真相。**

### B. 縮減發佈廣度（最高槓桿）

每日只發佈有限檔數（例如 50，而不是 300～990）。

- 依據：列加權 purged ADD −4.50% vs 宇宙 −3.28%；日期加權 50～100 檔組合 +0.70~+1.37% vs 宇宙
- 這**不是**「換一個更好的排序規則」（見 3.7），而是「不要把沒有選到東西的日子也發成滿版清單」
- ⚠️ 這是**線上策略變更**，需要 Walter 明確授權；且必須先用修好的 29～31 日樣本做 out-of-sample 驗證

### C. 退化日保護

當 `daily_input_quality` 顯示有缺特徵時，縮減或停止發佈 ADD。
退化日上 EV top-50 超額 +3.45% vs 全清單 +0.26%，縮減的效益最明顯。

### D. 閘門改為市場相對

把「閘門開多大」綁到市場廣度，而不是單一 head 的絕對機率。
`breadth_above_sma54` 對「模型有沒有 edge」的相關性 +0.647，是目前已知最強的因子。

### E. 移除或反轉 `pred_net_return ≥ 0` 條件

該頭在 ADD 書內反向（Q5 最差 −4.03%）。保留 `p_win` 作為主要門檻。

### F. 不重建 7/8–9/24

治理邊界。缺口宣告即可。

---

## 6. 這份文件沒有回答的問題

- **沒有做新模型訓練**，因此沒有「新 bundle 的 OOS 證據」。A 案的 NO-GO 是依現有證據下的結論，
  不是「已證明新模型也沒用」。
- **沒有把 `pred_net_return` 換掉**。反向的成因（特徵漂移？標籤定義？市場狀態特徵主導？）尚未定位；
  3.6 只證明「它在這段期間、在 ADD 書內反向」。
- **38 個交易日的空白仍然空白**，所以「模型在 7～9 月表現如何」目前無法回答。
- **`breadth54` 與 edge 的 +0.647 相關是 29 個日期的樣本**，n 很小，屬於假說而非定論。
- **只評估了 5 日與 10 日報酬**，沒有評估 20 日持有期（模型原始目標是 hold_days=20）。

---

## 7. 重現方式

```powershell
# Phase 0 產物
C:\Python314\python.exe D:\CODEX\AI-Telegram\taiwan_stock_report\forward_validation_log.py --refresh-only --date 2026-11-10
C:\Python314\python.exe -m pytest D:\CODEX\AI-Telegram\test_forward_validation_refresh.py D:\CODEX\AI-Telegram\test_forward_validation_coverage.py -q

# Phase 1 分析（唯讀）
C:\Python314\python.exe <workspace>\scripts\_debug\_phase1_diagnosis.py
C:\Python314\python.exe <workspace>\scripts\_debug\_gate_input_test.py
C:\Python314\python.exe <workspace>\scripts\_debug\_rule_comparison.py
C:\Python314\python.exe <workspace>\scripts\_debug\_accept_ledger_rebuild.py
C:\Python314\python.exe <workspace>\scripts\_debug\_verify_vectorised.py
```

**證據來源**

- ledger：`D:\CODEX\AI-Telegram\output\forward_validation\forward_validation_log.csv`
  （修好前備份：`forward_validation_log.before_phase0_20261111.csv`）
- summary：`D:\CODEX\AI-Telegram\output\forward_validation\summary.json`
- 推論來源：`model_predictions_daily`（`daily2_xgboost_20260620182039`）
- bundle：`taiwan_stock_report\models_daily2_macro_institutional_playbook_bull_2025_2026\metadata.json`
