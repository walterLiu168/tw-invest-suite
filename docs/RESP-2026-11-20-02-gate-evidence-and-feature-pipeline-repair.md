# RESP-2026-11-20-02 閘門重算、特徵管線修補與重訓

**日期**：2026-11-20
**對象**：production XGBoost bundle `daily2_xgboost_20260620182039`、閘門 `daily_prediction.min_win_prob / max_loss_prob`、前瞻驗證 ledger
**狀態**：閘門門檻**未改**（證據不足，見 §1）；特徵管線缺口**已補**；重訓已執行（§4）；**未推廣、未換線上 bundle**
**承接**：`docs/RESP-2026-11-12-01-retrain-root-cause-and-terms.md`（P1～P4 的前置定義）、
`docs/RESP-2026-11-20-01-nightly-failure-root-cause-and-recovery.md`（11/19 nightly 失敗與恢復）

---

## 0. 結論先講

**「重算閘門門檻」這題的誠實答案是：現在的證據基礎撐不起任何門檻。** 不是「閘門沒價值」，
是「閘門的評估跑在錯的時鐘上，而且被評估的那段期間閘門幾乎沒有開過」。

三件事同時成立：

1. **期限錯配**。模型是 20 日模型（`p_win20_net_1pct`、`p_big_loss20`、`pred_net_return`），
   但前瞻驗證 ledger 只記 `horizon_5d` 與 `horizon_10d`——**閘門從來沒有被用它自己的期限評估過**。
   在同一列組（78 列、2 天）上：ADD 超額 5 日 +2.71pp、10 日 +0.41pp、20 日 +7.51pp，
   但**絕對報酬** 5 日 −2.12%、10 日 +1.31%、20 日 −3.59%。
   只看 ledger 現有的 5d／10d，會把這批訊號讀得比實際好（10 日是唯一顯示正絕對報酬的期限）。
2. **可評估樣本太少**。改到 20 日期限後，22 個有完整 20 日結果的交易日裡，閘門只在
   **2 天**（2026-06-18、2026-06-22）觸發 ADD，共 **78 列**——只佔閘門自身 4,892 列的 1.6%。
   78 列不足以定門檻。
3. **上游特徵管線有三個缺口**（§2），它們才是閘門行為不穩的主因。閘門是症狀，管線是病因。

所以本回合的做法是：**先修證據層與管線，再談門檻。** 閘門門檻維持 `0.50 / 0.98` 不動，
因為 RESP-2026-11-12-01 §5.3 的兩條累積條件都還是 0：
「連續量測 ≥ 60 個**有預測的交易日**」與「新鮮前瞻驗證 ≥ **40 個新交易日**的連續 ledger」。

---

## 1. 閘門重算：期限錯配與樣本不足

### 1.1 現行閘門

| 參數 | 值 | 出處 | 角色 |
|---|---|---|---|
| `min_win_prob` | 0.50 | `config/data_policy.json` → `daily_prediction.min_win_prob` | ADD 門檻（`p_win20_net_1pct`） |
| `max_loss_prob` | 0.98 | `config/data_policy.json` → `daily_prediction.max_loss_prob` | ADD 門檻（`p_big_loss20`） |
| `min_return` | 0.0 | 程式預設（`daily_prediction_refresh.py::prediction_args` 的 `min_return=0.`） | ADD 門檻（`pred_net_return`） |
| `reduce_loss_prob` | 0.65 | 程式預設（同上，`reduce_loss_prob=.65`） | REDUCE 否決（`p_big_loss20`） |
| — | `pred_net_return ≤ −0.03` | 程式常數（`choose_action`） | REDUCE 否決 |

（`data_policy.json` 的 `daily_prediction` 區塊只有 `production_model_version`／`production_model_dir`／
`min_win_prob`／`max_loss_prob`／`min_source_coverage`／`rollback_reference`；
`min_return` 與 `reduce_loss_prob` 不在政策檔裡，是呼叫端給的預設值。）

決策邏輯（`taiwan_stock_report/model_predictions_daily.py::choose_action`）：
先判 REDUCE（`p_big_loss20 ≥ 0.65` 或 `pred_net_return ≤ −0.03`），再判 ADD，否則 HOLD。

### 1.2 三個期限、同一列組

**列組定義（單一母體，三個期限共用）**：
`input_quality_ok = True` ∧ 現行閘門判為 ADD ∧ 預測日有 20 日結果可用 → **78 列、2 個預測日**
（2026-06-18：67 列、2026-06-22：11 列）。每個期限各有 1 列沒有實現值，故 n=77。

市場基準＝同一批日期上、全部 quality-ok 列的等權平均（同一成本口徑）。

| 期限 | 口徑 | n | ADD 勝率 | ADD 平均 | 市場等權平均 | ADD 超額 |
|---|---|---|---|---|---|---|
| 5 日 | 毛（ledger 的 `return_5d`） | 77 | 20.78% | −2.12% | −4.83% | **+2.71pp** |
| 5 日 | 淨（−0.78% 成本） | 77 | 18.18% | −2.90% | −5.61% | +2.71pp |
| 10 日 | 毛（ledger 的 `return_10d`） | 77 | 48.05% | +1.31% | +0.90% | **+0.41pp** |
| 10 日 | 淨（−0.78% 成本） | 77 | 40.26% | +0.53% | +0.12% | +0.41pp |
| 20 日 | 淨（−0.78% 成本） | 77 | 31.17% | −3.59% | −11.09% | **+7.51pp** |

（超額對成本不敏感——兩邊扣同一個成本，差值不變；市場欄與超額欄用同一批日期、同一種加權。）

**這批訊號在三個期限都贏過市場，但量級差 18 倍，而且絕對報酬是負的**：
5 日 −2.12%、10 日 +1.31%、20 日 −3.59%（市場當天分別是 −4.83%、+0.90%、−11.09%）。
也就是說：**只用 ledger 現有的 5d／10d 去看，會把這批訊號讀得比實際好**——
10 日是唯一顯示正絕對報酬的期限，而模型要預測的 20 日絕對報酬其實是負的。

閘門挑的是「20 日會回來的股票」，評估它的視窗必須也是 20 日，否則讀到的是另一個故事。

> 附帶更正：本文件早前版本引用過一組 ADD 統計，但那組數字來自**另一個母體**
> （涵蓋 40 個預測日、805 筆 ADD 的廣母體），不是這 78 列的統計，已從本文移除。
> 早前「同一列組在 5 日與 20 日結論相反」的說法也一併撤回：
> 在同一母體上超額三個期限都是正的，符號並未翻轉，真正改變的是量級與絕對報酬。
> 重現：`scripts/_debug/_gate_same_rows.py`。

### 1.3 為什麼 20 日的樣本只有 78 列

| 視窗 | 有 20 日結果的預測日 | 閘門觸發 ADD 的日 | ADD 列數 |
|---|---|---|---|
| 2026-06-18~2026-11-19 | 22 | **2**（2026-06-18: 67、2026-06-22: 11） | 78 |
| 同上 | | 閘門自身的全部 ADD 列 | 4,892 |

閘門在 ledger 的 40 個預測日裡只在 **10 天**觸發 ADD，逐日列數（加總 4,892）：

| 日期 | quality-ok 列 | ADD | ADD 佔比 |
|---|---|---|---|
| 2026-11-19 | 1,042 | 135 | 12.96% |
| 2026-11-18 | 1,041 | 33 | 3.17% |
| 2026-11-17 | 1,040 | 1,020 | 98.08% |
| 2026-11-16 | 1,040 | 996 | 95.77% |
| 2026-11-13 | 1,035 | 967 | 93.43% |
| 2026-11-12 | 1,037 | 1,016 | 97.97% |
| 2026-11-11 | 1,038 | 333 | 32.08% |
| 2026-11-10 | 1,040 | 314 | 30.19% |
| 2026-06-22 | 971 | 11 | 1.13% |
| 2026-06-18 | 1,189 | 67 | 5.63% |
| **合計** | | **4,892** | |

其餘 30 個預測日**一天都沒開過**（2026-06-26~2026-10-20 全為 0）。

> **母體與來源**：ledger `output/forward_validation/forward_validation_log.csv`，
> `input_quality_ok = True` ∧ 依 ledger 自身的 `p_win20_net_1pct`／`p_big_loss20`／
> `pred_net_return` 重算的現行閘門。**與 DB `model_predictions_daily.ai_action` 不是同一個母體**：
> DB 保留了品質退化日的原始動作（例如 2026-11-18 DB 記 ADD=41，ledger 的品質完整子集只有 33）。
> 本節與 §1.4 的所有數字都出自這個母體。重現：`scripts/_debug/_authoritative_readings.py`。

原因在 §1.4 的 head 擺動。

### 1.4 真正的上游：`big_loss20` 地板整天翻轉

`p_big_loss20` 的**當日最小值**（floor）逐日變動：

| 日期 | quality-ok 列 | floor | ADD | ADD 佔比 | 說明 |
|---|---|---|---|---|---|
| 2026-09-29 | 518 | 0.033 | 0 | 0% | floor 最低 |
| 2026-06-18 | 1,189 | 0.061 | 67 | 5.63% | |
| 2026-11-12 | 1,037 | 0.035 | 1,016 | **97.97%** | floor 崩到最低 → 幾乎全帳 ADD |
| 2026-11-06 | 991 | 0.432 | **0** | **0%** | floor 最高 → 幾乎全帳 REDUCE |

（母體同 §1.3。2026-11-06 在 DB 裡另有 48 筆 ADD，但那些是品質退化列，不在本母體內。）

floor 在相鄰日之間擺動 **13 倍**，而 REDUCE 的否決門檻是 0.65：floor 一旦抬高，
`big_loss20 ≥ 0.65` 的列數從 364（06-18）飆到 **980**（11-06），
整帳在 ADD 與 REDUCE 之間翻面。

**這不是門檻問題。** 任何門檻都只是在這條全帳翻轉的基礎上做取捨。
這也解釋了為什麼同一列組在不同期限上會給出不同的答案：被翻轉的那幾天，正好是市場最糟的那幾天。

### 1.5 結論

| 選項 | 判定 |
|---|---|
| 直接改 `min_win_prob` / `max_loss_prob` | **不做**。78 列、2 個交易日、且集中在同一個崩盤 regime；任何門檻都只是過度配適。 |
| 把門檻放寬以提高樣本 | **不做**。會放大 §1.4 的全帳翻轉——閘門越寬，翻轉的日子發出越多 ADD。 |
| 先修期限與管線，門檻留待新鮮前瞻驗證 | **採用**。§3 已完成證據層與管線修補；RESP-2026-11-12-01 §5.3 的「新鮮前瞻驗證」條件
（設計凍結後累積 ≥ 40 個新交易日的連續 ledger）尚未開始。 |

門檻重算的前提是「用模型自己的期限、在閘門真的會開的日子上、用足夠的樣本」。
本回合把前兩項補上了（§3），第三項要等時間。

---

## 2. 上游：特徵管線的三個缺口

2026-11-12 的裁定把主因歸給 chip 家族的 train/serve skew。本回合量測後，
**缺口有三個**，而且三個的性質不同。

### 2.1 chip 特徵：來源表中途切換（缺口最大，已補）

`stock_chip_features_daily` 有一欄 `data_source`，直接記錄了建置時讀的來源表：

| 區段 | `data_source` | 每日覆蓋 | 佔當日宇宙 |
|---|---|---|---|
| 2020-01-02 ~ 2026-06-11 | `daily_data2` | 271 檔 | **11.4%** |
| 2026-06-12 ~ 2026-11-19 | `daily_data2_full` | 1,942~1,962 檔 | **100%** |

模型的訓練窗（2025）落在 11.4% 那一段，服務窗落在 100% 那一段。

**更正一項舊數字**：2026-11-12 的文件寫 live 視窗覆蓋率 59.3%／99.1%，那是用「視窗內累積
distinct 檔數」（2,436）當分母，而不是「每日檔數」（1,962）。逐日重算後，
`daily_data2_full` 每日約 **1,962** 檔，chip 表的 live 區段每日 **1,942~1,962** 檔，
即 **100% 覆蓋**。真正有問題的是**訓練窗的 11.4%**，不是服務窗。

> 這個更正很重要：先前「live 覆蓋率只有 59.3%」的敘述會讓人以為服務窗也有洞，
> 事實上服務窗是滿的，洞全在歷史端——而洞的位置正好落在訓練窗。

建置器本身**一直存在**：`D:\CODEX\AI-Telegram\data-downloader\stock_chip_features.py`，
而且本來就有 `--source-table {daily_data2 | daily_data2_full}` 參數。
每日管線呼叫（`strategy_lab/daily_pipeline.py::stock_chip_features_cmd`）本來就傳
`--source-table daily_data2_full`；**是歷史區段當初用 `daily_data2` 建的，而從未回填。**
（先前花費時間尋找「不存在的建置器」，是因為它不直接出現 `stock_chip_features_daily`
這個字串，而是用 `--source-table` 參數切換。）

### 2.2 us_anchor 特徵：2026-06-22~09-30 缺 64 天（已補）

`us_anchor_features_daily` 涵蓋 2021-01-04~2026-11-19，逐月缺漏如下：

| 區段 | 有列日 / 應有交易日 |
|---|---|
| 2021-01 ~ 2026-06-21 | **完整** |
| 2026-06-22 ~ 2026-06-30 | 0 / 7 |
| 2026-07 | 4 / 17 |
| 2026-08 | **0 / 20** |
| 2026-09 | 2 / 20 |

live 視窗因此只有 **39/97** 天有 us_anchor 列。us_anchor 是 `net_return_20d` head 的
Top-1 特徵（gain 佔比 5.46%），缺 60% 的日子等於服務時把整族特徵讀成 0。

原始資料（Yahoo）仍可取得，`data-downloader/us_anchor_features.py` 直接重跑即可補回。

### 2.3 新聞特徵：衍生管線自 2026-06-27 中斷

`news_sentiment_daily` 最後一列是 **2026-06-27**；`news_topic_features_daily` 的 live 視窗
只有 **41/97** 天有列（2026-07 只有 1 天、2026-08 整天沒有、2026-09 只有 2 天）。

但**原料完整**：`stock_news` 有 2,434,706 篇，2026-07/08/09 分別有 34,672 / 40,983 / 35,720 篇。
壞掉的是衍生管線，不是資料來源。

這解釋了 2026-11-12 文件記錄的「2026-10-28、2026-11-02 缺 41 個新聞特徵 → ADD 佔比 83.1%／95.3%」：
缺新聞特徵的日子，閘門全開。

**這一族有結構性問題，不只是斷線。** 兩條收集路徑的密度不同：

| | 有新聞的交易日 | 每日有新聞的標的數 |
|---|---|---|
| train 2023-01~2026-03-31 | 779 / 779 | 平均 **16.3**（min 5、max 44） |
| validation 2026-04~06-17 | 53 / 53 | 平均 28.2 |
| live 2026-06-18~11-19（修補前） | 41 / 97 | 平均 25.7，但有 **56 天完全為 0** |

- **用每日管線重跑歷史日期沒有用**：`news_topic_features.py` 走 Google News RSS，
  RSS 只給近期文章，重跑五個月前只會得到 **0~3** 檔／日（實測），遠低於正常的 16~44。
- **改用本地原料庫重跑可行但密度不同**：`stock_news` 保留了完整的爬取結果
  （2026-06-25 當日窗內有 1,565 篇），以 `--items-path` 餵給同一支建置器，
  該日由 1 檔變成 **72 檔**——比訓練窗的日均 16.3 檔還多。

所以新聞家族的缺口有兩層：① 56 天完全沒有新聞（服務時模型會讀到「整天零新聞」這個
訓練時從未出現的狀態）；② 用原料庫補回後，服務窗密度會是訓練窗的 2~4 倍。
**前者用原料庫補回即可消除，後者要嘛把訓練窗也用原料庫重建（924 天，約 7.7 小時），
要嘛把新聞家族整族排除在特徵集之外。** 兩者都需要另外的授權，本回合只做前者。

### 2.4 三個缺口的共同形態

| | 訓練窗（2025） | 服務窗（live） | 性質 |
|---|---|---|---|
| chip | 11.4% | 100% | 歷史端建置來源表錯誤，**可完整回填** |
| us_anchor | 100% | 40% | 服務端中斷，**可完整回填** |
| news | 100% | 35% | 服務端衍生管線中斷，**可完整回填** |

三個都是「一端滿、一端空」的分布錯配，而 XGBoost 對 NaN 原生處理 →
**缺特徵的方向是學到的**。所以「某整族特徵從 11% 覆蓋變成 100% 覆蓋」不是漸變，
是全帳輸出分布的整體位移。

---

## 3. 已完成的修補

### 3.1 證據層：ledger 增加 20 日期限

`taiwan_stock_report/forward_validation_log.py`

- `load_rows()` 新增 `horizon_20d_status` / `horizon_20d_date` / `close_20d` / `return_20d`
- `update_outcomes()` 的期限迴圈由 `(5, 10)` 改為 `(5, 10, 20)`
- `write_summary()` 新增 `pending_20d`、`model_horizon_trading_days`，
  頂層與 `by_action` 的勝率／平均報酬都補上 10 日與 20 日
- 順手修掉 `pending_5d` / `pending_10d` 的既有潛在 bug（欄位不存在時 `.sum()` 會炸）

`pytest test_forward_validation_refresh.py test_forward_validation_coverage.py` → **20 passed**。

### 3.2 覆蓋率守門（fail-closed）

`taiwan_stock_report/daily_prediction_refresh.py` 的 `auxiliary_health()` 原本只偵測
「整天沒有 chip 列」，所以 11% 覆蓋率的日子照樣放行。現在同時檢查**覆蓋率**：

```
chip 覆蓋率 = 當日 chip 列數 / 當日 daily_data2_full 檔數
低於 daily_prediction.min_source_coverage（預設 0.95）→ 該族特徵視為缺漏
→ 當日不發布任何 ADD（ADD 改寫為 HOLD），但仍完整記錄預測與收據
```

新增 `config/data_policy.json` 的 `daily_prediction.min_source_coverage`（0.95）。
收據新增 `coverage_gate` 欄位。

這是 2026-11-12 文件 §4 所說「可以在發佈前被擋掉」的失效模式：
**管線故障 → 閘門全開 → 在最糟的日子造成最大損失。** 現在那一步被擋住了。

### 3.3 三個特徵管線回填

| 管線 | 動作 | 結果 |
|---|---|---|
| chip | `data-downloader/stock_chip_features.py --from 2020-01-02 --to 2026-06-11 --source-table daily_data2_full`（逐年分塊），再補 live 缺列的 37 天 | 歷史區段改由 `daily_data2_full` 建置，覆蓋率 11.4% → 100% |
| us_anchor | `data-downloader/us_anchor_features.py --from 2026-06-22 --to 2026-09-30` | live 視窗 39/97 → **97/97** |
| news | `data-downloader/news_topic_features.py --trade-date <d> --write-db --items-path <archive>`（逐日，64/64 成功） | live 視窗 41/97 → **97/97** |

新聞那條的作法與另外兩條不同，值得記一筆：用每日管線的 RSS 路徑重跑歷史日期是**沒有用**的
（Google News RSS 只給近期文章，重跑五個月前只得到 0~3 檔／日，實測）；
改用本地原料庫 `stock_news`（2,434,706 篇，涵蓋到 2026-11-20）以 `--items-path`
餵給**同一支**建置器，才把密度拉回來。單日驗證：2026-06-25 由 1 檔 → **72 檔**
（當日窗內 1,565 篇）。

代價是密度不再與訓練窗一致（見 §2.3 末段）。

chip 回填後的年度分布（**2026-11-20 14:40 直接量測 `stock_chip_features_daily`**；
建置日誌印出的 rows 與表內實際列數在 2022／2023 有 9,956 列落差，故以量測值為準）：

| 年度 | 列數 | 交易日 | 檔數 |
|---|---|---|---|
| 2020 | 510,137 | 245 | 2,197 |
| 2021 | 514,349 | 244 | 2,201 |
| 2022 | 529,328 | 246 | 2,243 |
| 2023 | 532,921 | 239 | 2,316 |
| 2024 | 550,063 | 242 | 2,388 |
| 2025 | 564,985 | 243 | 2,406 |
| 2026（至 11-19） | 445,135 | 205 | 2,490 |
| **合計** | **3,646,918** | **1,664** | **2,626** |

其中 2020-01-02~2026-06-11（原本建自 `daily_data2` 的歷史區段）為 **3,448,468 列／1,563 個交易日**；
2026-06-12~11-19（live 區段，含補回的 37 天）為 198,450 列／101 個交易日。
另外補上 live 視窗缺列的 **37 天（2026-07-15~09-16）**：77,564 列／1,976 檔／40 日
（同一支建置器；那段時間每日管線沒有跑，所以整天沒有 chip 列）。

**回填後的覆蓋率**（分母是「當日 `daily_data2_full` 檔數」，不是視窗內累積 distinct 檔數）：

| 視窗 | 回填前 | 回填後 | 有 chip 列的日子 |
|---|---|---|---|
| train 2023-01-01~2026-03-31 | 11.4% | **98.9%** | 779 / 779 |
| validation 2026-04-01~06-17 | 11.3% | **99.0%** | 53 / 53 |
| playback 2026-06-18~11-12 | 混合 | **98.8%** | 92 / 92 |
| live 2026-06-18~11-19 | 100%（天數缺 37 天） | **98.9%** | 97 / 97 |

回填後整張表只剩 `data_source='daily_data2_full'`（單一來源）：
**3,646,918 列／1,664 個交易日／2,626 檔**（量測於 2026-11-20 14:40），
legacy 的 418,327 列／273 檔殘表已清空。

---

## 4. 重訓

### 4.1 執行規格

依 2026-11-12 文件 §5.2，唯一的改動是**訓練窗往前拉**（chip 覆蓋率拉平後才有訓練價值）、
playback 換成**全新**視窗、特徵集沿用生產版以便一對一比較：

```powershell
cd D:\CODEX\AI-Telegram
C:\Users\icemo\AppData\Local\Programs\Python\Python310\python.exe -X utf8 `
  taiwan_stock_report\train_daily2_swing_ai.py `
  --source-table daily_data2_full --universe core_stock `
  --feature-set all_layer12_layer13_institutional_playbook --model xgboost --require-gpu `
  --models-dir taiwan_stock_report\models_daily2_institutional_playbook_bull_2023_2026 `
  --outdir taiwan_stock_report\output\daily2_institutional_playbook_bull_2023_2026 `
  --train-start 2023-01-01 --train-end 2026-03-31 `
  --validation-start 2026-04-01 --validation-end 2026-06-17 `
  --playback-start 2026-06-18 --playback-end 2026-11-12 `
  --hold-days 20 --roundtrip-cost 0.0078 --big-loss-threshold -0.08 `
  --target-pct 0.08 --stop-pct -0.05 --top-k 20 --capital 1000000 --max-pos 20 `
  --min-win-prob 0.50 --max-loss-prob 0.98 `
  --portfolio-score p_win20_net_1pct --portfolio-exit-mode fixed
```

**環境注意**：xgboost 3.1.2（Python 3.10）有 CUDA 12.5 建的，可用 GPU；
xgboost 3.4.1（Python 3.14）**看不到 GPU**（`No visible GPU is found`，自動 fallback CPU）。
**重訓必須用 3.10。** `--require-gpu` 會在非 CUDA 環境直接失敗。

資料規模：載入 `daily_data2_full` **1,061,765 列／1,196 檔**（core_stock 宇宙），
特徵 358 個，feature_hash `292c949ce69ce00b…`（現任是 `3144e5afc5a45ae9…`）。

### 4.2 與現任模型對照

新模型 `daily2_xgboost_20261120135419`（訓練時已含補齊後的 chip／us_anchor／news 三族）：

| 項目 | 現任 `20260620182039` | 新 `20261120135419` |
|---|---|---|
| 訓練窗 | 2025-01-01~2025-12-31（chip 覆蓋 11.4%） | 2023-01-01~2026-03-31（chip 覆蓋 98.9%） |
| 驗證窗 | 2026-01-01~2026-03-31 | 2026-04-01~2026-06-17 |
| playback 窗 | 2026-04-01~2026-06-17（32 天） | 2026-06-18~2026-11-12（**71 天，全新**） |
| validation AUC `win20_net` | 0.5439 | **0.5616** |
| validation AUC `win20_net_1pct` | 0.5483 | 0.5455 |
| validation AUC `big_loss20` | 0.6769 | 0.6516 |
| playback AUC `win20_net` | 0.5214 | **0.5872** |
| playback AUC `win20_net_1pct` | 0.5324 | **0.6223** |
| playback AUC `big_loss20` | 0.6934 | **0.7663** |
| playback 交易數 | 40 | 80 |
| playback 淨勝率 | 72.5% | 33.75% |
| playback 每筆報酬 | +26.36% | **−7.77%** |
| playback 總報酬 | +58.87% | **−31.45%** |
| playback 最大回撤 | −2.82% | −39.43% |
| playback Sharpe | 8.60 | −1.76 |

（另有一輪 `daily2_xgboost_20261120133043`，跑在新聞補齊**之前**：validation AUC 0.5616 相同，
playback AUC `win20_net` 0.5600、`win20_net_1pct` 0.5980，組合 −44.17%。
補齊新聞後 playback 的 AUC 從 0.5600 升到 0.5872、組合虧損從 −44.17% 收斂到 −31.45%——
**新聞族的缺口確實會壓低模型的表現**，這是「缺口影響真實評估」的直接證據。）

### 4.3 怎麼讀這張表

**兩件事同時成立，而且互相牴觸。**

1. **管線修補確實改善了模型**：橫截面排序能力在兩個獨立視窗都上升
   （validation AUC 0.5439 → 0.5616；全新 71 天 playback 窗 AUC 0.5214 → 0.5872、
   `win20_net_1pct` 0.5324 → 0.6223、`big_loss20` 0.6934 → 0.7663）。
   chip 覆蓋率從 11.4% 拉到 98.9% 之後，模型終於學到了「有 chip 特徵時該怎麼預測」。
2. **但投資組合層是虧錢的**：80 筆、勝率 33.75%、總報酬 −31.45%、MDD −39.43%。
   現任模型那個 +58.87%／Sharpe 8.60 是 **32 天、40 筆**的產物——
   2026-11-12 文件早就寫過「n=40 的 ROI 是雜訊」，而且那個窗還被 06-20 的選拔用過。
   **換到 71 天的全新窗，數字就翻面了。**

換句話說：**修好的模型把「原本被小樣本掩盖的真實虧損」顯示出來了。**
這不是修補造成的退化，是修補讓真實情況第一次看得見。

而且這也回答了「閘門值不值得調」：即使模型的排序能力提升了，
`p_win20_net_1pct` 最高的 20 檔在 71 天全新窗裡仍然是虧的。
**閘門不是問題所在，策略疊層（選股 → 持倉 → 出場）才是。**

### 4.4 推廣門檻（RESP-2026-11-12-01 §5.3）對照

| 條件（RESP-2026-11-12-01 §5.3 原文） | 門檻 | 本次 | 結果 |
|---|---|---|---|
| 連續量測 | ≥ 60 個**有預測的交易日**，且覆蓋缺口已宣告 | 0（設計尚未凍結） | ☐ |
| purged walk-forward OOS | 贏過**同日宇宙**，且勝率 +≥3pp 或平均報酬 +≥0.5% | 未做 | ☐ |
| 贏過自己的 HOLD 基準 | 必須贏 | 未做 | ☐ |
| 橫截面訊號 | AUC ≥ 0.56 | validation 0.5616 | ☑ |
| 組合指標 | **交易數 ≥ 200**，且 ROI 需在 ≥2 個不重疊視窗皆為正 | 80 筆、ROI −31.45% | ☐ |
| 穩定性 | 閘門寬度日變動（`big_loss20` 地板）≤ 訓練期水準；退化日不發布 | 退化日已由 P4 守門擋下；地板日變動未量化 | 部分 |
| **新鮮前瞻驗證** | 設計凍結後累積 **≥ 40 個新交易日**的連續 ledger | 0 | ☐ |

**七項條件只過一項（穩定性只做到一半）。線上 bundle 不換。**

---

## 5. 殘餘風險與待 Walter 決定

1. **閘門門檻未改**（0.50 / 0.98）。理由見 §1.5；重啟條件是 RESP-2026-11-12-01 §5.3 的新鮮前瞻驗證。
2. **重訓未推廣**。線上仍是 `daily2_xgboost_20260620182039`；新 bundle 只是產物
   （`models_daily2_institutional_playbook_bull_2023_2026`）。
   `config/data_policy.json` 的 `production_model_version`／`production_model_dir` 未動，
   `model_registry` 也沒有自動登錄新模型（訓練腳本不寫 registry），**沒有發生誤推廣**。
   推廣需要另外授權，且門檻要換成 RESP-2026-11-12-01 §5.3 那套。
3. **策略疊層是下一個真正要解的問題**。模型的橫截面 AUC 提升了，但疊層仍然虧
   （80 筆／71 天／−31.45%）。修閘門或修模型都動不了這個；要動的是
   「用 p_win20_net_1pct 挑前 20 檔、持有 20 天」這個決策本身
   （§5.4 提過 `pred_net_return ≥ 0` 這個條件在 ADD 書內是反向的）。
4. **新聞家族的密度落差仍在**（§2.3）：live 視窗 ~58.7 檔/日 vs 訓練窗 16.3 檔/日。
   要完全對齊需要把訓練窗也用 `stock_news` 原料庫重建（924 天，約 7.7 小時），
   或把新聞整族排除在特徵集之外。兩者都需另外授權。
5. **AI-Telegram 的 `taiwan_stock_report/train_daily2_swing_ai.py` 上有他人未提交的工作**
   （約 17.8 KB、17 個 hunk），本回合只提交自己的 hunk，未碰他人內容。
   `taiwan_stock_report/daily_prediction_refresh.py` 原本**不在版控內**，
   本回合連同覆蓋率守門一起納入版控。
6. **`config/data_policy.json` 被 `.gitignore` 排除**（`config/`），所以
   `min_source_coverage` 這個新鍵只存在於本機，改動不會進版控。
7. **`tw-invest-suite` 已 push（HEAD = `origin/main` = `0a68e4381`）；
   只有 AI-Telegram 的 `9760439` 與 `0d6ead8` 依指示未 push。**
8. **AI-Telegram 的 `aws_amplify` 憑證遺失**（`rootkey.csv`）仍未處理，
   靜態站自 11/03 起無法發布。

---

## 6. 重現方式

```powershell
# 閘門重算（5d/10d/20d、同一列組、雙基準）
C:\Python314\python.exe <workspace>\scripts\_debug\_gate_recalibration.py
C:\Python314\python.exe <workspace>\scripts\_debug\_gate_recalibration_20d.py
C:\Python314\python.exe <workspace>\scripts\_debug\_verify_20d_result.py
C:\Python314\python.exe <workspace>\scripts\_debug\_gate_firing_pattern.py

# 特徵管線覆蓋率
C:\Python314\python.exe <workspace>\scripts\_debug\_feature_coverage_windows.py
C:\Python314\python.exe <workspace>\scripts\_debug\_aux_feature_coverage.py
C:\Python314\python.exe <workspace>\scripts\_debug\_us_anchor_coverage.py
C:\Python314\python.exe <workspace>\scripts\_debug\_news_source_coverage.py

# 回填
cd D:\CODEX\AI-Telegram
C:\Python314\python.exe data-downloader\stock_chip_features.py --from 2020-01-02 --to 2020-12-31 --source-table daily_data2_full
C:\Python314\python.exe data-downloader\us_anchor_features.py --from 2026-06-22 --to 2026-09-30
C:\Python314\python.exe data-downloader\news_topic_features.py --ensure-schema --write-db --source-table daily_data2_full --trade-date <date> --max-items-per-keyword 20
```

**證據來源**
- ledger：`D:\CODEX\AI-Telegram\output\forward_validation\forward_validation_log.csv`、`summary.json`
- 建置器：`D:\CODEX\AI-Telegram\data-downloader\stock_chip_features.py`、`us_anchor_features.py`、`news_topic_features.py`
- 特徵表：`stock_chip_features_daily`（`data_source` 欄位）、`us_anchor_features_daily`、`news_topic_features_daily`
- 閘門：`D:\CODEX\AI-Telegram\config\data_policy.json`、`taiwan_stock_report/model_predictions_daily.py::choose_action`
