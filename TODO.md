# TODO — tw-invest-suite

## Done ✅

- [x] **1,962 個 ticker × 17-tab HTML 全自動 render + publish**（每日 22:25）
- [x] **Cross-source data strategy**：DB + yfinance + FinMind，cache 優先 + 驗證
- [x] **GitHub Pages** (`walterLiu168.github.io/stock-report/analyze/`) + **groovelab.dev** 雙發佈
- [x] **Watchlist 24 檔精選**：4 價位 bucket × 3 long + 3 short
- [x] **8 種型態 × 240 日 walk-forward backtest** + dashboard
- [x] **18 大師解讀**（12 投資大師 + 4 分析師 + 2 管理專家）
- [x] **型態搜尋** at `groovelab.dev/analyze.html`
- [x] **台灣顏色慣例**（紅漲 / 綠跌）
- [x] **9 項 UI 改善**（法人 20 日、估值雙源、ROE TTM+季、觀察白話、顏色、Build-Thesis、Backtest 多策略、大師卡片、TODO）
- [x] **法人表格視覺重構**（彩色 cell + 內嵌 bar + 多日彙總）
- [x] **觀察重點卡片化**（5 維度 auto-fit 網格）
- [x] **render batch 拆 4 chunks 並行**（15 min 跑完 1962 隻，0 fail）
- [x] **公開 GitHub repo**（walterLiu168/tw-invest-suite，56 檔 26K 行）
- [x] **PWA installable**（manifest.json + sw.js）
- [x] **Landing page**（行銷式 index.html，含 stats/features/workflow）
- [x] **Docs 索引頁**（`public/docs/index.html`）
- [x] **LLM commentary 骨架**（任何 OpenAI-compatible endpoint）
- [x] **XGBoost 預測 + walk-forward backtest**（5 tickers 跑通）
- [x] **LSTM skeleton**（需 torch 才能跑）
- [x] **週末 auto-skip**（Sat/Sun 只 render+publish）
- [x] **disk-based TTL cache**（`~/.cache_manager/`）
- [x] **fail-fast 機制**（每 dataset 30 fail threshold）
- [x] **每日 status JSON**（`_debug/daily_status.json`）

## In Progress 🔄

- [x] **Phase 2: Web 產品站優化**（landing page + PWA manifest + service worker + docs 索引）
- [x] **Phase 2: LLM 每日 commentary**（`src/commentary/daily_commentary.py` — dry-run OK，需 API key 跑實際 LLM）
- [x] **Phase 3: ML 模型**（`src/ml/{features,xgb_predictor,lstm_predictor}.py` — XGBoost 跑通，LSTM skeleton）
- [ ] **Phase 4: 盤中即時 + Telegram 推播**
- [ ] LLM commentary 真的整合進 daily batch（需設 API key）
- [ ] LSTM 整合 torch 並跑實際訓練

## Backlog 📋

### Phase 2: Web 產品站
- [ ] 把 `public/` 整理成可部署結構（Vite / 純 HTML 都行）
- [ ] 加 `deploy.md`：GitHub Pages + groovelab.dev 設定
- [ ] 加 PWA / manifest.json（手機可裝）

### Phase 2: LLM 即時分析
- [ ] `src/commentary/daily_commentary.py` — 對 watchlist 24 檔做 commentary
- [ ] 整合 LLM（OpenAI / Anthropic / 本地）
- [ ] 輸出 Markdown 報告 + 訂閱
- [ ] 整合到 18 大師 tab

### Phase 3: ML 模型
- [ ] `src/ml/lstm_predictor.py` — LSTM 預測
- [ ] `src/ml/xgboost_features.py` — XGBoost 多因子
- [ ] walk-forward 驗證 + 信心區間
- [ ] 整合回測 + live

### Phase 4: 即時性
- [ ] 盤中即時報價（yfinance intraday 5min）
- [ ] Telegram 推播（突破/法人大買/新聞觸發）
- [ ] 預警 dashboard

### Phase 5: 多市場
- [ ] 美股整合（yfinance US tickers）
- [ ] 港股 / 日股
- [ ] 跨市場比較

---

## Bug / 已知問題

- **FinMind news endpoint** 最近回 0 筆（可能 endpoint 改），目前用 DB `stock_news` fallback
- **ROE 季報**某些 ticker 出現極端值（>500%），原因是庫藏股未從股東權益扣除
- **8039 valuation** yfinance 114.98 vs FinMind 86.51 = 32.9% 差異（yfinance TTM vs FinMind 單季）
- **Cloudflared outbound** 被擋 → 改用 GitHub Pages + groovelab.dev file serve

---

## 改善時記得做的事

1. 加 entry 到 `docs/decision-log.md`
2. 更新 `docs/data-schema.md` 如果改欄位
3. 更新 `README.md` 如果加新功能
4. 跑 `render_only.py --no-yfinance --no-news` 確認 batch 仍正常
5. Push 到 GitHub Pages 確認 live site
