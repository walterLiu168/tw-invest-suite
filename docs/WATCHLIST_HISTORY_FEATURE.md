# 選股清單歷史回看（watchlist history）

**日期**：2026-11-16
**需求**：「我要能自己回查 watchlist 每一檔的歷史」

---

## 1. 為什麼需要

每日精選清單只有 24 檔，而且每晚整份換掉。任何一張網頁截圖都只能回答
「現在榜上有哪些」，永遠回答不了：

- 這檔上次進榜是什麼時候？
- 進榜那天我們的理由是什麼？
- 進榜之後賺了還是賠了？
- 離榜之後又跌了多少？

既有產物其實都有答案，只是散在不同地方：`market_screen_picks` 保留了每次入選的
`score`、`rationale`、`bucket`、`horizon`、`close_at_pick`；`daily_data2_full` 有正規收盤價；
`public/watchlist-full-YYYY-MM-DD.html` 有每日整份快照（但每檔 2 MB，而且不是查詢用的結構）。

本功能把它們合成一份可查詢的歷史文件 + 一個頁面。

---

## 2. 產物

| 檔案 | 性質 | 內容 |
|---|---|---|
| `src/watchlist_history.py` | 程式 | 讀 DB → 組歷史 → 原子寫出 JSON |
| `public/data/watchlist-history.json` | 產物（nightly 產生） | 完整歷史文件 |
| `public/watchlist-history.html` | 靜態頁（git 追蹤） | 歷史瀏覽器 |

### JSON 結構

```jsonc
{
  "date": "2026-11-13",            // nightly 資料日（認證用）
  "nightly_id": "f6cc1593...",      // nightly 批次（認證用）
  "source": "canonical MySQL market_screen_runs / market_screen_picks / daily_data2_full",
  "runs": 50,                      // 篩選次數
  "dates": ["2026-08-12", "..."],  // 每個篩選日
  "current": { "date": "2026-11-16", "run_id": 108, "picks_count": 24 },
  "duplicate_pick_rows": { "2026-09-07": ["1303"], "...": [] },  // 同日重複入選（揭露用）
  "tickers": {
    "1303": {
      "name": "南亞", "industry": "塑膠工業",
      "first_seen": "2026-08-31", "last_seen": "2026-11-16",
      "appearances": 47,            // 去重後的篩選次數
      "in_current": true,
      "entries": [                  // 每次入選一筆
        { "d": "2026-11-16", "b": "100-300", "h": "long", "s": "active",
          "sc": 98, "c": 274.0, "chg": 1.2, "e60": 3.4, "e240": 12.1,
          "r": { "級別": "日 K（120 根）", "方向": "偏多", "失效條件": "..." } }
      ],
      "path": [                     // 首次進榜後的每日正規收盤與累積報酬
        ["2026-08-31", 242.5, 0.0], ["2026-09-01", 234.5, -0.03299]
      ]
    }
  }
}
```

`r` 原本是一段 `**欄位**：值` 的文字。建置時解析成結構化欄位，理由兩個：
省掉 1,200 次重複標籤（文件從 943 KB 降到 909 KB），以及頁面可以**一行一個事實**呈現。

---

## 3. 頁面功能

`public/watchlist-history.html`

- **摘要卡**：歷史區間、篩選次數、曾進榜檔數、目前榜上檔數、同日重複入選天數
- **總覽表**：代號／名稱／產業／首次進榜／最後在榜／上榜次數／目前分級／首次收盤／最後收盤／自首次報酬／狀態
- **搜尋**：代號、名稱、產業
- **篩選**：全部／仍在榜／已離榜
- **排序**：上榜次數／最後在榜日／首次進榜日／自首次報酬／代號
- **下鑽**：點任何一列 → 抽屜顯示該檔完整時間軸
  - 統計卡：首次進榜、最後在榜、上榜次數、自首次報酬
  - 報酬路徑圖（SVG，紅＝漲／綠＝跌，含 0 軸虛線）
  - 入選紀錄表：日期／分級／方向／分數／收盤／當日／超額60日／超額240日／狀態
  - 每次入選的理由逐行展開（級別、資料日、當下位置、方向偏多／偏空、最近中樞、最新筆、失效條件…）
- **深層連結**：`watchlist-history.html?ticker=1303` 直接開啟該檔
- **手機版**：欄位自動收合（產業、最後在榜、首次／最後收盤、超額欄位）

### 台股顏色慣例

漲＝紅、跌＝綠（與美股相反），沿用 `watchlist.html` 的 `--red`／`--green`。

---

## 4. nightly 整合

| 檔案 | 改動 |
|---|---|
| `src/all_reports.py` | 呼叫 `watchlist_history.write_json(...)`；`paths` 加入 `data/watchlist-history.json` |
| `scripts/pipeline_state.py` | `REPORT_FRONTEND_FILES` 加入 `watchlist-history.html`；認證 `expected` 集合加入 `data/watchlist-history.json`；`REPO_SOURCE_FILES` 加入 `src/watchlist_history.py` |
| `scripts/render_full_watchlist.py` | 每張 pick 卡加「📜 歷史 →」連結 |

- stage 7（all_reports）在 nightly 內執行 → 歷史每晚自動長大
- 認證契約：`data/watchlist-history.json` 必須帶 `date` == 本次 `data_date`、
  `nightly_id` == 本次 `nightly_id`，否則 `validate_all_reports` 會擋下
- `scripts/` 下的兩個 cron 檔已同步到 runtime（`C:\Users\icemo\.claude\skills\tw-invest-suite\scripts`），
  repo ↔ runtime SHA-256 一致

---

## 5. 順手查到的既有缺陷：同日重複入選

`market_screen_picks` **沒有 `(run_id, ticker)` 唯一鍵**。實測有 17 天、20 組同一檔在同一
次篩選被寫入兩次（`1303`、`2454`、`2330`、`3443`、`2395`、`3026`、`2308`）。

後果：那些天的 24 筆 picks 其實只有 23 個不重複標的，其中一格被同一檔占掉兩次。
`publish_manifest.fetch_picks()` 只檢查列數（24）所以查不出來，認證的 manifest 也會
把該檔列兩次。

**本功能的處理**：
- 建置時以 `(run_id, ticker)` 去重（保留 `id` 最小者），上榜次數不再超過篩選次數
- 缺漏揭露在 JSON 的 `duplicate_pick_rows`，頁面顯示「同日重複入選 17 天」

**沒有修 DB**（沒有寫 schema、沒有加唯一鍵、沒有回寫既有列）——那是另一個需要單獨授權的
修正；且修之前要先確認 market screen 為什麼會重複入選。

---

## 6. 驗證

- `tests/test_watchlist_history.py`：6 個測試（理由解析、同日去重、認證身分、緊湊輸出、
  產物白名單、頁面契約、台股顏色）
- 全套 `pytest tests/`：235 passed / 1 failed
  - 唯一失敗 `tests/test_db_config.py::test_missing_password_fails_closed` 是**既有失敗**，
    原因是 `scripts/db_client.py` 有未提交的改動（新增 Windows registry 密碼 fallback），
    舊測試仍期待「密碼缺失就 fail-closed」。與本功能無關。
- 瀏覽器實測（手機視窗 487×767）：總覽表、下鑽抽屜、報酬圖、理由逐行、深層連結、
  去重後次數（47 / 50）皆正確
- 文件大小 909 KB（緊湊 JSON；GH Pages 會 gzip，實際傳輸約 180 KB）

---

## 7. 手動重跑

```powershell
cd C:\Users\icemo\Projects\tw-invest-suite
C:\Python314\python.exe scripts\_debug\_backfill_watchlist_history.py
```

或直接跑模組：

```powershell
C:\Python314\python.exe src\watchlist_history.py
```

---

## 8. 相關

- `docs/architecture.md` — 整體版面
- `scripts/pipeline_state.py` — 認證契約與產物白名單
- `src/all_reports.py` — nightly stage 7
- `public/chips-history.html` — 既有的歷史頁先例（本頁沿用同一套 house style）
