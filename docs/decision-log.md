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
2. **2026-11-17 經 Walter 明確批准後，再修選股層**：新增 `pick_horizons()`，
   short 名單跳過 long 已取走的名稱並改取下一名；bucket 不夠 6 個不重複名稱時，
   short 由 long 分數最低的名額依序讓位以保住 24 個名額，並記錄 `reused` 供稽核。
   **每日 24 個名額必定是 24 個不重複標的。**
3. **不**加 DB 唯一鍵、**不**回寫既有資料列——互斥由選股邏輯保證，
   持久層仍靠 DELETE-then-INSERT 的冪等性。
4. 統計扭曲其實很小（平均報酬 ≤0.006、勝率 ≤+2.2pp）；真正要修的是**宣稱不實**與重複呈現。
5. 呈現層的誠實揭露**保留**為第二道防線：認證層目前仍只驗名額分布、不驗標的是否重複。

**Why**:
- 「24 檔」是對外承諾（頁面標題、`AGENTS.md`、data-schema 都寫 24 檔），
  36% 的日子實際只有 23 檔，屬事實錯誤
- 兩個獨立策略（長期持有 vs 短中期交易）同時看中一檔，本身不是錯；
  錯的是把「名額數」當成「檔數」宣稱，並讓它雙重計入績效統計
- 互斥會讓 short 名額往下移（某檔原本同時是 long 與 short 首選時，
  short 那一格改由該 bucket 的 short 次名接手）→ 屬策略變更，必須明確批准
- 兩道防線都要留：選股層保證不重複，呈現層保證就算未來有人改回去也不會說錯話

**Trade-off**:
- 選項 B 生效後，short 名單的成分會與過去不同 → 績效比較需以 2026-11-17 起的新篩選為基準
- `market_screen_picks` 沒有 `(run_id, ticker)` 唯一鍵這件事仍存在，
  目前靠 DELETE-then-INSERT 的冪等性擋住，不是靠約束

**驗證**:
- `tests/test_market_screen_exclusive.py`：4 個測試（互斥、short 分數、bucket 名額不足時讓位、每 bucket 3+3）
- `tests/test_watchlist_overlap.py`：4 個測試（重複只計一次、無重複、缺報酬、頁面不得硬寫 24 檔）
- 線上實測 2026-11-16：24 張卡、3443 出現兩次（long + short），重複名額揭露列正確
- `scripts/market_screen.py` 屬 SHA 契約內的 cron 檔，runtime 副本已同步
- 詳見 `docs/RESP-2026-11-17-01-long-short-slot-overlap.md`

---

## D020: 衍生欄位補算不與資料集階段綁死；精選歷史進首頁 nav

**日期**：2026-11-17

**Context**:
11/17 的 18:20 篩選通過了 D019 的互斥契約（24 名額／24 個不重複標的），但產出的
24 檔 `change_pct` 全是 0、short 分數只剩 5 種值。追查後確認 `daily_data2_full` 的
`change_pct` 在 11/17 全 NULL、`sma_*`／`atr_14`／`rsi_14`／`is_gap` 全是欄位 DEFAULT 0：
FinMind canonical 階段在 18:00–18:07 執行時，margin 資料集回報
`Canonical source is empty`、shareholding／shares 缺漏 → 資料集階段丟例外 →
`recompute_derived` 從未執行 → 最新交易日就留在佔位值上。而 19:00 的 price 階段
`affected_rows=0`（狀態已標記完成）→ `touched_dates` 維持 False → 補算同樣被跳過。
short 分數的 trend／rsi／gap 三個組成因此全數失效，分數上限從 3.5 塌到 1.4，
12 檔 short 選股有 9 檔會選錯。

同一晚 21:30 的 nightly（`run_daily.ps1`）會用 `--refresh-existing` 重跑篩選並覆蓋同一筆
run，但補算窗口只剩 22:25 之前。

**Decision**:
1. **立刻補算 11/17**（Walter 授權選項 A）：以同一張表的既有 OHLCV 重算 7 個衍生欄位，
   先在 11/16 的真值上做唯讀驗算（差異僅為欄位小數位進位），再用上游
   `recompute_derived()` 對 5 檔抽樣交叉驗證（逐欄 0 差異）。不呼叫 FinMind API、
   不改 schema、不動其他欄位。
2. **補結構性漏洞**（Walter 授權選項 A；當時 local-only 未 push，現已在遠端 `2a3808aa3`）：在
   `AI-Telegram/strategy_lab/finmind_batch_update.py` 新增 `tickers_missing_derived()`，
   資料集階段改為 `try/except` 記錯但不中斷，補算條件由 `touched_dates and "price" in phase_names`
   改為只看 `"price" in phase_names`（`touched_tickers` 為空時用佔位值偵測兜底），
   補算與 inst-nets／cache 失效跑完後**再 re-raise**，維持 fail-closed。
   偵測條件用 `change_pct IS NULL OR sma_13 = 0`——`rsi_14 = 0` 會誤判連 14 根跌停的標的，已排除。
3. **精選歷史進首頁 nav**：既有 `public/watchlist-history.html` 從未被任何頁面連到，
   首頁 nav 也沒有它。補上第 9 個跨頁 tab（靜態頁 3 個 + nightly 重新生成的 4 個產生器），
   並在該頁新增「📅 每日 24 檔」視圖（由既有 JSON 前端推導，不改已認證的 artifact）。

**Why**:
- 量測先於模型、量測先於修復：同一個「看起來正常」的 run（24 名額、認證通過、log 乾淨）
  底下藏著資料品質塌陷，只有逐欄 NULL 稽核才看得出來
- 補算必須與「資料集有沒有寫到東西」脫鉤。`affected_rows=0` 在正常情況代表沒事，
  在狀態已標記完成的情況下卻代表「永遠不會再補」——這正是 11/17 的成因
- 不能為了讓流程「看起來成功」而吞掉失敗：re-raise 保留原本的失敗 exit code
- nav 分頁要改**產生器**而不是輸出檔：`chips.html`／`sectors.html`／`concepts.html`／
  `chips-advanced.html` 每晚重新生成，只改輸出檔隔夜就被蓋掉
- 「每日 24 檔」不另建資料來源：既有 `watchlist-history.json` 已含每日入選明細，
  前端推導可避免改動已認證 artifact 與 nightly 的資料契約

**Trade-off**:
- 修補只在 local，未 push；且該檔另有他人未提交的改動（`official_twse_json`／
  `capital_suspensions`／`resolve_price_universe`），**不可整檔 commit**，必須逐 hunk 取用
  （**2026-11-20 更新**：此條的狀態註記已過期。`tickers_missing_derived` 與上述三個符號
  都已在遠端 `2a3808aa3` 裡；`strategy_lab/finmind_batch_update.py` 目前的工作樹差異是**他人**
  的未提交內容，仍然不可整檔 commit。決策內容本身不變。）
- `chipscore_daily` 沒有最新交易日（11/16 的篩選也是 `chipscore: 0`）是**天天如此**的
  結構性缺口，本次未處理，short 分數的 chip 來源仍長期缺料
- `tickers_missing_derived` 用 `sma_13 = 0` 當佔位值訊號，極少數 Close 全為 0 的列會被
  無害地重算一次（冪等，不改變結果）

**驗證**:
- 18:20 篩選：run_id=110，24 列 distinct=24，每個 `(bucket, horizon)` 皆 3 檔，log 無 FAILED
- 補算後複查：`change_pct` NULL 1,964 → 0、`sma_13` 全 0 → 0、`rsi_14` 全 0 → 1、漲跌幅範圍
  與 11/16 一致
- 上游 `recompute_derived()` 對 5 檔抽樣重算 → 與補寫值逐欄 0 差異
- 新 helper：健康日期回報 0 檔；人為清空 5 檔後 5 檔全數偵測到
- `pytest tests/`：245 passed / 1 failed（唯一失敗為既有的
  `test_db_config.py::test_missing_password_fails_closed`，成因是他人未提交的
  `scripts/db_client.py` registry fallback）
- 8 個改動頁面 inline script 全數 `node --check` 通過；瀏覽器實測 nav 9 tab、
  逐檔與每日兩個視角、`?view=day` 深層連結、console 無錯誤
- 詳見 `docs/RESP-2026-11-17-02-screen-verification-derived-fix-pick-history.md`

---

## D021: 發佈器要等它所認證的生產者

**日期**：2026-11-18

**Context**:
22:50 的發佈器等 nightly 結束（23:09）後，在 23:10-23:19 執行 publish。gh-pages 的 push 成功
（`acb690161 Verified daily status 2026-11-17`），但 postflight 回傳 exit=1 →
`publish_verified_sites.ps1` 在第一個子腳本後就 `exit` → `sync_groove_release.py` 與
`chip_push.py` 從未執行 → `C:\Groove-Lab`（groovelab.dev 的來源）停在 11/16，線上落後一個
session，要靠跨午夜的 hourly catchup（00:00 `PUBLISH_ONLY` → 00:09）才補上。

真正的失敗 check 不是排程時序，而是 postflight 的 `company_null`：`daily_data2_full` 當日的
`company` 空值必須 ≤5，而填公司名稱的 `tw-invest-suite-company-refresh` 排在 **23:25** ——
比發佈器晚。23:19 時空值尚未清乾淨 → check 失敗 → postflight `overall_pass=False` →
dashboard 轉 CRITICAL → exit 1。00:05 重跑時 `null=0` 就通過了。

（附帶釐清：`company-refresh`／`sync-legacy`／`health-check` 這些晚到任務在 postflight 裡只進
`warnings`，本來就不會讓 postflight 失敗；`checks["tasks"]` 的 pass 恆為 true。）

**Decision**:
1. **在程式碼層讓發佈器等它依賴的生產者**（`scripts/publish_ghpages_daily.ps1`，repo 與 runtime
   同步為同一份 bytes）：
   - 等 nightly 停止（既有行為）
   - 若 nightly 是「今天」跑的，再等 `tw-invest-suite-company-refresh` 與
     `tw-invest-suite-sync-legacy` 今日已執行過
   - 判斷用 `LastRunTime.Date`（**不看 rc**）：producer 真的失敗時應讓 postflight 如實失敗
     （fail-closed），而不是讓發佈器空等到 deadline
   - 等待以既有的 `$deadline` 為界
   - 跨午夜的 catch-up 路徑不等待（該時段生產者已在目標日跑過）
2. **不動認證閘門**：`company_null` 的 ≤5 標準維持，不為了讓發佈早一點而放寬。
3. **不改成排程時間**：原本想把 `tw-invest-suite-publish` 的觸發從 22:50 移到 23:45，但該工作
   排程以 S4U 登入，`Set-ScheduledTask` 被 ACL 擋、`schtasks /change` 要求互動式密碼
   （且不得由代理處理）→ 改用程式碼層的依賴感知等待：版本可控、不依賴排程權限、也擋得住
   未來有人把觸發時間往前調。
   - 備份：`scripts/_debug/publish_task_before_20261118.xml`（原始觸發 `2026-10-06T22:50:00+08:00`）

**Why**:
- 發佈器認證的資料，是那些「晚於 nightly、但在發佈前」才生產出來的欄位。認證閘門本身沒錯，
  錯的是發佈時機早於資料生產者。
- 等「任務有跑過」而不是等「任務成功」：失敗的 producer 應讓 postflight 如實失敗，而不是讓
  發佈器空等兩小時。
- 等待寫在程式碼裡比寫在排程裡好：排程時間要提升權限才能改，且下次有人把時間往前調就會悄悄
  退化回同一個坑。

**Trade-off**:
- 發佈會從約 23:19 移到約 23:31（等 company-refresh 與 sync-legacy），比原本晚約 12 分鐘，
  但**同夜就完成**兩站同步與 Telegram push，不再需要靠跨午夜補同步。
- 若 company-refresh 當天真的失敗，postflight 仍會失敗（正確行為），此時仍需靠 catchup 補。

**驗證**:
- repo 與 runtime 的 `publish_ghpages_daily.ps1` SHA-256 一致；BOM 與原有行尾保留；
  PowerShell parser 無錯誤
- guard 條件實測：nightly 昨天跑（catch-up 路徑）→ 不等待；nightly 今天跑（同夜路徑）→
  等到 23:25／23:30
- `run_daily.ps1` 只有短路模式 `-Mode publish` 才會呼叫 publisher；排程的 daily-report 用
  full mode → nightly 不會被這個等待拖住
- 詳見 `docs/RESP-2026-11-17-02-screen-verification-derived-fix-pick-history.md`

---

## D022: 完整性檢查的四項修補——不靜默丟分頁、不靜默改位元組、補算不綁死流程

**日期**：2026-11-19

**Context**:
例行資料完整性檢查（官方 chain audit + DB 層稽核）確認 DB 與認證鏈健康，但發現四個缺陷，
其中兩個是我自己造成的：

1. **P1 live 精選頁少一頁**：18:00 的 news-only 重渲染把 live 的 `watchlist.html` 覆蓋成
   沒有「🎯 潛在反彈」分頁的版本（該日融資資料尚未載入 → 候選回空 → 分頁被靜默略過），
   使用者整天看到少 60 檔的頁面。官方 audit 的 `manifest hash_mismatch=1` 就是它。
2. **P3 Groove 收據永遠 failed**：我 11/16 新建 `watchlist-history.html` 時忘了把它加進
   `C:\Groove-Lab\server.py` 的認證頁白名單 → 該頁只送 `no-store`、少了 `no-transform` →
   Cloudflare 有權注入 Web Analytics beacon → 位元組驗證必敗 → 連帶 Telegram 籌碼摘要
   自 11/13 起未送出。
3. **P4 FinMind 衍生欄位補算仍會被跳過**：11/19 的 18:00 那班在資料集迴圈之後中止，
   而 derived 補算排在迴圈之後 → 最新交易日再次留下佔位值（`change_pct` NULL、sma/rsi 全 0），
   18:20 的篩選因此用壞掉的 short 評分選股。19:00 那班才補回來。
4. **P2 Telegram 未送**：是 P3 的下游症狀，不是獨立缺陷。

**Decision**:
1. **P1：分頁不可靜默消失**。`_fetch_margin_distress_candidates()` 改為逐級回退：
   今日 scan JSON → 最新已產生的 scan JSON → 最新有 `MarginBalance > 0` 的日期的 DB fallback → 原行為；
   回退到較舊日期時分頁顯示「⚠ 本次融資資料日為 X」。
   教訓：**呈現層遇到上游資料未到時，應降級顯示並標明，而不是整段消失**。
2. **P2/P3：兩端都修**。伺服器白名單補上 `/watchlist-history.html`（`no-transform` 讓邊緣不得改寫），
   驗證端另外容忍 beacon 注入（只移除那一支 script，其餘差異仍失敗，被容忍路徑記進收據）。
   教訓：**認證鏈的位元組比對不該被 CDN 的行為改變**——但也不能因此放寬比對，所以兩端都補。
3. **P4：補算不得綁死在資料集階段的成敗上**。derived 補算移入 `finally`，只要 price 階段在範圍內
   就一定執行；而且 price 階段即使 `affected_rows=0`（狀態已標記完成）也會用佔位值偵測補算。
   教訓：**衍生欄位是價格的純函數，它的補算不該依附在任何會失敗的步驟之後**。
4. **每次修補都要有「故障注入」證據**：把一列的衍生欄位清成佔位值 → 重跑 price 階段（空跑情境）
   → 確認修回且值與原值完全相同。

**Why**:
- 三個缺陷的共同形狀都是「**靜默**」：分頁靜默消失、位元組靜默被改、補算靜默被跳過。
  靜默的失敗最貴，因為沒有任何一處會報錯，只有看結果的人會發現。
- P1 的修法選擇「顯示舊資料並標明日期」而不是「等資料到了再顯示」：使用者要的是一份完整可讀的頁面，
  帶著明確的資料日標記，比少一頁好。
- P3 兩端都做是因為兩端各有道理：伺服器端讓線上回應回到認證位元組（根本解），
  驗證端容忍注入則讓這條鏈在邊緣行為改變時不會再次卡死（韌性）。

**Trade-off**:
- 分頁回退會顯示較舊日期的融資資料；已用頁面上的資料日提示揭露，不再假裝是最新。
- origin 行程需提升權限才能重啟，`no-transform` 要等它下次自然重啟才生效；在此之前靠驗證端的容忍層維持管線通暢。
- P4 只保證「price 階段在範圍內就會補算」；若 price 階段本身失敗（OHLCV 沒寫進去），
  補算會寫 0 值而不是 NULL——那是 fail-closed 的正確行為。

**驗證**:
- P1：runtime 副本實測 `_fetch_margin_distress_candidates(top_n=60)` → `candidates=60 source_date=2026-11-18`
- P3b：線上實測 `verify_paths` → `verified=5 tolerated=['watchlist-history.html'] PASS`
- P4：故障注入測試 → 清空 2330 的 7 欄 → price 階段 `affected_rows=0` → `[derived] updated_rows=1`，
  修回值與原值完全相同
- `pytest tests/`：見同日的執行結果（唯一失敗為既有的 `test_db_config.py`）
- 詳見 `docs/RESP-2026-11-17-02-screen-verification-derived-fix-pick-history.md` 第 8 節

## D023: 認證鏈的兩個基礎設施缺陷——狀態檔競態與午夜快照缺口

**日期**：2026-11-20

**Context**:
複查 11/19 的 nightly 成品時，結論不是「成品待確認」而是**失敗**：Stage 1 的 `finmind_maint`
掛掉 → 整輪 FAILED → 無 marker、無發布、無 Telegram。追查過程中挖出兩個**先前未知**的基礎設施缺陷：

1. **P5：132 MB 續傳狀態檔的原子替換競態**。`AI-Telegram` 的 `StateStore.save()` 用
   `tmp.replace(self.path)` 替換 `finmind_batch_state.json`；同一個檔案有兩個 producer
   （`AI-Telegram Scheduled Pipeline` 與 nightly 的 `_fetch_today.py --phase canonical`，
   22:00:29 與 22:00:33 兩支 `canonical_universe_*.json` 可證），贏的那個把輸的那個的
   原子替換打成 `[WinError 5] 存取被拒`，於是整個 canonical 階段中止。
   這不是 regression：`dl_errors.jsonl` 裡同型錯誤已出現 5 次（10/13、10/15、**11/11**、11/12、11/19），
   11/11 那次 nightly 也以完全相同的型式失敗。
2. **P6：午夜補救跑永遠落在供應商的快照缺口裡**。`refresh_market_map()` 只查
   `TaiwanStockInfo` 的「今天」。實測該供應商**只保留一份完整快照、日期標成今天**
   （3,358 列），過去日期只留 1–2 列差異紀錄，而完整快照約在**午夜後一小時**才發布。
   因此 00:00:01 的補救跑永遠查不到東西 → Stage 1 valuation 失敗 → 整輪 FAILED。
   這個失敗在 **09/30、10/01、10/02、10/03、10/06、10/07、10/22、11/04、11/12、11/20 共 10 次**，
   也就是說**每小時的認證補救網自 2026-09-30 起就是壞的**——這才是 11/11 與 11/19 的
   nightly 失敗後從未自癒的真正原因（不是沒人重試，是重試機制本身壞了）。

**Decision**:
1. **P5：狀態檔的原子替換要能承受被鎖**。`StateStore.__init__` 改成先
   `path.read_bytes().decode("utf-8")` 再 `json.loads`（讀完關 handle 再解析，避免 132 MB 檔
   在解析期間被別的 producer 鎖住）；`save()` 在 `PermissionError` 下退避重試
   （8 次、上限 3.0s、最長約 13.5 秒），最終仍失敗才重新拋出。
   教訓：**續傳 marker 只是快取，資料本身已進 DB——掉一個 marker 只值一次重載，不值得中止整個階段**；
   但重試必須有上限，最後仍然 fail-closed。
2. **P6：listing venue 要能在快照缺口期解析，而且不能靜默接受殘缺快照**。三層：
   (a) 查 7 天視窗而非今天；(b) **完整性門檻**——完整快照有數千列、差異日只有 1–2 列，
   `MIN_LISTING_SNAPSHOT_ROWS = 1500` 把「已發布」「發布中」「只有差異」分開，
   **半成品發布不再會被誤當成完整快照**（原程式會直接收下當天所有列）；
   (c) **備援來源用交易所自己的 Open Data**（TWSE `t187ap03_L` 1,098 檔 ＋ TPEx `mopsfin_t187ap03_O`
   898 檔，聯集 1,996、零衝突），因為交易所名單**沒有發布排程**，午夜隨時可用。
   另把 venue 來源寫進 `finance_fetch.json` 收據（`venue_source`／`venue_source_date`）。
   教訓：**跨午夜抓「當日快照」型資料時，必須有完整性門檻與不依賴供應商排程的備援**；
   依賴單一來源的排程，等於把可預期的缺口寫進排程。
3. **P7：認證鏈有兩組獨立的來源雜湊檢查，run 進行期間不可變更相關檔案**。
   `source_hashes()` 在 `finalize_inputs` 與 `complete` 兩處各擋一次，而且各有兩種失敗：
   runtime↔repo SHA 不符（`runtime/repo SHA mismatch`），以及與 run 開始時記錄的
   `run['source_hashes']` 不符（`Source changed before input finalization`）。
   我在 02:00 那班執行中套用 P6，直接把整輪打回 FAILED（Stage 1 四階段全綠只差最後一道）。
   教訓：**認證鏈的防線是「run 開始到結束之間來源不可變」，所以修補必須排在 run 之外**；
   每小時的 catchup 會自己重試，改完等下一班比手動觸發安全。
   已寫進 `AGENTS.md`「不要做的事」第 10、11 項。

**Why**:
- 兩個缺陷的形狀都是「**別人擋住我**」：狀態檔被鎖、快照還沒生出來。兩者都不該讓整條認證鏈中止。
- P6 特別值得做成「雙來源」，因為它的缺口是**供應商的排程**，不是我們的 bug；
  依賴別人的排程就等於把自己的復原能力交出去。交易所名單反而是最穩的那一份。
- P7 是這次過程中學到的最重要的操作性教訓：認證鏈有防線，而防線的觸發條件比想像中寬。
- 覆蓋率比較支持這個方向：官方名單對估值宇宙 1,974 檔覆蓋 1,966，**優於**供應商快照的 1,958；
  且兩者在 1,982 個共同代號上 `.TW`／`.TWO` 完全一致 → 換來源不會讓已快取的估值資料失效。

**Trade-off**:
- 備援來源的**宇宙覆蓋率反而比較高**：交易所名單對 1,974 檔宇宙覆蓋 **1,966**，供應商快照只有 1,958。
  11/19 那 16 檔缺估值快取的代號裡，有 8 檔（1808 潤隆建設、4804 大略國際、8084 巨虹電子、
  8291 尚茂電子材料、9103 美德向邦、9105 泰金寶、9110 越南製造加工、9136 巨騰國際）官方名單有、
  供應商快照沒有 → 走備援時這 8 檔反而拿得到 venue、可能補回快取。
  代價是官方名單不含 ETF／ETN（供應商多那 421 檔），但 ETF 碼不在 1,974 的估值宇宙內。
- 每次 venue 解析多打 1 次供應商查詢；備援成立時再多 2 次交易所 HTTP（僅在供應商無完整快照時）。
- 完整性門檻 1,500 是經驗值（實測完整快照 2,403 列、差異日 ≤17 列），若市場規模量級改變需重估。
- P5 的重試最長約 13.5 秒；最壞情況下 canonical 階段仍會失敗（fail-closed）。

**驗證**:
- P6 故障注入 8 情境全綠：完整快照走供應商、午夜缺口走交易所、發布中取較早的完整快照、
  供應商錯誤走交易所、兩邊都掛 fail closed、注入 rows 維持既有尾綴語意、過期／衝突 rows fail closed。
- venue 一致性：官方與供應商在 1,982 個共同代號上尾綴相反 **0 處** → 切換來源不使快取失效。
- `pytest tests/test_valuation_sources.py -q` → 7 passed；runtime 實際檔案
  `refresh_market_map()` → `{'source': 'provider', 'source_date': '2026-11-20', 'mapped_tickers': 2403}`。
- P5 於正式排程驗證：02:00 那班 `finmind_maint` 於 02:10:37 exit 0（132 MB 狀態檔寫入成功，無 WinError 5）。
- 詳見 `docs/RESP-2026-11-20-01-nightly-failure-root-cause-and-recovery.md`

## D024: 認證成功不等於發布成功——排程的退出碼不可用來判斷現在的狀態

**日期**：2026-11-20

**Context**:
11/19 在 04:04:34 終於取得有效認證（`last_completed.json`：`status=ok`、`data_date=2026-11-19`、
`nightly_id=db92dacd…`），GitHub Pages 也發布並遠端驗證成功（commit `c2df18c3`）。
但 **Groove 同步與 Telegram 籌碼推送沒有執行**——Telegram 收據停在 11/13。

追下去是一條完整的循環依賴：

```
tw-invest-suite-daily-report（就是 nightly 本體，21:30 觸發）在 11/19 失敗 → task rc=1
  └→ build_dashboard.py 把 daily-report rc≠0 判成 🔴 CRITICAL（dashboard exit 2）
      └→ postflight_daily.py 看到 dashboard exit≥2 → overall_pass=False → exit 1
          └→ publish_ghpages.py 只看 post.returncode → status 翻成 "failed" → exit 1
              └→ publish_verified_sites.ps1 逐段檢查 exit code → 在 Groove 同步前停下
                  └→ chip_push.py 沒跑 → Telegram 收據停在 11/13
```

`tw-invest-suite-daily-report` 的 rc=1 **就是 11/19 nightly 失敗的倒影**。catchup 在 03:00
重跑並成功認證之後，這個 rc 仍是舊的，要等到 11/20 21:30 的下一次 nightly 才會被覆蓋。
於是只要某一晚 nightly 失敗，恢復路徑就會被永久堵住。

這與 D023 的 P6 是同一種病：**用一個過時的失敗訊號去判斷現在的狀態**。

**Decision**:
1. **認證若發生在某個排程上次執行之後，就代表那次執行已被取代** → 該排程的 rc 降級為 🟡 WARNING
   （仍顯示在 Action items，不靜默）。判定用 `marker.started_at` 與 task `last_run` 比較；
   兩者都是本機時間，取前 19 個字元做字典序比較即可。
2. **認證成功與發布成功是兩件事，收據要分開看**。`publication_result.json` 記
   `postflight_exit`，`groove_publication_result.json` 與 `chip_telegram_result.json` 各自記自己的批次；
   只有三者都對上同一個 `nightly_id`，`certified_for()` 才回 true。
3. **改了被 `source_hashes()` 涵蓋的檔案，就讓 catchup 重跑認證**，不要手動重簽 marker。
   手動改 marker 的雜湊等於偽造認證證據，絕不允許。

**Why**:
- 排程的 `last_task_result` 描述的是**那一次執行**的結果，不是「現在的狀態」。
  當有更晚的、已認證的執行存在時，用舊 rc 判斷現在是錯的。
- 把失敗降級成「仍可見的警告」而不是「消失」，是為了維持「不可靜默」的原則：
  使用者仍然看得到那晚 nightly 失敗過，只是不再被它卡住。
- 這個缺陷的殺傷力在於它讓 P5／P6 的修補成果無法落地：認證成功了、GitHub Pages 也上線了，
  但兩站與 Telegram 仍然停在舊日期。**修好上游而沒修好下游，等於沒修。**

**Trade-off**:
- 排程 rc 的判定不再單獨決定發布，因此一晚 nightly 失敗後，該晚的失敗不會阻止恢復發布。
  這是刻意的：真正的成功判準是 marker ＋ 發布收據，不是排程的退出碼。
- 改了 hashed 檔案就必須重跑整條 nightly（約 70 分鐘）才能重新認證。代價是時間，
  好處是認證證據永遠與當下的原始碼一致。

**驗證**:
- 修補前：dashboard 判 🔴 CRITICAL（exit 2）→ postflight exit 1 → publication status=failed。
- 修補後（同一份 marker 與 receipt）：daily-report 的 rc=1 被判為「已被 db92dacd 的成功認證取代」的
  🟡 WARNING；dashboard 不再產生 CRITICAL。
- 05:00 的 catchup 以 `run_daily.ps1 -Force` 重跑整條並重新認證，隨後發布；
  Groove 與 Telegram 收據隨之更新（結果見 `docs/RESP-2026-11-20-01-nightly-failure-root-cause-and-recovery.md`）。
- 詳見 `docs/RESP-2026-11-20-01-nightly-failure-root-cause-and-recovery.md`
## D025: 閘門要用模型自己的期限評估；門檻先不動，先補特徵管線

**日期**：2026-11-20

**Context**:
出發點是「重算閘門門檻」。複查後發現兩件事擋在前面：

1. **期限錯配**。production 模型是 20 日模型（`p_win20_net_1pct`／`p_big_loss20`／
   `pred_net_return`），但前瞻驗證 ledger 只實作 `horizon_5d`／`horizon_10d`。
   **閘門從來沒有用它自己的期限被評估過**：ledger 只記 5d 與 10d。
   同一列組（quality_ok ∧ 現行閘門 ∧ 有 20 日結果的預測日 → 78 列、2 個預測日）上：
   ADD 超額 5 日 +2.71pp、10 日 +0.41pp、20 日 +7.51pp（三個期限都贏過市場），
   但**絕對報酬** 5 日 −2.12%、10 日 +1.31%、20 日 −3.59%。
   只看 ledger 現有的 5d／10d，會把這批訊號讀得比實際好——10 日是唯一顯示正絕對報酬的期限。
2. **樣本不足**。改到 20 日期限後，22 個有完整 20 日結果的交易日裡，現行閘門只在
   **2 天**觸發 ADD（2026-06-18／06-22，共 78 列）＝閘門自身 4,892 列的 1.6%。
   78 列、2 天、同一個崩盤 regime，不足以定任何門檻。

追下去發現真正的病因在上游：**三個特徵管線缺口**（chip／us_anchor／news），
以及 `p_big_loss20` 的當日 floor 在相鄰日擺動 13 倍（0.033~0.432），
使整帳在 ADD 與 REDUCE 之間翻面——**閘門是症狀，管線是病因。**

**Decision**:
1. **閘門門檻不動**（`min_win_prob=0.50`／`max_loss_prob=0.98`）。
   在模型自己的期限上只有 78 列可用，任何門檻都是過度配適；
   而把門檻放寬以提高樣本，恰好會放大全帳翻轉的日子。
2. **先修證據層**：ledger 增加 20 日期限（`horizon_20d_status`／`return_20d` 等），
   摘要與 `by_action` 同步輸出 10 日與 20 日。**評估閘門前先確認 ledger 的期限 == 模型的期限。**
3. **先修特徵管線**：用官方建置器 `data-downloader/stock_chip_features.py`
   以 `--source-table daily_data2_full` 重建 2020-01-02~2026-06-11 的歷史區段，
   補上 live 視窗缺列的 37 天；補 `us_anchor_features_daily` 的 2026-06-22~09-30；
   以本地 `stock_news` 原料庫重建 live 視窗的新聞特徵。
4. **加覆蓋率守門（fail-closed）**：推論當日 chip 覆蓋率低於
   `daily_prediction.min_source_coverage`（0.95）→ 該族特徵視為缺漏、
   **當日不發布任何 ADD**、收據記 `coverage_gate`。
5. **重訓但不推廣**：依 RESP-2026-11-12-01 §5.2 的規格重訓（train 2023-01-01~2026-03-31、
   validation 2026Q2、playback 2026-06-18~11-12），**沿用生產特徵集**以便一對一比較；
   線上 bundle 不換，推廣另需授權且要滿足 RESP-2026-11-12-01 §5.3 的門檻。

**Why**:
- 閘門要評的是 20 日的東西，ledger 卻只給 5 日與 10 日的答案：同一列組的絕對報酬
  5 日 −2.12%、10 日 +1.31%、20 日 −3.59%，只看前兩個期限會讀得比實際好。
  在這種情況下調參數等於在錯誤的座標系裡找答案。
- 「78 列、2 天」是硬上限：閘門只在市場最糟的兩天開過，那些天的樣本不能代表
  閘門在正常市場下的行為。放寬門檻會讓樣本變多，但每一個新增樣本都來自
  `big_loss20` floor 抬高日的全帳翻轉，**會把最糟的行為學成規則**。
- 特徵管線的缺口才是可修的東西，而且修完之後，模型才第一次在「訓練與服務同一個分布」
  的條件下被評估。RESP-2026-11-12-01 §5.1 已經寫明：**P1～P3 完成前重訓是浪費**。
- 覆蓋率守門是 2026-11-12 稱為「最惡劣失效模式」的那一個
  （管線故障 → 閘門全開 → 在最糟的日子造成最大損失），
  而它「可以在發佈前被擋掉」——所以擋掉比調參數優先。

**Trade-off**:
- 門檻維持現值，等於承認目前**沒有可用的閘門**；在新的新鮮前瞻驗證累積夠之前，
  線上的 ADD 清單仍可能整日翻轉（但現在會被覆蓋率守門擋掉退化日）。
- 20 日期限要多 20 個交易日的資料才會完成，ledger 的 `pending_20d` 會長期偏高；
  這是誠實反映「模型還沒被自己的期限驗證過」，不是缺陷。
- 重訓用了 RESP-2026-11-12-01 §5.2 的三年視窗（924 個交易日、約 106 萬列），記憶體與時間成本都高於
  原來的一年視窗；但只有把 chip 覆蓋率拉平，這個視窗才有訓練價值。
- 新聞家族的原料庫重建會讓 live 視窗的新聞密度（~70 檔/日）高於訓練窗（平均 16.3 檔/日），
  這是兩條收集路徑密度不同造成的；要完全對齊需要把訓練窗也用原料庫重建（924 天，約 7.7 小時），
  或把新聞整族排除在特徵集之外。兩者都需要另外的授權。

**驗證**:
- chip 覆蓋率：train 11.4% → **98.9%**、validation 11.3% → **99.0%**、
  live → **98.9%**（天數也補齊）；整張表（2026-11-20 14:40 量測）
  **3,646,918 列／1,664 日／2,626 檔**、單一 `data_source='daily_data2_full'`，
  legacy 的 418,327 列／273 檔殘表清空。
- us_anchor：live 視窗 39/97 → **97/97**。
- news：live 視窗 41/97 → 補齊（原料庫重建）；單日驗證 2026-06-25 由 1 檔變 72 檔。
- 覆蓋率守門：以 `data_policy.local.json` 把門檻暫時設成 1.01（不可能值）做受控驗證，
  確認 `coverage_gate` 被寫入且當日不發布 ADD；驗證後移除覆寫。
- ledger 20 日期限：`pytest test_forward_validation_refresh.py test_forward_validation_coverage.py`
  → 20 passed。
- 重訓結果與與現任模型的對照見 `docs/RESP-2026-11-20-02-gate-evidence-and-feature-pipeline-repair.md` §4。

## D026: 週末不是「沒有資料要更新」，是缺了把已提交的 picks 綁回 run state

**日期**：2026-11-22

**Context**:
1. 11/21（週六）21:30 的 nightly 失敗在 Stage 7：`src/all_reports.py:99` 取 `run['picks']` → `KeyError`。
   但 `run['picks']` 從來不是 render 寫的，是 `finalize_inputs` 綁的；而 `finalize_inputs`
   只存在於 `run_daily.ps1` 的**交易日分支**裡。週末跳過下載階段 → 那兩個鍵從頭到尾不存在。
   **旁證**：資料庫 `market_screen_runs` 的 `run_date` 全部是平日，週末從無新的 screen run，
   但週五那次（run_id 119）的 24 檔 picks 一直在 DB 裡、全部 active——**picks 一直都在，只是沒綁**。
2. **週末路徑從未被認證過**：`public/data/publish_manifest_*.json` 只有平日（最新 2026-11-20）。
   11/22（週日）21:30 會以完全相同的方式失敗。
3. 同一個根因也解釋了稽核症狀：11/21 的 render **已經改寫 1,974 個 analyze 檔**才在 Stage 7 崩，
   所以 manifest 對不上 → chain audit 報 1,978 個 hash 不符。**一個根因、兩個症狀。**

**Decision**:
1. **新增 `pipeline_state.py bind-screen-inputs`**：把 DB 已提交的 24 picks／run_id／picks_count／
   bucket_counts 綁進 run state——`finalize_inputs` 之外的第二條綁定路徑，
   給沒有跑 canonical refresh 的執行（週末、帶 `-SkipFinmind` 的 catch-up）使用。
   `run_daily.ps1` 在 `finalize_inputs` 不存在時補上這個 stage。
2. **週末重渲染不得改動 canonical 資料**：bind 重算 `canonical_inputs_hash(data_date)`，
   必須與**上一次認證**的 `canonical_inputs_sha256` **位元組相同**，不同就拒絕綁定；
   相同才記 `inherited_maintenance_nightly_id`，讓新認證**繼承**上一輪的維護收據。
3. **只放寬 catchup／guard 的 maintenance 綁定**（同一 nightly_id **或**同一繼承來源）。
   publication 的 nightly_id 仍須與 marker 相等；marker 的 data_date／marker_version／status 照舊。
4. **`complete()` 與 `all_reports.py` 的缺鍵改成名單**：講清楚缺什麼，不再丟 KeyError。
5. **yfinance 在非交易日不再誤報**：目標日期本來就沒有 session，0 個新鮮標的是正確答案；
   獨立排程也不再覆寫 nightly 的 `finance_fetch.json`。

**Why**:
- 認證鏈的每一段都在回答同一個問題：**這批產物是從哪一份 canonical 資料、哪一次認證長出來的。**
  週末缺的不是資料，是那條綁定。
- 維護收據證明的是「那份 canonical 資料有從供應商正確刷新過」——它綁的是**資料**，
  不是**某一個 nightly 實例**；把它綁到 nightly_id 上只是交易日的巧合，週末兩者必然分岔。
- 放寬的邊界不是「信任」而是「證明」：繼承的前提是 canonical 摘要位元組相同，
  這比 nightly_id 相等更嚴格。
- 若只補「綁 picks」而不處理收據繼承，週末認證會成功，**但 catchup 每小時都會判定未認證
  → 每小時重跑一次整條 nightly**。能認證不等於修好。

**Trade-off**:
- 每次週末認證多算一次 canonical 摘要（實測 52.5 秒）→ bind stage 的 timeout 由 120s 提到 420s。
- 週末認證會重寫 `public/` 產物並發佈一次與週五同資料的新 manifest——這是 run_daily.ps1
  週末分支本來就寫著的設計（only render + patterns + publish），代價是發佈流水線週末多跑一次。
- `certification_catchup_guard.ps1` 原本不在版控內（認證鏈的 9 個孤兒之一）。
  這次為了改 maintenance 綁定必須動它，因此一併納入版控，否則這個修正會變成新的孤兒。

**驗證**:
- 隔離單元驗證：模擬 11/21 的 run state（status=running、無 picks、無 run_id）→ bind 成功綁定
  24 picks、run_id=119，且與 DB 即時快照完全一致；二次綁定被擋。
- canonical 連續性：2026-11-22 量測，現行 `canonical_inputs_hash('2026-11-20')`
  與 11/20 認證存下的 `canonical_inputs_sha256` **相同**（52.5 秒）。
- `maintenance_claim_holds()` 六項斷言：同一輪／繼承／摘要備援（相同摘要 True、錯誤摘要
  False）／requested_date 不符 → False。
- 端到端：2026-11-22 17:21:06 **週末路徑第一次被認證**（`adbf6c6c…`、data_date 2026-11-20、
  7 個 stage 全綠、2,037 個產物、degraded 0）；`inherited_maintenance_nightly_id` 指向 11/20
  那一輪。發佈 exit 0、`postflight_exit=0`、manifest 重寫（1,978 個 hash 不符歸零）、
  Telegram `already_sent=True`（未重複推送）。chain audit 只剩「未曾從睡眠喚醒」一項 finding。
- 收據細節見 `docs/RESP-2026-11-22-01-weekend-nightly-repair-and-daily-task-health.md` §5。

## D027: 危險名單要沿用既有的風險定義，等級靠徽記不靠顏色

**日期**：2026-11-24

**Context**:
Walter 要兩個新頁籤：一個是「我應該 asap 賣出」的危險名單，一個是「AI 自己模擬買賣並記帳」的
AI 帳（AI 帳等危險頁的規則定下來再做，否則帳本會和危險規則打架）。

**Decision**:
1. **危險頁不重新發明風險分數**：rows 直接來自 margin-rebound scan 的輸出（那已經是認證鏈的
   stage 5，130% 硬規則與 7 維加權都是既定的）。危險頁只是同一份資料的另一個視圖——
   同一份資料不能有兩個定義（chip 表踩過這個坑）。
2. **等級沿用掃描的 tier**：tier 1（維持率 < 130%）= ⚠️ 危險，tier 2（130-150% 且融資連 3 日下降）
   = ⚡ 警戒；排序 = 先等級、再 7 維風險分數。不另設門檻。
3. **顏色分工**：方向欄（漲跌、融資增減、20 日預期淨報酬、20 日大跌機率）用全站慣例
   **紅＝多／漲／正、綠＝空／跌／負**；等級由 **⚠️／⚡ 徽記**承載，維持率與風險分數用數字呈現。
   理由：這一頁的「壞」訊號大多是賣超與下跌，若直接塗紅綠會讓同一個顏色有兩種意思。
4. **頁面並列互相矛盾的看法，不取捨**：掃描的說明說「短線反彈候選」，模型對 629 檔仍給 ADD。
   「該賣」與「模型說買」放在同一列，讓人自己判斷。
5. **產生認證產物的腳本本身必須被雜湊**：`src/danger_signals.py` 加進 `REPO_SOURCE_FILES`
   （同 `stock_features_daily.py` 那類漏洞）；8 頁的跨頁 nav 全部加上新頁籤。

**Why**:
- 認證鏈裡已經有一個被證明可用的風險定義，再寫一套只會製造兩種真相。
- 頁面是**警訊**不是**決策**：把證據攤開，門檻與排序是規則，買賣是人的判斷。

**Trade-off**:
- 粒度是每日收盤後（不是盤中）→「asap」＝明早開盤前的清單。
- 母體是全市場 1,251 檔，不是持股；持股優先需要持股清單來源（手動檔或券商匯入），
  資料層已把 ticker 與事實拆開，之後加一層篩選是薄的。

**驗證**:
- 2026-11-23 的掃描輸出 → 1,251 候選、853 危險、398 警戒、865 檔有模型訊號。
- HTML 結構驗證：1,251 列與 JSON 一致、標籤平衡、無亂碼、nav 有新頁籤；瀏覽器目視通過。
- 改動 nav 後 `daily_certification_catchup.py --check-only` 立刻回 `READY_FOR_CATCHUP`
  → hourly catchup 會自動重跑並重新認證（D026 補上的產物漂移自癒生效）。
- 細節見 `docs/RESP-2026-11-24-01-danger-list.md`。

## D028: 危險頁要能被自己推翻——帳本 append-only、只看超額、成績公開

**日期**：2026-11-24

**Context**:
「這張表準不準、怎麼追蹤」的問題，量下去有三個發現：
1. **清單的歷史根本沒被記下來**：`history.json` 每檔只有 `first_seen / tier / last_seen`，
   沒有逐日旗標紀錄 → 無法回測、也無法證明任何事。
2. **原始維持率有完整逐日歷史**：`finmind_taiwan_margin_maintenance` 147,044 列、
   **72 個交易日**、每日約 2,050 檔、`maint_source` 全部是 finmind（單一來源）。
   所以可以回溯重建，也可以從今天開始逐日留痕。
3. **基準率太高**：硬規則每天標到 27-47% 的全市場（11/23 標 877 檔）→
   「被標的跌了」幾乎是必然 → **只有超額與「贏過市場的天數」有資訊量**。

第一次量測（回溯 72 天）：超額 +0.49~+1.33pp、63~80% 的交易日贏過市場，
**但 1~20 日的絕對報酬仍然是負的**（賣掉比不賣少賠，不是賺）。這跟 D025 的閘門評估同形。

**Decision**:
1. **每日帳本 append-only**：`public/data/danger-history/<date>.json` 記該日發佈的旗標集合，
   **既有檔案永不覆寫**（帳本記的是「當時發佈了什麼」）。
2. **規則版本進帳本**（`D027-v1+<scan.py 雜湊前 8 碼>`）：日後改權重或門檻，
   歷史必須用「當時的規則」評估，否則就是事後改答案。
3. **評估只看超額，不看絕對報酬**，且必須與**同批交易日的等權全市場**比。
   判定用 live 記錄前 20 個交易日，之後只用 live；不足 20 個就用回溯量測並標明來源。
4. **live 與回溯分開記**，頁面標明哪個是回溯、哪個是 live。
5. **成績公開放在頁面上，連「沒有鑑別力」也寫**；頁面必須能自己推翻自己。

**Why**:
- 一個只會嚇人、不會被推翻的頁面沒有價值；把方法和判定一起公開，
  數字變差時使用者看得到，規則也就有了改的依據。
- append-only ＋ 規則版本是唯一能避免「事後改答案」的做法。

**Trade-off**:
- 每次認證多算一次回溯量測（約 1 分鐘的 DB 查詢）＋ 一份帳本檔（每 session 約 16 KB）。
- live 記錄在累積到 20 個交易日前，判定只能靠回溯量測。

**驗證**:
- 2026-11-24 實跑：帳本 `public/data/danger-history/2026-11-23.json` 寫出（16.5 KB）、
  `public/data/danger-track.json` 產出、判定 `has_edge`（來源 backtest，因 live 只有 1 個 session）。
- 回溯 72 天的超額：1 日 +0.59pp、3 日 +0.49pp、5 日 +0.51pp、10 日 +0.57pp、20 日 +1.33pp。
- 另一個發現：每個交易日被標檔數的期中位數 123，最近四天 552／744／964／877
  → 全市場槓桿壓力近期明顯升高。
- 細節見 `docs/RESP-2026-11-24-01-danger-list.md` §5。

## D029: AI 帳要能被自己推翻——規則寫死、帳本 append-only、判定看絕對報酬

**日期**：2026-11-25

**Context**:
Walter 要一個「AI 自己挑、自己買賣」的模擬帳戶，並且**要照著這份模擬實際下單、拿它支付服務費**。
所以這不是展示頁，是一個會決定他下一步動作的東西。

量完之後有三件事是確定的：
1. **模型的進場訊號目前沒有被證明有效**：唯一有已結算結果的視窗裡，AI 的 ADD 呼叫
   5 日淨 −10.17%（市場 −8.04%，−2.13pp）、10 日 −10.66%（−3.31pp），且不過閘門也一樣差。
2. **出場規則有鑑別力**：同一段期間 130% 維持率規則的超額是 +0.49~+1.33pp。
3. **模型 98% 的呼叫都是 ADD** → 只聽 AI 自己的訊號，它幾乎不會出場。

**Decision**:
1. **規則寫死並版本化（AIV1），且印在頁面上**：R1 收盤決策／收盤成交；R2 只做已發佈 24 檔的 long；
   R3 同時最多 6 檔等權不加碼；R4 每檔每天最多一筆（買或賣）；R5 出場四條件先到先算；
   R6 手續費 0.1425%×2 ＋證交稅 0.3%；R7 現金會計；R8 基準＝等權全市場；
   R9 判定線＝滾動 20 日「淨報酬 > 0 且超額 > 0 且回撤 < 25%」，連續 3 期不達線停止新進場。
2. **「一天一檔一筆」**（Walter 指定）：同日同時符合買賣時賣出優先，當日已賣不當日買回。
3. **空單不計損益**：台股個股幾乎不能做空，short 只記為「當日迴避」。
4. **判定線用絕對淨報酬，不是超額**：因為這個帳戶要拿來付費——超額為正但淨報酬為負，
   帳戶一樣會付不出錢。
5. **回溯段與 live 段分開標記**：規則是看過資料之後定的，所以 2026-11-25 之前標為回溯（含事後偏差），
   之後才是前瞻紀錄。帳本 append-only，每筆帶規則版本。

**Why**:
- 一個會決定他實際下單動作的東西，規則必須寫得出來、版本化、可逐筆驗算；
  否則出事時無法回溯是哪一條規則造成。
- 帳本必須能自己說「我沒有鑑別力」，否則它只是裝飾。

**驗證**（回溯 2026-08-12 → 11-24，56 個交易日、99 筆交易）：
權益 1,000,000 → 828,129、淨報酬 **−17.19%**、市場 −26.05%、**超額 +8.86pp**、最大回撤 −33.63%、
滾動 20 日通過 10/37。**判定 no_edge**：相對有價值、絕對沒有存活。
加上這套出場規則後，帳戶從模型的 −2~3pp 變成 +8.86pp → **edge 來自出場紀律**。
出場次數：跌出 24 檔 36、停損 8、20 日到期 2、危險規則 1。
- 細節見 `docs/RESP-2026-11-25-01-ai-ledger.md`。

## D030: AI 帳存活線不設用量上限——因為這條線就是 AI 帳的 funding 來源

**日期**：2026-11-25

**Context**:
Walter 看完用量回報後明確表示：**不對這條工作線設 token／用量上限，也不接受節流建議**。
理由是這條線本身（AI 帳存活計畫）就是支付 MiniMax 服務費／token 費用的來源——
在 funding 端省算力，等於削減未來的收入。

**Decision**:
1. **AI 帳存活計畫不設 token／request／時間上限**，允許完整跑完假設掃描
   （持有期限 20／40／60／90 交易日等變體一次跑齊，不做取樣）。
2. **沒有預算上限不等於沒有方法紀律**。以下四條是不變量，不因算力寬鬆而放寬：
   - 每次只改**一個**變因，其餘規則固定，才能歸因；
   - 跨變體比較必須用**單一母體**（同一批 56 個交易日、同一批進場池，D025 教訓）；
   - **判定線 R9 不變**（滾動 20 日淨報酬 > 0 且超額 > 0 且回撤 < 25%）；
   - **帳本不能自己改答案讓驗收變綠**。
   否則多算力只會加速過度擬合。
3. 成本控制的手段改為**算力而非金錢**：變體一律用參數化＋離線回溯掃描，
   不為每個變體新增認證產物、不反覆重跑 nightly、不動認證白名單。

**Why**:
- 這個帳戶的產出就是 funding，限制投入＝限制收入。
- 但放寬成本會同步放寬過度擬合的空間，所以放寬的是「算力預算」，不是「判定標準」。

**驗證**:
- 決策同步寫入交接文件 `HANDOFF-AI-LEDGER-SURVIVAL-2026-11-25.md`，並轉送到接手的新對話。

## D031: AI 帳目前的進場選擇是「代號升序」、部位 sizing 讓第 6 檔補不進——帳本還沒有選股智慧

**日期**：2026-11-25

**Context**:
為了回答「我為什麼挑這些股票」，讀引擎與帳本時發現兩個**先前沒有被記錄**的結構事實。
兩者都用資料驗證過，不是讀碼推測。

**F1：進場選擇＝代號升序（已驗證，32 個有買進的交易日零例外）**
- `src/ai_ledger.py` 的進場迴圈註解寫「the published long picks, **in published order**」，
  而進場池是 `market_screen_picks ORDER BY run_id, ticker, id` → 同一輪內即**代號升序**。
- 驗證：32 個有買進的交易日，買進的每一檔都是當日 long 清單裡的**代號較小者**，
  且買進順序與代號升序一致，**違例 0 次**。
- 實例：11-24 的 long 清單是 `[1303, 2330, 2357, 2395, 2454, 2618, 2880, 2881, ...]`，
  帳本持有的是前五檔；第 6 檔 2618 長榮航**從未被買過**。
- 後果：**排序依據＝代號，完全不含任何論點**。`score`、`excess_return_240d`、
  `excess_return_60d` 這些欄位帳本從未用來排序。
  → 隱性偏誤：系統性偏好低代號（低價股、排除 2880／2881／2882／2886 等金融股），
  並且永遠排在大盤權值與強勢股之外。

**F2：部位 sizing 固定 equity÷6，第 6 檔常常補不進（已驗證）**
- 進場金額＝`equity_value / 6`，**不看當日剩多少現金**；現金不足時每個候選被 `continue` 掉。
- 驗證：56 個交易日中有 **32 天（57%）**部位數 < 6；這些日子現金／權益平均 **13.1%**（最高 16.0%）；
  整體平均閒置現金 7.8%。最近 5 個交易日閒置 12–16%，第 6 檔從 11-20 起就沒補進去。
- 實例：11-24 equity = 828,129 → 每檔預算 138,021，但現金只有 115,825 → 每一個候選都跳過，
  包括本輪唯一 e60 為正（+15.7%）且有「買點候選：二買」的 2618 長榮航。

**Decision**:
1. **把 F1、F2 列為最高優先的兩個變因，並排在 H1／H2／H3 之前**：
   - **H0**：進場排序改成有論點的排序（候選：`score` 降冪、`e240` 降冪、
     或「e240 > 0 且 e60 < 0」的均值回歸條件優先），其餘規則固定。
     → 直接決定「買哪 6 檔」，是唯一可能把 `no_edge` 翻正的單一變因。
   - **H0b**：部位 sizing 讓 6 檔投滿（消除 13–16% 閒置現金；例如新進場金額取
     `min(equity/6, 可用現金 ÷ 剩餘空缺數)`）。
2. **H0b 不預設會更好**：多投＝多曝險，在空跌段可能更差，必須實測。這是量測，不是修 bug。
3. **先量 H0，再量 H0b，其餘保持 AIV1**——每次只動一個變因。
4. **F1／F2 必須寫進 AI 帳頁面**：頁面目前印著「同時最多 6 檔、等權」，
   但實務上 57% 的交易日只有 5 檔、且有 13–16% 閒置現金、選股依據是代號順序。
   → 誠實揭露優先：頁面要寫明「目前選股順序＝代號升序（無論點排序）」與實際持股天數分布，
   以及「有 10–16% 資金常駐現金」。這是揭露，不是辯護。
5. 實作歸屬：`src/ai_ledger.py` 的修改由接手的新對話獨占（避免兩個寫者同檔），
   本筆決策只寫在 docs（docs/ 不在認證雜湊白名單，改它不影響當前 marker）。

**Why**:
- 一個要拿來付費的帳戶，必須先知道自己真正的選股機制是什麼。
  目前的答案是「代號」——這不是策略，是預設值。
- 兩個發現都直接影響「能不能活著付費」：H0 決定選誰，H0b 決定有多少錢其實在場外閒置。

**驗證**:
- `scripts/_debug/_verify_entry_selection.py`（唯讀）：F1 32/32 一致、違例 0；
  F2 32/56 天 < 6 檔、閒置現金平均 13.1%。

## D032: 執行前提定案——300 萬本金、只做整股、live 維持 AIV1；並新增「可執行宇宙」這個變因

**日期**：2026-11-25

**Context**:
AI 帳存活掃描（第一輪，14 個變體）回報後，發現一個必須先解決的前提問題：
帳本的部位大小是 `equity/6`，而 `shares = int(budget/price)` → **交易零股**。
一個要照單用真錢下單的帳戶，必須先確定執行前提，否則回溯結論在實務上不成立。

**Decision**:
1. **實際下單本金：300 萬左右**（Walter 決定）。
2. **執行：只做整股**（不用零股）。理由（證交所／金管會官方說明）：
   - 盤中零股可交易（1～999 股、9:00–13:30、限價 ROD、僅電子單），但
     **零股成交價不作為開盤／收盤價**，且盤中零股無收盤集合競賣可成交
     → **「照收盤價成交」在零股做不到**，R1 只有整股才成立。
   - 零股不得融資融券／借券賣出。
   - 零股最低手續費 20 元門檻（成交 2,000 元時實際費率換算約 1%，為標準 0.1425% 的 7～14 倍）
     → 模型用 `max(amount×0.1425%, 20)` **已正確涵蓋**，不需改。
3. **live 段維持 AIV1 不動**（2026-11-25 起的前瞻母體必須乾淨，不能被 in-sample 選模污染）；
   **AIV2 以影子帳（shadow track）並行記錄**，等 live 滿 20 個交易日再由 Walter 決定是否切換。
4. **AIV2 規則分層**：策略層（R1～R9 的選股與進出）與執行層（E1 本金 300 萬｜E2 只做整股、每檔 1 張
   ｜E3 每檔預算上限 50 萬 → 1 張買得起 ⇔ 單價 ≤ 500 元｜E4 部位數 ≤ 6｜E5 權重由股價決定）分開。
   - **「等權」在整股下不成立**（1 張市值 = 1000 × 股價）→ R3 規則文字必須改寫，
     否則頁面在講一件做不到的事。
   - **初始本金 100 萬 → 300 萬**：會改變整股取整與手續費最低 20 元門檻的結果
     → 所有變體必須在 300 萬下重跑，100 萬下的那 14 個數字只能當策略層參考。

**並記錄三個已量測的執行約束事實**（`scripts/_debug/_execution_feasibility.py`，唯讀，56 個 session 全算）：

| 項目 | 結果 |
|---|---|
| 部位預算 | 本金/6 = 50 萬 → **1 張買得起 ⇔ 單價 ≤ 500 元** |
| 每 session 可買 long 檔數 | min 6／median 7／max 8 → **56/56 個 session 都湊得滿 6 檔**（部位不會開天窗） |
| 可買宇宙 | 金融＋低價傳產：2880 華南金、2881 富邦金、2882 國泰金、2886 兆豐金、2891 中信金、2892 第一金、6505 台塑化、1303 南亞、2412 中華電、2618 長榮航、9933 中鼎 |
| 被排除 | **半導體與電子大盤全滅**：2330、2357、2395、2454、3443 創意、3711 日月光投控（1 張 > 50 萬） |
| **H3 的 MR 條件 ∩ 可買宇宙** | median 0、max 4；**56 個 session 有 39 個（70%）是空集** |
| 6 檔最便宜可買 × 1 張的實際投入 | 平均 **752,726 元 ＝ 本金 25%**，閒置現金 **75%** |

**兩個決定性推論**：
1. **H3（唯一在回溯中把絕對報酬翻正的變體）與執行約束互斥**：
   在 Walter 實際能買的宇宙裡，70% 的交易日開不出部位。
2. **25% 曝險在空頭母體裡必然顯示正報酬** → 那是曝險效果，不是選股 edge。
   → 因此對照組改為**曝險配對**：掃 25%／50%／75%／100% 四個曝險級距，
   每級距與**同曝險率**的等權市場比較；只有在所有級距超額都為正才算選股有鑑別力。
   → 量測母體改為 **execution-feasible universe**，且**先濾可買性、再套策略排序**
   （先排序後跳過買不起的會讓結果被股價隱形扭曲成另一個規則）。

**Why**:
- 一個要拿來付費的帳戶，必須先知道自己真的買得起、買得到什麼價位。
- 「絕對報酬為正」在 25% 曝險的空頭母體裡是必然的，不是證據；
  把曝險與選股混在一起談 edge，會得到一個錯的答案。

**驗證**:
- `scripts/_debug/_execution_feasibility.py`（唯讀，可重跑）
- `scripts/_debug/_verify_entry_selection.py`（F1／F2）

## D033: 目標改為最大化獲利、基準改為存款利息；Walter 全權授權重建歷史訊號與重訓 ML

**日期**：2026-11-25

**Context**:
Walter 指出關鍵事實：**300 萬放存款，利息就能付 MiniMax 費用**，
所以 AI 帳不必自給自足，唯一目標是最大化獲利，且「unlimited using minimax」。
這一次發言同時改變了**基準**、**風險邊界**與**授權範圍**三件事。

**Decision**:
1. **基準改為存款利息**（2026-11-25 牌告：央行牌告存放款利率／五大銀行平均／富邦牌告）：
   - 五大銀行平均一年期定存 **1.70%**（資料日 115-11-20）
   - 台北富邦一年期定儲：固定 **1.675%**／機動 **1.715%**（更新日期 2026/11/25）
   - 全台 41 家牌告一年期定儲區間 **1.32%～1.81%**
   → **300 萬的存款基準 ≈ 年化 1.7% ≈ 51,000 元/年 ≈ 4,250 元/月**。
   帳本新增報告欄：**超額 vs 存款（net − 1.7%）**。**判定線 R9 不動**。
2. **風險邊界從「生存限制」變成「風險偏好選擇」**：MDD 25% 與 −12% 停損不再由付費能力決定
   → 新增掃描軸（停損 −8%／−12%／−20%／無；MDD 容忍 10%／25%／40%／不設），
   以「**獲利 vs 回撤前沿曲線**」呈現，由 Walter 選曝險與風險偏好。
3. **全權授權（2026-11-25）**：
   - **授權重建 2020–2026 全部歷史的市場螢幕精選訊號**；
   - **全面授權**：含重訓 ML 權重、commission 新策略、選股模型改造；
   - → **9/30 handover 邊界（未經授權不重訓／不 commission／不重建過去訊號）就此解除**，
     依據＝Walter 2026-11-25 的明確授權。
   - 維持不變：本金 300 萬、只做整股、live 段維持 AIV1、AIV2 影子並跑。
4. **重建必須先過驗收閘門才可用**：
   - **G1 重現檢查**（決定性）：用同一套程式重建 2026-08-12→11-24 這 56 天，
     與資料庫既有 `market_screen_picks` 逐日逐檔比對（名單／horizon／score／e60／e240／rationale）。
     **重現不出來就停，不要往上蓋。**
   - G2 無前視檢查（截斷資料重跑，輸出須一致）
   - G3 存續偏誤揭露（`daily_data2_full` 只含現存標的）
   - G4 不擾動現況（2026-11-24 那輪須仍是唯一 active 集合）
   - G5 成本實測（單日耗時 × 全期時數，背景批次跑）
5. **更正：「AI-Telegram 管線 45 天空轉」講過頭了**（實測推翻）：
   - `model_predictions_daily` 最新寫入 **2026-11-24 22:24**（56,356 列）→ 主預測新鮮
   - 11/24 整條鏈跑到 23:02（strategy_adjustment 22:37／telegram_delivery 22:52／night_markets 22:42）
   - owner 心跳 11-25 17:15 仍更新；watchdog 排程 lastResult=0；其他 4 支任務 lastResult=0
   - 真正卡住的是**主排程實例**（state=Running、lastResult 0x800710E0＝排程拒絕啟動第二個實例）。
     `output/pipeline_state/scheduler.lock` 被 PID 2976 握著（mtime 10/09 13:52、檔案被鎖連讀都讀不到）；
     該 PID 為 Session 0 的 python.exe、建立於 2026-10-09 13:52:21（與鎖 mtime 相差 1 秒）、
     父行程 40864 已不存在（孤兒）。**其命令列因 Session 0 權限無法讀取**。
   - ⚠️ **不要殺 PID 2976**（2026-11-25 複驗後修正）：owner 心跳每輪仍在更新
     （17:25、17:28 實測）、watchdog lastResult=0；且「CPU 0 秒」是**讀不到屬性**而非真的 0。
     → PID 2976 **很可能就是自 10/09 起持續在跑、握著鎖的 owner 本體**，
     殺掉會直接弄壞 AI-Telegram 的每日 stage。
     「排程註冊顯示 0x800710E0」其實是**鎖在正常運作**（擋住第二個 scheduler 實例），
     不是故障。每日 stage 由各獨立排程（`tw-invest-suite-finmind-download`、
     `AI-Telegram Daily Report 22-47` 等）與 owner 迴圈分擔，不依賴該鎖。
   - 另有四張**輔助／舊表**停止寫入：`daily2_prediction_bands_daily`（08-01）、
     `prediction_eval_daily`（07-06）、`skis_aigo_prediction_latest`（07-10）、
     `moonread_predictions_v1`（01-04）→ 屬既有資料債，不是管線死掉
   → **模型端是活的，AI 帳的選股來源不是死的。**要提升選股品質該改選股／排序規則，
     不是去救管線。
6. **新變因軸：ML 因子**。`model_predictions_daily`／`xg_predictions_daily`（860,212 列）
   **從未被 AI 帳用過**；現有授權下可作為進場因子，但必須先實查其最早資料日，
   否則含 ML 因子的規則只能用短樣本 → 與長樣本不可比，必須分開報。

**Why**:
- 基準錯了，目標就錯了。拿「自給自足」當目標會把策略推向防守；
  真正的基準是存款 1.7%，而策略要做的是在承擔風險的前提下一步把它贏過去。
- 只有空頭 regime 的樣本無法支撐「最大化獲利」的宣稱 → 全歷史重建是必要的，不是奢侈的。

**驗證**:
- 唯讀腳本：`scripts/_debug/_execution_feasibility.py`、`_verify_entry_selection.py`、
  `_check_model_freshness2.py`
- 存款利率來源：中央銀行「牌告存放款利率異動資訊」（1151120）、
  央行「五大銀行平利率」（資料日 115 年 11 月 20 日）、台北富邦 ebank 存款利率牌告（2026/11/25）

## D034: 基準口徑修正——等權日報酬鏈接 ＋ 母體濾掉 0 收盤列（BENCH-v2）

**日期**：2026-11-26（**當天 10:45 改寫过一次**：第一版把「市場實際跌 −48%」當成結論，是錯的，
下面這版是複驗後的正確版本，錯誤原因見 §D034 勘誤）

**Context**:
`src/ai_ledger.py` 的 `benchmark_curve()` 原本算的是**收盤「價格水位」平均**
（`level = mean(all Close)` 再除以首日）→ 不是報酬序列：不合成、不除權、不等再平衡，高價股主導。
另外 `load_closes()` 沒有濾 `Close=0`，而 `daily_data2_full` 保留停牌／下市名稱的 0 收盤列
（2026-08-01～11-30 共 **1,749 列、76 個交易日**，每天 7～35 列）→ 在等權日報酬鏈接裡，
每一列 0 收盤都是 **−100% 的一天**，每天把等權平均拉低 1～3pp。
第三個錯：live 段基準重新歸一 → live 第一天基準恆為 0，市場當天跌多少整個漏掉。

**實測（57 個交易日母體，2026-08-12→11-25）**：

| | 含 0 收盤（舊母體） | 乾淨母體（Close>0，BENCH-v2） |
|---|---|---|
| 市場報酬（56 session，08-12→11-24） | −45.24% | **−13.85%** |
| 市場報酬（57 session，含 live 11-25） | −48.49% | **−17.76%** |
| 帳本 net | −22.21% | −22.21%（不變） |
| **帳本超額** | +7.40pp | **−4.45pp** |
| live 第 1 天超額 | −6.06pp | **−1.43pp**（帳戶 −6.06%、市場 −4.63%） |

**Decision**:
1. **基準口徑改為等權日報酬鏈接**（BENCH-v2）：每個 session 取「當日所有有前收的標的之報酬均值」再逐日複利；
   母體＝與選股同一個篩選後 universe（`Close>0`、4 位數代號）。
2. **live 段承接回溯段的 base**，不可在 live 段重新歸一。
3. **基準算不出來時用 `None`／unknown，絕不可用 0 代替**（0 會被誤讀成「今天市場沒動」）。
4. **保留 `benchmark_curve_level_legacy()`**，頁面同時顯示舊口徑與新口徑
   → 不假裝數字一直以來就是對的。舊的 `+8.86pp` 一律不得再引用。
5. **`rolling()` 修正**：舊版拿「帳戶 20 日報酬」去比「市場**自成立以來**的累計報酬」→ 判定線遠比 R9 嚴格；
   改成同一窗口兩邊都量，並**真的**納入 R9 印在頁面上的 MDD<25%（舊版根本沒檢查）。
   量完 MDD 條款是**非綁住**（六種組合裡「只因 MDD 而不通過」的窗口數都是 0）。
6. **危險名單頁不需要重算**：`src/danger_track.py:111-113` 的籃子與市場本來就用日報酬，沒有價格水位問題
   → **未修改** `src/danger_signals.py`／`src/danger_track.py`。
7. **量測修正，不是策略改動**：超額變差，**絕對報酬不變**。
   → AIV1：net −22.21%、**超額 −4.45pp**、MDD −33.63%、滾動 5/38 → **輸給市場也輸給存款**。
   → 只有 H3（MR 進場）有正的曝險配對超額（+9.83pp），但只有 31 筆買進、曝險 53.5%、
     且在 300 萬整股的可執行宇宙裡沒有 edge（28/57 天無部位、平均 0.95 檔、曝險 14.2%）。
   → 36 格執行網格（本金 × 槽位 × 每檔張數）**沒有任何一格是正的**。

**Why**:
- 一個要拿來付費的帳戶，基準算錯就等於把成績單算錯。而這次的錯誤方向是**讓帳戶看起來比實際好**
  （舊口徑說市場跌 30%、新口徑說跌 18%）→ 更需要立刻修正。
- 同時把「輸給市場」這件事如實寫出來：目前 AIV1 的 +7.40pp 是幻覺，真實是 **−4.45pp**。

**D034 勘誤（第一版錯在哪）**：
第一版 D034 主張「市場實際跌 −48.49%、帳本真實超額 +26.29pp」。
那個 −48.49% 是**我自己寫的驗算腳本把 0 收盤列算成 −100% 的一天**造成的汙染，
且我把同一個汙染造成的「每月都跌」當成 regime 事實。
→ 由接手的新對話獨立驗證三種演算法後推翻；我另以獨立腳本複算確認
（`scripts/_debug/_bench_contamination_check.py`：0 收盤列 1,749／76 天；
乾淨母體 56 session −13.85%、57 session −17.83%；月度乾淨：08 +5.82%、09 +1.56%、
10 −4.40%、11 −16.73%）。**方向完全相反：真實超額是負的，不是 +26pp。**

**驗證**:
- `scripts/_debug/_benchmark_method_check.py`、`scripts/_debug/_bench_contamination_check.py`（皆唯讀）
- 修正 commit `d72831baa`（已 push）；改了 hashed 檔 → 當前 marker 的 source SHA 失配，
  需下一輪 nightly 重新認證才生效；`scripts/_debug/_sync_runtime.py` 已跑、76 個雜湊 OK

## D035: 勘誤——D029／D031／D033 裡被 D034 推翻的結論

**日期**：2026-11-26

**Context**:
D034 把基準口徑修正之後，先前幾條決策裡引用舊口徑數字的敘述就不再成立。
這裡集中列出被推翻的部分，**供後續引用時直接以本條為準**。

**被推翻的敘述**：

1. **D029**：「加上這套出場規則後，帳戶從模型的 −2~3pp 變成 **+8.86pp** → edge 來自出場紀律」
   → **作廢**。+8.86pp 是舊基準（價格水位平均）造出來的數字。
   → 修正後（BENCH-v2）：AIV1 的真實超額是 **−4.45pp**（帳本 net −22.21%、市場 −17.76%），
     **帳本輸給市場**。原結論「edge 來自出場紀律」**尚未被證明**。

2. **D029／D031**：「模型原始 ADD 5 日 −2.13pp／10 日 −3.31pp」
   → 這兩個數字來自模型訊號層的**絕對**報酬差，**不依賴基準口徑**，仍成立。
   → 但「因此 edge 來自出場紀律」的推論已作廢（見上一點）。

3. **D033**：「樣本只有單一空頭 regime（2026-08-12 起，每個月都跌，11 月日均 −1.49%）」
   → **作廢**。那是 0 收盤汙染造成的。乾淨等權月度報酬為
     **2026-08 +5.82%｜09 +1.56%｜10 −4.40%｜11 −16.73%** → 樣本**含兩個上漲月**，
     不是單一 regime（但仍屬同一個「先漲後加速跌」的下半年區間，regime 多樣性仍不足）。

4. **D031**：F1（進場選擇＝代號升序）、F2（sizing 讓第 6 檔補不進）
   → **不受影響，仍然成立**（那是帳本行為，與基準無關）。

5. **D032**：「H3 與 Walter 的執行約束互斥（70% 交易日無部位）」
   → **仍成立**，且 BENCH-v2 下更明確：H3′ 在可買宇宙的曝險配對超額 **≈ 0**。

6. **D033 授權段**（重建全部歷史、全面授權、9/30 邊界解除、基準＝存款 1.7%）
   → **全部仍然有效**。

**Decision**:
- 後續任何引用「超額」的地方，一律用 BENCH-v2 口徑；舊口徑只能以「舊口徑」並列顯示。
- **絕對報酬與 MDD 是基準無關的**，任何時候以它們為準（net −22.21%、MDD −33.63%）。
- 「帳本能否贏過存款 1.7%」目前答案是 **不能**（H3 的 +0.16%／57 日 → 年化約 +0.7%，
  仍低於 1.7%；且 36 格執行網格無正格）。
- 多 regime 的答案只能由歷史重建（Phase 1）給出 → 仍是接下來的主線。

**驗證**: `docs/RESP-2026-11-25-02-ai-ledger-survival-sweep.md`、`docs/RESP-2026-11-25-03-historical-rebuild.md`

## D036: 執行前提再定案——允許零股（維持 300 萬）＋ 風險偏好放寬（MDD 40%／停損 −20%）

**日期**：2026-11-26

**Context**:
D034 修正基準後的真實結果（57 個交易日、BENCH-v2）：
- AIV1：net **−22.21%**、超額 **−4.45pp**、MDD −33.63%、滾動 5/38 → **輸給市場，也輸給存款 1.7%**
- 只有 H3（MR 進場）有正的曝險配對超額（+9.83pp），但只有 31 筆買進、曝險 53.5%，
  且**在「300 萬＋只做整股」的可執行宇宙裡沒有 edge**（28/57 天無部位、平均 0.95 檔、曝險 14.2%）
- 36 格執行網格（本金 × 槽位 × 每檔張數）**沒有任何一格是正的**
- 問題的根源：策略看起來有 edge 的標的（2330／2357／2395／2454／3443／3711）**一張要 59～405 萬**，
  300 萬的整股限制把它們整個擋在門外 → 只剩金融與低價傳產可交易，而那裡沒有 edge。

**Decision**（Walter 2026-11-26）：
1. **執行前提：允許零股，本金維持 300 萬**（推翻 2026-11-25 的「只做整股」）。
   - 每檔 50 萬部位預算在零股下可買到任何價位：2330 @2230 → 224 股｜2454 @4050 → 123 股｜
     2357 @821 → 609 股｜2395 @589 → 848 股｜1303 @249 → 2007 股｜3443 @5630 → 88 股｜
     3711 @530 → 943 股 → **H3 的候選全部買得起**。
   - 「等權」重新成立（整股時權重由股價決定，零股時回到 equity/N）→ **E5 改回等權**。
2. **風險偏好：寬鬆**——MDD 容忍 **40%**、停損 **−20%**（原 25%／−12%）。
   - 這是 **R9 的規則版本變更（AIV2）**，不是事後放寬判定線。三條護欄：
     ① AIV1 與 AIV2 的判定必須**並列報**；② kill switch 期數（3 期）與其他條款不變；
     ③ **live 段不可回溯套用**——live 每一天用當日生效的版本判定，並標出切換日。
3. **R1 的成交假設必須版本化**（零股沒有收盤集合競賣）：
   - `FILL-CLOSE`（現況，決策在收盤後、以當日收盤價成交）→ **只有整股做得到**，列為參考口徑
   - `FILL-NEXT-OPEN`（決策在收盤後、次一交易日開盤價成交）→ 整股與零股都做得到
   → **最終規則的定案必須以 `FILL-NEXT-OPEN` 為準**；不得拿一個做不到的模型去賺錢。
4. 零股的實務限制要寫進頁面（證交所／金管會官方）：
   交易單位 1～999 股、申報 9:00–13:30、僅限價 ROD、僅電子單、
   **不得融資融券與借券賣出**（帳戶不能加槓桿）、**零股成交價不作為開盤／收盤價**、
   單筆最低手續費 20 元（成交 2,000 元時實際費率換算約 1%，遠高於 0.1425%）。
5. 新增掃描軸：**部位數 N（6／8／10／12）**（零股下每檔 equity/N 仍買得起）、
   與**成交模型**（CLOSE／NEXT-OPEN）的交叉表。

**Why**:
- 「最大化獲利」的實際瓶頸不是規則，是**買不到標的**。零股把整個宇宙打開，
  也讓「H3 與執行約束互斥」這條結論有機會被推翻——這是本輪最該先量的東西。
- 同時必須承認：放寬 MDD 與停損會讓回撤更深。edge 尚未被多 regime 驗證之前，
  這等於用更寬的閘門跑一個還沒證實會贏的策略 → 所以必須把 AIV1 判定並列保留。

**驗證**:
- 執行與成交模型的數字由接手的新對話以參數化掃描產出
  （`scripts/_debug/`，gitignored），報告見 `docs/RESP-2026-11-25-02-ai-ledger-survival-sweep.md`

## D037: AIV2 的停損由 −20% 改回 −12%——量測說「寬鬆」那一半是壞的

**日期**：2026-11-26

**Context**:
Walter 2026-11-26 選了「寬鬆：MDD 容忍 40%／停損 −20%」（見 D036）。
在**規則日曆修正後的 70 個交易日母體**（2026-08-12→11-25、市場 −17.76%、同期存款 +0.469%）上重測後，
這組選擇的兩個成分表現完全不同：

1. **MDD 容忍軸完全不 binding**：10%／25%／40% 三個門檻在同一 stop／成交組合下，
   滾動通過窗口數**完全相同** → 「寬鬆」的 MDD 那一半**沒有代價也沒有好處**，
   它唯一的實質作用是「不讓 25% 那條把好曲線擋掉」。
2. **停損軸四格中三格是 −12% 最好**（唯一例外見下表第 4 列，2026-11-26 由量測單位回報更正）：

| 進場池 | 參數 | 停損 −8% | **停損 −12%** | 停損 −20% | 無停損 |
|---|---|---|---|---|---|
| H3 | AIV2（零股／NEXT-OPEN） | 年化 +11.40% | **年化 +30.83%**（超額 +25.51pp、滾動 36/51） | 年化 +25.98%（+24.38pp、33/51） | 年化 +7.29% |
| H3 | AIV1（CLOSE） | −17.45% | **−3.97%**（+16.64pp、32/51） | −12.06% | −12.06% |
| AIV1 | AIV2（零股／NEXT-OPEN） | −59.33% | **−55.51%**（−2.39pp、16/51） | −58.20% | −56.58% |
| AIV1 | AIV1（CLOSE） | −61.75% | −56.07%（−2.67pp、17/51） | **−54.88%（本格是 −20% 較好）** | −57.04% |

→ **停損 −20% 在四格中的三格比 −12% 差**；唯一例外是「live 進場池 ＋ FILL-CLOSE（live 條款）」那一格，
  −20% 好 **0.59pp 淨報酬**（−19.83% vs −20.42%、曝險配對 −3.20pp vs −3.78pp）。
→ **所以定案的依據不是「四格全勝」，而是「live 帳戶實際要跑的是 AIV2 條款，那兩個組合都指向 −12%」**
  （H3＋AIV2：年化 +30.83% vs +25.98%；live 池＋AIV2：−55.51% vs −58.20%）。

**Decision**:
1. **AIV2 的 `stop_loss` 由 −20% 改回 −12%**（= AIV1／R9 原本預登記的預設值）。
   **這不是放寬判定線，是回到預設值**：Walter 選的 −20% 是「放寬」，而放寬在每一格都比較差。
2. **MDD 容忍維持 40%**：它不 binding，且能避免 25% 那條在多 regime 母體上誤擋好曲線。
3. 記錄事實：Walter 2026-11-26 曾明確選「寬鬆（MDD 40%／停損 −20%）」，本條依量測結果修正其中一半。
4. **誠實限制**：以上全部 in-sample、單一空頭母體 → 多 regime 驗證仍待歷史重建完成（2020-01-02 起）。

**另記一項對「照單下單」影響很大的事實：kill switch 實作後，live 帳戶自 2026-09-16 起即停止進場。**
- 實測：kill switch 開啟時 live 段第一天的淨報酬是 **0.00%**（不是賺到，是**沒有下單**），
  同期市場 −4.63% → 表面超額 +4.63pp 全部來自「空倉」。
- AIV1 進場池 + AIV2 + never 模式：70 天裡有 **45 天**停止進場；H3 影子帳：15～17 天。
- → **頁面必須寫明**：「live 帳戶目前處於 kill switch 停止進場狀態，live 段第一天的 0.00% 是『沒有下單』，
  不是策略賺到。」這是 Walter 照單下單前必須知道的事。
- → **live 帳戶的計數器承繼回溯期**（帳戶層級的規則語意：這個帳戶已連續失敗，就不該再開新倉）；
  **影子帳（H3）改用全新計數器**（研究軌，不承繼回溯期的失敗計數），以維持前瞻測量的乾淨。

**驗證**:
- `scripts/_debug/_ledger_round10.json`（唯讀，70 天引擎：kill switch 12 組、停損軸 16 格、live 12 組）
- `scripts/_debug/_ledger_round10.py`、`_ledger_round10_verify.py`

## D038: 現行數字定稿（70 天母體）＋三個新發現

**日期**：2026-11-26

**Context**:
kill switch 實作、停損改回 −12%、影子帳計數器改為 live 段重算之後，先前報過的數字全部失效
（例如 H3 的 +51.51% 年化、AIV2 live 池的 +12.46% 年化，都是決策前的口徑）。
以下是**目前唯一有效**的一組。母體：**70 個交易日**（2026-08-12→11-25，其中 57 天有發佈精選）、
市場 −17.76%、同期存款 +0.469%、300 萬、零股、N=6、停損 −12%、MDD 容忍 40%。

| 進場池 | 條款 | kill | 淨 | 年化 | 曝險配對 | 曝險 | 交易 | 停止進場 |
|---|---|---|---|---|---|---|---|---|
| live 池（代號升序） | AIV2 | off | −20.15% | −58.20% | −4.90pp | 85.4% | 83 | 0 |
| live 池 | AIV2 | resume | −12.47% | −38.36% | −1.50pp | 60.8% | 56 | 29 |
| live 池 | AIV2 | never | −0.33% | −1.18% | +5.90pp | 34.2% | 26 | 45 |
| H3 池（影子帳） | AIV2 | off | **+7.75%** | **+25.98%** | **+17.70pp** | 55.0% | 47 | 0 |
| H3 池 | AIV2 | counter | **+11.05%** | **+45.84%** | **+18.11pp** | 38.8% | 26 | 15 |

**三個新發現**：
1. **「達線就恢復」在這段樣本裡一次都沒生效過**：live 池的 resume 與 never 結果**完全相同**
   （−12.47% vs −12.47%、停止天數 29 vs 25）→ 觸發後的滾動視窗再也沒有回到達線。
   → **kill switch 的實際效果等同於「連續失敗就停手、直到樣本結束」。** 這是規則語意的關鍵限制，
   不是 bug，但必須寫在頁面上（否則讀者會以為它能自動恢復）。
2. **H3 輸給存款是成本造成的**（FILL-CLOSE 條款下）：H3 淨 −2.16%、手續費＋稅 2.90%、
   去掉成本 **+1.41%（年化 +5.17%，贏過存款 1.7%）**；但**曝險配對超額反而從 +15.59pp 降到 +12.49pp**
   → **成本不是唯一解釋，去掉成本後相對表現反而變差** → 成本是淨報酬的拖累，但 edge 也薄。
3. **130% 出場規則在 70 天母體用正式引擎重測**（舊數字走的是草稿模擬器＋57 天母體，**作廢**）：
   AIV1 有規則 −20.37% → 無規則 −21.28%（**+0.91pp**，規則對 live 進場池有幫助）；
   H3 有規則 −2.16% → 無規則 −1.84%（**−0.32pp**，規則對 H3 是負的）
   → **長樣本只能驗證「無 130% 規則」的版本，而那一版對 H3 反而略好** → 這點要寫進 doc 03。

**Decision**:
1. 上表為目前唯一有效的一組數字；doc 02 §0 已改用新值，舊值標示作廢並註明出處。
2. **多 regime 掃描的判準不變**（kill switch 與 H3 若只在空頭 regime 有效 → 不是 edge，是市場時機），
   並新增一條必測項：**H3 的超額究竟來自 240 日動能（e240>0）還是 60 日超跌（e60<0）**
   → 在多 regime 母體上分別量 `e240>0 only` 與 `e60<0 only`，再與 H3（兩者並取）比。
3. 頁面必寫三件事：(a) 進場規則 32 格全負、H3 在影子帳不下單；
   (b) kill switch 開啟時 live 帳戶自 2026-09-16 起停止進場、live 首日 0.00% 是「沒有下單」；
   (c) **「達線就恢復」在樣本中從未發生**。

**驗證**:
- `scripts/_debug/_ledger_round10.json`（70 天引擎：kill switch 12 組、停損軸 16 格、live 12 組）
- `docs/RESP-2026-11-25-02-ai-ledger-survival-sweep.md`（母體速查表＋逐表標註）
- `docs/RESP-2026-11-25-03-historical-rebuild.md`

## D039: H3 的本質是「短期弱過濾」、隨機對照組方法修正、重建 ETA 更正

**日期**：2026-11-26

**Context**:
第十一輪續回報量出三件事，其中前兩件會改變後續**所有**多 regime 掃描的設計。

**Decision / 發現**:
1. **H3 ≡「只取 e60 < 0」**（長期強那一半在此母體是廢話）
   - 已發佈精選 long 的 **684 個 pick-days** 中：e240>0 且 e60<0 ＝ 147（21.5%）；
     **e60<0 且 e240≤0 ＝ 0（0.0%）** → **每一個 e60<0 的精選都同時 e240>0**。
   - → H3 與「只取 e60<0」的交易**逐欄完全相同**（26 筆買進、14 檔、曝險 55.0%、曝險配對 +17.70pp）。
   - 三個過濾器分解（70 天母體、同一基準）：

| 過濾器 | 每日期望筆數 | AIV2 淨 | AIV2 vs 配對 | live 條款淨 | live 條款 vs 配對 |
|---|---|---|---|---|---|
| H3 ＝ e240>0 且 e60<0 | 4.49 | +7.75% | **+17.70pp** | −1.12% | **+9.33pp** |
| 只取 e60<0 | 4.49 | +7.75% | +17.70pp | −1.12% | +9.33pp（與 H3 逐欄相同） |
| **只取 e240>0** | 21.32 | **−19.26%** | **−4.12pp** | −20.45% | −4.13pp（**無 edge**） |
| 動能 e240>0 且 e60>0 | 16.68 | **−35.35%** | **−20.39pp** | −30.00% | −14.17pp（與 H3 差 38pp，是它的反面） |

   → **有效的那一半是短期弱（e60<0），方向是均值回歸，不是 240 日動能。**
   → 若未來要把 H3 升級成 live 進場規則，**規則文字應寫成單一條件 `e60 < 0`**
     （自由度更低、更好驗證、與量測一致）；但多 regime 掃描仍要**同時報** `e60<0 only`
     與 `e240>0 且 e60<0`——若兩者在某些 regime 分歧，那個分歧本身就是資訊
     （代表長期動能過濾只在某些 regime 才有效）。
2. **隨機對照組的方法錯誤（重要，會系統性影響結論）**
   - 第九輪的對照組是「只打亂同一天的順序、不改被選到的名單」。
     對 live 進場規則（每天約 21 檔 long、引擎取前 6）是**正確**對照；
     對 **H3（過濾後每天剩 4.49 檔、部位名額 6 檔）則是無效對照**：
     池子比名額小 → 順序幾乎不影響結果 → **對照組會重現 H3 自己**
     （實測：錯的對照跑出 H3 中位 +6.49%，規則本身 +7.75%）。
   - **正確對照＝每天挑到同樣數量的隨機檔（同一已發佈 universe 內）、20 seeds**：

| 規則 | 規則本身 | 同數量對照（中位） | 對照最好的一個 seed |
|---|---|---|---|
| H3／AIV2 | +7.75%／**+17.70pp** | −6.56%／+0.93pp | +3.75%／+11.34pp → **規則贏過全部 20 個 seed** |
| H3／live 條款 | −1.12%／**+9.33pp** | −16.18%／−7.21pp | −7.98%／+0.95pp → 同樣全勝 |
| 只取 e240>0／AIV2 | −19.26%／−4.12pp | −20.38%／−4.95pp | → **與隨機無異**（再次確認無 edge） |

   → **多 regime 掃描一律用「同數量」對照組**，否則每個 regime 都會重現「對照組＝規則自己」的假象。
3. **重建 ETA 更正**：269／1,598（16.8%）、實測 2.26 檔／分鐘 → 剩 1,329 檔 ≈ 9.8 小時 → **約今晚 23:00**；
   原報「明早 08:00」是低估速率。**但 2020 段（單日 28～53 秒）只佔四分之一的工作量，
   2021 年後單日要 149～163 秒 → 實際收工會更晚，落在明天凌晨至上午。**

**Why**:
- 「長期強＋短期弱」是我們自己在敘事裡美化一個**其實只有單一條件**的規則 → 頁面與文件必須照實寫。
- 對照組方法錯誤會系統性地讓規則無法被公平比較（在 H3 這個案例反而讓它看起來比較差，但方向不可靠）。

**驗證**:
- `docs/RESP-2026-11-25-02-ai-ledger-survival-sweep.md` §6.5.1（拆解＋對照組方法修正）、§9 結論 2
  （commit `19389f5a1`，**僅 docs/**，src/ 未動 → 今晚 nightly 的認證面不變）
- 新腳本與結果只放在 session workspace（`_h3_decomposition.py`、`_h3_control.py` 及其 json），未寫進 repo 的 scripts/
