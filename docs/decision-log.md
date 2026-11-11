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

