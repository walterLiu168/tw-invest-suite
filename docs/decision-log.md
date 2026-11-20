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
