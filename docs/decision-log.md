# Decision Log — 為何這樣選

> 重要的架構決策，避免未來重新發明輪子。

---

## D001: MySQL-first 資料策略

**日期**：2026-08-12

**Context**:
原設計是「FinMind + FinLab + yfinance」三源平行抓。

**Decision**:
永遠先讀 MySQL `tw_elec.daily_data2_full`，缺資料才打 API。

**Why**:
1. DB 已有 20 年+ 歷史 OHLCV + 法人 + 融資融券
2. FinMind sponsor tier 6,000/hr 但 anti-abuse 觸發會 ban IP
3. FinLab 只到 2018-Q3，幾乎是死資料
4. DB 查詢 1 隻 ticker < 50ms，API 至少 1s

**Trade-off**:
- DB 需要維護（每日 ETL）
- 失去 FinMind 即時性（但收盤後就同步了）

---

## D002: yfinance 取代 FinLab

**日期**：2026-08-13

**Context**:
FinLab 是付費服務，但只到 2018-Q3 之後就沒資料了。

**Decision**:
完全不用 FinLab，改用 yfinance 抓估值（PE/PB/dividend_yield/ROE/marketCap）。

**Why**:
1. yfinance 免費、無 quota limit
2. 資料比 FinLab 新（最新一季）
3. yfinance 已被 sponsor 驗證 OK

**Trade-off**:
- yfinance 偶爾不穩（被 Yahoo 限流）
- 解法：fail-fast 30 隻失敗就停

---

## D003: FinMind rate limit 1.05s/call

**日期**：2026-08-13

**Context**:
FinMind sponsor 6,000/hr 看起來很夠，但實際觸發 anti-abuse 機制後會 ban IP。

**Decision**:
每個 FinMind call 間 sleep 1.05s = 57/min = 3,420/hr，遠低於 6,000 但安全。

**Why**:
- 1,962 隻全跑 4 datasets = 7,848 calls
- 7,848 / 57 = 138 分鐘 = 2.3 小時
- 觀察 ban 從不觸發

**Trade-off**:
- 慢（2.3 hr/全跑）
- 但穩定，不會被 ban

---

## D004: disk-based TTL cache

**日期**：2026-08-13

**Context**:
原本用記憶體 dict 做 cache，重啟就掉。

**Decision**:
改用 disk-based cache（`~/.cache_manager/<dataset>/<TICKER>.json`）。

**Why**:
1. 重啟後資料還在
2. 1,962 隻 ticker × 4 datasets = 7,848 檔案，disk 還是吃得下
3. JSON 格式可手動檢查
4. TTL per dataset（PE 1d、ROE 7-30d 等）

**Trade-off**:
- Disk I/O 比 memory 慢
- 觀察 7,848 讀寫約 3 分鐘，可接受

---

## D005: 週末不抓資料

**日期**：2026-08-14

**Context**:
週六日 FinMind 沒新資料，yfinance 也不動，純粹浪費 quota。

**Decision**:
`run_daily.ps1` 自動偵測週末，僅做 render + publish。

**Why**:
- 省 2.3 hr 跑 batch 的時間
- DB 仍用 last trading day 的資料（週六渲染顯示週五收盤）

**Trade-off**:
- 週末跑了也沒新東西
- `-Force` flag 可強制跑

---

## D006: cache-only mode 給 batch render

**日期**：2026-08-14

**Context**:
重新 render 1,962 隻時，如果 cache 還新鮮，不該打 API。

**Decision**:
`render_only.py --no-yfinance --no-news` 只讀 cache，不打 API。

**Why**:
- 重新 render 從 50 分鐘降到 ~50 分鐘（render 是 CPU bound 不是 I/O）
- 不打 API = 不會觸發 rate limit

**Trade-off**:
- 看不到最新資料（但週末/平日下午重 render 不需要新資料）

---

## D007: 17-tab UI（取代單頁滾動）

**日期**：2026-08-15

**Context**:
原本單頁滾動 1,962 個章節太長。

**Decision**:
改成 17 tabs + Chart.js。

**Why**:
1. 找資訊快速（直接點 tab）
2. 技術/法人 tab 內嵌 Chart.js
3. URL hash 記憶 tab

**Trade-off**:
- 17 個 tab 太多 → 分兩排（PRIMARY 11 個 + SECONDARY 6 個）
- 技術 tab 加 2 個 chart（價格+MA、RSI）

---

## D008: 法人表格視覺重構

**日期**：2026-08-16

**Context**:
原本純 markdown 表格，0 值混雜，沒視覺化。

**Decision**:
改成 HTML 卡片式 + 彩色 cell + 內嵌 bar + 多日彙總。

**Why**:
- 一眼看出「哪些日子大買/大賣」
- 多日彙總（5/10/20）放在最上面當 summary
- 合計欄 amber 高亮

**Trade-off**:
- 程式碼多 ~50 行
- HTML 變長

---

## D009: 觀察重點卡片化

**日期**：2026-08-16

**Context**:
原本純 bullet list，閱讀吃力。

**Decision**:
5 個維度（動能/法人/估值/品質/營收）各一張卡，auto-fit 網格。

**Why**:
- 一眼看到 5 個維度狀態
- 顏色編碼（紅/綠/灰）對應情緒
- 每張卡內含「白話說明」

**Trade-off**:
- 沒有資料的維度不出現卡（不會顯示空卡）
- 行動裝置會自動換行

---

## D010: 台灣顏色慣例

**日期**：2026-08-15

**Context**:
預設 CSS 變數是美股慣例（綠漲紅跌）。

**Decision**:
swap CSS `:root` 的 `--red`/`--green` 值：
```css
:root {
  --red: #ec7063;    /* 台灣：紅 = 上漲 */
  --green: #58d68d;  /* 台灣：綠 = 下跌 */
}
```

**Why**:
- 不用改 selector（所有用 var(--red) 的地方自動正確）
- 維護成本低

**Trade-off**:
- 變數名 `red` 對應正值，語意反直覺
- 註解要寫清楚「台灣慣例」

---

## D011: 殖利率雙格式檢測

**日期**：2026-08-15

**Context**:
yfinance 殖利率有兩種格式：> 0.5 是百分比（1.5 = 1.5%），< 0.5 是小數（0.015 = 1.5%）。

**Decision**:
```python
dy_pct = dy if dy > 0.5 else dy * 100
```

**Why**:
- yfinance 不一致
- 0.5 閾值實測有效

**Trade-off**:
- 剛好 0.5 視為百分比（罕見）

---

## D012: 法人表格視覺重構

**日期**：2026-08-16

**Context**:
原本純 markdown 表格，0 值混雜，沒視覺化。

**Decision**:
改成 HTML 卡片式 + 彩色 cell + 內嵌 bar + 多日彙總。

**Why**:
- 一眼看出「哪些日子大買/大賣」
- 多日彙總（5/10/20）放在最上面當 summary
- 合計欄 amber 高亮
- 大買/大賣日（>60% 最大絕對值）整列背景 highlight
- 0 cell 顯示 "0"（不再是空白），看起來不雜亂

**Trade-off**:
- 程式碼多 ~50 行
- HTML 變長

---

## D013: 觀察重點卡片化

**日期**：2026-08-16

**Context**:
原本純 bullet list，閱讀吃力。

**Decision**:
5 個維度（動能/法人/估值/品質/營收）各一張卡，auto-fit 網格。

**Why**:
- 一眼看到 5 個維度狀態
- 顏色編碼（紅/綠/灰）對應情緒
- 每張卡內含「白話說明」

**Trade-off**:
- 沒有資料的維度不出現卡（不會顯示空卡）
- 行動裝置會自動換行

---

## D014: render batch 拆 chunks

**日期**：2026-08-16

**Context**:
1,962 隻全跑 ~52 分鐘，超過 bash 工具的 30 分鐘上限。

**Decision**:
切成 4 個 chunk（每 ~491 隻），每個 chunk 跑 ~15 分鐘。並行 4 個 background task。

**Why**:
- 每 chunk 都能在 30 min 內完成
- 4 個並行 = 總時間仍 ~15 min（不是 60 min）
- 0 fail / 1962 done

**Trade-off**:
- 4 個 python process 同時跑，DB 連線數增加
- 用 `render_chunk.py` 取代 `render_only.py` 的全跑模式

---

## D015: Pattern 顏色翻成台灣慣例

**日期**：2026-08-16

**Context**:
之前 pattern 顏色用美股慣例（up=綠、down=紅），但 user 明確要求台灣慣例（up=紅、down=綠）。

**Decision**:
全部翻過來：
- `pattern_classifier.py` PATTERNS dict：3 個 uptrend 改 red、3 個 downtrend 改 green
- `build_patterns_html.py` CSS：.pos 用 var(--red)、.neg 用 var(--green)、.win-high = var(--red)、.verdict.win = 紅底、.verdict.lose = 綠底
- `analyze.html` chip 結果表：.pos = var(--red)、.neg = var(--green)
- `render_ticker_html.py` 舊 fallback：.up/.down, .pos/.neg, .zen-bullish/.zen-bearish, .tag-green/.tag-red 全部翻

**Why**:
- 台股投資人看「紅=漲、綠=跌」
- 之後別人不會誤以為我們搞錯

**Trade-off**:
- 類別名 `tag-green` / `tag-red` 仍保留（語意是「好/壞」），但底色是反的 — 加註解說明
- 之後新增 pattern 時要記得：up→red、down→green

**驗證**:
- `pattern_classifier.py` 開頭加註解提醒
- Build-Thesis 也是用同樣邏輯（🟢 多頭 = 紅、🔴 空頭 = 綠）— 在 thesis 訊息也用
- 截圖確認 patterns.html 上 8039 當日 +9.22% 是紅、long_drawdown 表 -73.57% 是綠

---

## D016: 先修量測再談模型；重訓 NO-GO

**日期**：2026-11-11

**Context**:
2026-11-11 被問「should we train again?」。production bundle `daily2_xgboost_20260620182039`
訓練於 2026-06-20，train window 只有 2025 一年。但重新量測時發現 forward-validation ledger
本身有四個靜默缺陷（只追 ADD、每天只寫最新預測日、品質退化列被靜默丟棄、`ledger_origin` 全無資訊），
所以「5 個月的 OOS 證據」其實只有 23～26 個訊號日。在這種基礎上討論要不要重訓是沒有意義的。

**Decision**:
1. 先做 Phase 0（量測修復），再做 Phase 1（診斷），**重訓最後考慮且目前 NO-GO**。
2. ledger 改為追蹤全部三種動作、補回被跳過的預測日、品質退化列記錄並標記而非丟棄、
   `ledger_origin` 依真實發布延遲推導、`summary.json` 加 `by_action` 與 `coverage`。
3. 沒有預測列的 38 個交易日（2026-07-08~09-24）**不重建**，只宣告為缺口。
4. 診斷結論：模型接近 beta、沒有穩定 edge；**價值被「發佈廣度」破壞**——
   整份清單輸宇宙 1.22pp，縮到 50～100 檔就贏 0.7～1.4pp；閘門開最大時市場廣度最低。
5. 因此下一步優先順序是：**縮減發佈廣度 → 退化日保護 → 閘門市場相對 → 移除反向的
   `pred_net_return >= 0` 條件**，全部排在重訓之前。

**Why**:
- 量測壞掉時，任何模型結論都只是在雜訊上做決策；ledger 從 8,160 列修到 36,522 列、
  26 天修到 35 天之後，GO／NO-GO 的四項條件才有辦法真的檢查
- 四項 GO 條件全 FAIL（連續量測 ≥60 天 FAIL、勝率贏宇宙 ≥+3pp FAIL、
  報酬贏宇宙 ≥+0.5% FAIL、贏過自己的 HOLD 基準 FAIL）→ 現在重訓是把雜訊當真相
- split-half 驗證顯示沒有任何替代排序規則穩健地贏過現行閘門 → 該修的是廣度與閘門，不是排序
- `breadth_above_sma54` 對「模型有沒有 edge」的相關性 +0.647，是已知最強的單一因子 →
  閘門市場相對化比換模型更有杠杆

**Trade-off**:
- 縮減發佈廣度、改閘門屬於**線上策略變更**，必須 Walter 明確授權，不能自行套用
- 38 天的空白永遠補不回來 → 「模型在 7～9 月表現如何」目前無法回答
- `pred_net_return` 反向的成因尚未定位（特徵漂移？標籤定義？市場狀態特徵主導？），
  目前只證明「在這段期間、在 ADD 書內反向」

**驗證**:
- 20 個測試通過；向量化 outcome 更新 vs 原本逐列實作 cell-by-cell 0 差異（5,207 列 × 8 欄）
- 重建驗收：原有 8,160 列 0 遺失、0 訊號或已完成報酬被改寫；連續兩次回填 byte-identical
- 效能：日常 7.5 秒、全量回填 10.3 秒（原本 143 秒，超過 cron 的 120 秒預算 → 已修）
- 詳見 `docs/RESP-2026-11-11-01-model-health-and-retrain-verdict.md`

---

## D017: 重訓前必須先把特徵覆蓋率拉平（train/serve skew）

**日期**：2026-11-12

**Context**:
D016 的 NO-GO 建立在「證據量不足 + 四項 GO 條件全 FAIL」上，隔天解剖凍結 bundle 與各來源表後，
找到真正的根因：**chip 特徵家族的訓練／服務分布錯配**。

`stock_chip_features_daily` 的 `data_source` 欄位顯示：
2020-01-02～2026-06-11 整段歷史都建自 `daily_data2`（每日只有 271 檔，佔宇宙 11.4%），
2026-06-12 起改用 `daily_data2_full`（每日 ~2,380 檔，99.1%），**歷史從未回填**。
模型的 train 與 validation 視窗覆蓋率是 11.3～11.4%，live 視窗是 59.3%（逐日可為 99% 或 0%），
而模型上線日 2026-06-18 是覆蓋率暴增後的第 6 天。

**Decision**:
1. **重訓不是第一步**，且必須是「條件式 GO」：先把特徵管線修好並回填，再重訓。
2. 必要前置 P1～P4：
   - P1 修 chip 特徵建置器的來源表（整段歷史用 `daily_data2_full`）
   - P2 回填 2020-01～2026-06-11 的 chip 特徵，覆蓋率 ≥95%
   - P3 補 `us_anchor_features_daily` 2026-06～09 缺的 58 個交易日
   - P4 覆蓋率守門：推論當日覆蓋率偏離訓練基準就不發布 ADD 訊號（fail-closed）
3. 重訓推廣門檻把「40 筆交易的 ROI」換掉：交易數 ≥200、橫截面 AUC ≥0.56、
   市場相對 purged OOS、且需設計凍結後 ≥40 個新交易日的前瞻驗證。
4. 閘門改版（縮減廣度、退化日保護、市場相對化、移除反向的 `pred_net_return ≥ 0`）
   與權重無關，可以並行，而且回報更快。
5. 同時承認：**模型本質是市場計時器**——三個 `p_win` head 的 Top-1 都是全市場的
   `breadth_above_sma54`，市場狀態特徵佔各 head gain 的 19.8～29.6%，
   七個 head 特徵重疊度 0.78～0.85。重訓能帶來穩定性，帶不來橫截面選股能力。

**Why**:
- chip 家族 30+ 欄位的輸入分布在訓練與服務之間完全不同；XGBoost 對 NaN 有原生處理，
  所以「某族特徵從 11% 覆蓋變 99%」不是漸變而是全帳輸出分布整體位移。
  實測對應：2026-07-31 chip 整表無列 → ADD 佔比 86.0%；2026-10-28／11-02 缺 41 個新聞特徵
  → 83.1%／95.3%；34 個乾淨日平均只有 24.3%。**管線故障會變成極度看多的訊號書。**
- 訓練與驗證覆蓋率一致，所以只訓練不會暴露這個問題；模型是第一次在 99% 覆蓋的世界上運行。
- `chip_cov ↔ ADD佔比` Spearman −0.626；`品質收據缺特徵數 ↔ ADD佔比` Pearson +0.499。
- 不先修管線就重訓，只會產出同一個錯配的複製品。

**Trade-off**:
- P1～P3 是資料管線工程，需要時間與對上游資料保留期限的確認
- 新的 bundle 在拿到 ≥40 個新鮮前瞻交易日之前**不能推廣**，所以這是一條有時限的路線
- 「模型是市場計時器」意味著若產品定位是每日選股清單，需要重新思考模型在產品中的角色

**驗證**:
- 覆蓋率與轉換點：`scripts/_debug/_coverage_transition.py`
- 覆蓋率 vs 閘門寬度：`scripts/_debug/_coverage_vs_gate.py`
- bundle 各 head 的 gain 結構：`scripts/_debug/_bundle_anatomy.py`
- 詳見 `docs/RESP-2026-11-12-01-retrain-root-cause-and-terms.md`

---

## D018: 選股清單歷史回看（watchlist history）

**日期**：2026-11-16

**Context**:
每日精選 24 檔每晚整份換掉，任何網頁都只能回答「現在榜上有哪些」，
永遠回答不了「這檔上次進榜是什麼時候、理由是什麼、之後賺賠如何」。
既有資料其實都在：`market_screen_picks` 保留每次入選的 score／rationale／bucket／
close_at_pick，`daily_data2_full` 有正規收盤價，只是沒有被組織成可查詢的歷史。

**Decision**:
1. 新增 `src/watchlist_history.py`：讀 `market_screen_runs` + `market_screen_picks` +
   `daily_data2_full` → 產生單一緊湊文件 `public/data/watchlist-history.json`
   （每檔含首次／最後進榜、上榜次數、每次入選明細、首次進榜後的每日報酬路徑）。
2. 新增靜態頁 `public/watchlist-history.html`：總覽表（可搜尋／篩選／排序）+
   點列下鑽該檔時間軸與報酬圖 + `?ticker=` 深層連結；顏色沿用台股慣例（紅漲綠跌）。
3. nightly stage 7（`src/all_reports.py`）每次重建歷史文件，
   `scripts/pipeline_state.py` 的認證白名單同步加入兩個新產物，
   `scripts/render_full_watchlist.py` 每張 pick 卡加「📜 歷史 →」連結。
4. 理由文字在建置時解析成結構化欄位（原本是 `**欄位**：值` 的整段文字），
   文件由 943 KB 降到 909 KB，頁面也能一行一個事實呈現。
5. **不修** `market_screen_picks` 的同日重複入選（見下），只去重並揭露。

**Why**:
- 歷史是「清單」這種每日替換型產物唯一能被稽核的證據；沒有它，
  任何績效宣稱都只能用當日截圖
- `market_screen_picks` 沒有 `(run_id, ticker)` 唯一鍵，實測 17 天、20 組同一檔在同一次
  篩選被寫入兩次；那些天的 24 筆其實只有 23 個不重複標的，而
  `publish_manifest.fetch_picks()` 只檢查列數所以查不出來。
  本功能以 `(run_id, ticker)` 去重（保留 id 最小者）並在頁面與 JSON 揭露天數，
  但**沒有**加唯一鍵、沒有回寫既有列、沒有改 market screen——
  那要先查清楚為什麼會重複入選，屬於另一個需要單獨授權的修正。
- 認證契約（`validate_all_reports`）對產物集合是嚴格相等比對，
  新增檔案若不同步白名單會讓 nightly 認證失敗，因此改動必須成對進行

**Trade-off**:
- 歷史文件每晚重建，main 會有滾動 diff（與既有的 `chips-history-index.json` 同一模式）
- JSON 909 KB（緊湊 JSON，GH Pages 會 gzip，實際傳輸約 180 KB）
- 只涵蓋 `market_screen_runs` 保留的期間（目前 2026-08-12 起 50 次）；更早的清單無 DB 紀錄

**驗證**:
- `tests/test_watchlist_history.py`：6 個測試（理由解析、同日去重、認證身分、
  緊湊輸出、產物白名單、頁面契約、台股顏色）
- 全套 `pytest tests/`：235 passed / 1 failed；唯一失敗
  `test_db_config.py::test_missing_password_fails_closed` 為**既有失敗**
  （`scripts/db_client.py` 有他人未提交的 registry fallback 改動；
  以 HEAD 版本隔離驗證為 3 passed），與本功能無關
- 瀏覽器實測（487×767 手機視窗）：總覽表、下鑽抽屜、報酬圖、理由逐行、
  深層連結、去重後次數皆正確
- 詳見 `docs/WATCHLIST_HISTORY_FEATURE.md`

---

## D019: 每日精選的名額不等於檔數——誠實揭露，不改選股邏輯

**日期**：2026-11-17

**Context**:
歷史回看頁（D018）需要按 ticker 聚合每日精選，發現 `market_screen_picks` 裡有同一檔
在同一次篩選佔兩個名額。追查結果：`market_screen.py:348-353` 的 long 與 short 是
**兩套彼此獨立的排序**，都在同一個 bucket 候選池上跑，short 名單沒有排除 long 名單。
`persist_atomic()` 對 `market_screen_runs` 以 `run_date` UPSERT 且插入前先 DELETE 該 run 的
picks，所以不是重複寫入；`daily_data2_full` 也沒有任何重複 `(Ticker, Date)` 列。
認證層只驗每個 `(bucket, horizon)` 剛好 3 檔、總數 24 檔，**從不驗 24 個名額是否為 24 個
不重複標的** → 帶著重複一路通過認證並發佈。

50 次篩選中 **18 次**有重複；2026-11-16 線上清單的 **3443 同時出現在 long 與 short 兩張卡**，
頁面標題卻寫「24 檔」。呈現層的平均報酬與勝率走 `all_picks`（24 列）→ 重複檔被算兩次。

**Decision**:
1. 先修**呈現層**、不動選股邏輯：新增 `summarize_picks()` 以不重複標的計算平均與勝率；
   摘要卡、頁面標題、頁尾在有重複時改寫成「24 名額／23 檔」；頁面加一列黃色揭露說明
   列出重複檔名與重疊名額數。
2. **不**改 `market_screen.py` 的 long／short 選股邏輯、**不**加 DB 唯一鍵、
   **不**回寫既有列——讓 short 名單排除 long 名單會改變當天選到誰，屬策略變更，
   依 D018 的治理邊界需 Walter 明確批准。
3. 統計扭曲其實很小（平均報酬 ≤0.006、勝率 ≤+2.2pp）；真正要修的是**宣稱不實**與重複呈現。

**Why**:
- 「24 檔」是對外承諾（頁面標題、`AGENTS.md`、data-schema 都寫 24 檔），
  36% 的日子實際只有 23 檔，屬事實錯誤
- 兩個獨立策略（長期持有 vs 短中期交易）同時看中一檔，本身不是錯；
  錯的是把「名額數」當成「檔數」宣稱，並讓它雙重計入績效統計
- 改選股邏輯的成本（需要一輪 nightly 驗證名額分布與認證穩定），
  相對於只修呈現層的收益不成比例 → 先修呈現層、觀察一週再評估

**Trade-off**:
- 選項 A（現況）：同一張卡仍會出現兩次，但帶不同長期／短中期角色標籤，資訊其實完整
- 選項 B（待批准）：short 名單排除 long 名單 → 24 個不重複標的，但當天 short 首選會換人
- `market_screen_picks` 沒有 `(run_id, ticker)` 唯一鍵這件事仍存在，
  目前靠 DELETE-then-INSERT 的冪等性擋住，不是靠約束

**驗證**:
- `tests/test_watchlist_overlap.py`：4 個測試（重複只計一次、無重複、缺報酬、頁面不得硬寫 24 檔）
- 線上實測 2026-11-16：24 張卡、3443 出現兩次（long + short），重複名額揭露列正確
- 詳見 `docs/RESP-2026-11-17-01-long-short-slot-overlap.md`

