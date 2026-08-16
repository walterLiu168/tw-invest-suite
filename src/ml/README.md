# ML — 機器學習預測

> 對 1,962 檔台股做方向預測，含 walk-forward 回測。

## 已實作

### 1. `features.py` — 特徵工程
從 `daily_data2_full` 抓 500 天 OHLCV + 法人 + 融資融券 + 技術指標，
產出 24 個特徵：

| 類別 | 特徵 |
|---|---|
| Returns | ret_1d, ret_3d, ret_5d, ret_10d, ret_20d |
| MA 偏離 | ma13_dev, ma27_dev, ma54_dev |
| 量能 | vol_ratio_20, is_gap |
| 法人 | foreign_1d_k, foreign_3d_k, foreign_5d_k, foreign_20d_k, foreign_20d_pct, foreign_buy_ratio, three_5d_k, ForeignRatio |
| 融資券 | margin_chg_1d, margin_chg_5d, short_chg_5d, margin_short_ratio |
| 波動 | atr_pct, vol_20d |

**注意**：目前不含 `industry_type` / `valuation` / `monthly_revenue`，擴充時加進 `build_features()`。

### 2. `xgb_predictor.py` — XGBoost 方向分類
- Binary classification: 5-day forward direction (up/down)
- Walk-forward validation：每 252 天訓練，60 天測試，step 30 天
- 產出 per-ticker accuracy / precision / recall / F1 / AUC
- 產出 feature importance（跨 ticker 平均）

**跑**：
```powershell
# 5 檔測試
python -m xgb_predictor --tickers 2330 2317 2454 0050 8039 --feat-imp

# Top 100 by volume
python -m xgb_predictor --top 100 --out outputs/ml/xgb_top100.json
```

### 3. `lstm_predictor.py` — LSTM 序列模型（skeleton）
- Input: 60 天 × 24 features
- LSTM(64, 2 layers) → Linear(1) → sigmoid
- 目標: 5-day forward direction
- Walk-forward 80/20 split

**需要 torch**（沒預裝）：
```powershell
# GPU (RTX 3060 Ti 8GB)
pip install torch --index-url https://download.pytorch.org/whl/cu121

# CPU only
pip install torch
```

**跑**：
```powershell
python -m lstm_predictor --tickers 2330 2317 2454 --device cuda
```

## 為什麼預測準確率 ~50%

這是正常的。股市 5-day direction 基本上 random walk，技術指標只有微弱訊號。
要提升需要：
1. **更好的特徵** — 加入營收 YoY、殖利率、產業、相對大盤強度
2. **更長歷史** — 1,962 檔全跑、20 年資料
3. **不同目標** — 不是「漲/跌」而是「漲 > X% / 跌 > Y%」
4. **集成模型** — XGBoost + LSTM + 規則投票

## 整合到 daily batch

`run_daily.ps1` 加：
```powershell
# Stage 7: ML prediction (after publish, before next day)
& python "$PSScriptRoot\src\ml\xgb_predictor.py" --top 100 --out "outputs\ml\daily_$(Get-Date -Format 'yyyy-MM-dd').json"
```

## 已知限制

- XGBoost 用 `tree_method='hist'`，CPU only（GPU 需要 `tree_method='gpu_hist'` + CUDA）
- LSTM skeleton 還沒做 walk-forward（只 80/20 split）
- 沒做 feature selection（24 個特徵可能有冗餘）
- 沒做 cross-validation（walk-forward 就夠了，但 grid search 沒做）

## 下一步

- [ ] 加入估值 / 月營收特徵
- [ ] 多 ticker 一起訓練（XGBoost 不需要，但 LSTM 要 batch）
- [ ] LSTM walk-forward（每 30 天 retrain）
- [ ] 模型 ensemble（XGB + LSTM + 規則）
- [ ] 預測結果輸出到 `market_screen_picks`（自動加進 watchlist）
- [ ] 每週自動 retrain
