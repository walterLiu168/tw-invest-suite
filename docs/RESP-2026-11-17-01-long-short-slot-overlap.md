# RESP-2026-11-17-01 每日精選「同一檔兩個名額」根因與處置

**日期**：2026-11-17
**對象**：`market_screen` 每日精選清單（24 名額）
**狀態**：已實作「誠實呈現 + 統計去重」；「改成 24 個不重複標的」待 Walter 決定
**前置**：`docs/WATCHLIST_HISTORY_FEATURE.md`（歷史回看頁，D018）

---

## 0. 結論

**不是資料庫壞掉，也不是重複寫入。是選股邏輯允許同一檔同時佔「長期」與「短中期」兩個名額，
而持久層與認證層都只檢查名額分布、從不檢查標的是否重複。**

50 次篩選中有 **18 次**出現同一檔佔兩個名額 → 對外宣稱的「24 檔」實際只有 **23 檔**。
2026-11-16 線上清單就是如此：**3443 同時出現在 long 與 short 兩張卡**。

**Walter 已於 2026-11-17 批准選項 B（long／short 互斥），已實作。**
同時保留呈現層的誠實揭露作為第二道防線。

---

## 1. 根因鏈

### 1.1 選股層：兩個獨立排序，沒有互斥

`scripts/market_screen.py:348-353`

```python
for label, _, _ in PRICE_BUCKETS:
    bucket = by_bucket.get(label, [])
    longs  = [replace(c, horizon="long")  for c in pick_long_term(bucket, PICKS_PER_HORIZON)]
    shorts = [replace(c, horizon="short") for c in pick_short_term(bucket, PICKS_PER_HORIZON)]
    result[label] = {"long": longs, "short": shorts}
```

`pick_long_term()`（`:277`）與 `pick_short_term()`（`:280-283`）是**兩套彼此獨立的排序**，
都在同一個 bucket 的候選池上跑，**short 名單沒有排除 long 名單**。

所以同一檔同時是某 bucket 的長期首選與短中期首選時，兩個名額都被它拿走。

### 1.2 分數的證據

`replace(c, horizon=...)` 保留原 `c.score`，而 `pick_short_term` 會用 `short_term_score(c)`
覆寫候選池裡每個 `c.score`（long 的複本已先複製出來，所以 long 分數安全）。

DB 裡的實測配對：

| 日期 | 檔 | long 分數 | short 分數 | bucket |
|---|---|---|---|---|
| 2026-09-07 | 1303 | 97.08 | 2.30 | 100-300 |
| 2026-09-23 | 2395 | 87.86 | 2.30 | 300-1000 |
| 2026-10-28 | 1303 | — | — | 100-300 |
| 2026-11-16 | 3443 | 92.86 | ~1.5 | >1000 |

→ 同一檔在兩個名額裡的 long / short 分數**完全不同**，確認是兩套獨立評分各自挑到它。

### 1.3 持久層：沒有唯一鍵，但也不是它造成的

- `market_screen_picks` 沒有 `(run_id, ticker)` 唯一鍵（`data/schema/mysql.sql:85`）
- 但 `market_screen_runner.persist_atomic()`（`:257-273`）對 `market_screen_runs` 以 `run_date` 做
  UPSERT，並在插入前 `DELETE FROM market_screen_picks WHERE run_id = %s`
  → **同一個 run_id 不會累積重複列**
- 實測 `daily_data2_full` 沒有任何重複 `(Ticker, Date)` 列（0 組）
  → 快照不是重複來源；`db_client.market_snapshot()` 沒有 `DISTINCT` 是一個隱性風險，
  但目前不是這次重複的原因

### 1.4 認證層：只驗名額，不驗標的

`scripts/render_full_watchlist.py` 的現行檢查只要求每個 `(bucket, horizon)` 剛好 3 檔、
總數 24 檔：

```python
expected = {(b, h): 3 for b in BUCKETS for h in ("long", "short")}
if run["picks_count"] != 24 or len(picks) != 24 or groups != expected:
    raise ValueError(...)
```

**沒有任何一條檢查 24 個名額是 24 個不重複標的** → 帶著重複的名單一路通過認證並發佈。

### 1.5 呈現層：數字被雙重計算

`render_full_watchlist.py`（原本 `:1911`）：

```python
rets = [perf_map.get(c.ticker, {}).get("ret_since_pick") for c in all_picks ...]
avg = sum(rets) / len(rets)
wins = sum(1 for r in rets if r > 0)
```

走 `all_picks`（24 列）→ 重複檔的報酬**算兩次**。
同時「活躍 picks 24」與頁面標題「24 檔」都把 24 個名額說成 24 檔。

---

## 2. 影響量化

18 / 50 次篩選有重複（18 / 50 = 36%）。以有 5 日報酬的日子計算：

| 影響面 | 量級 |
|---|---|
| 對外宣稱的檔數 | 36% 的日子「24 檔」實際 23 檔 |
| 平均報酬扭曲 | ≤ 0.001（10-28）／+0.0006（11-06）／+0.0063（11-09） |
| 勝率扭曲 | +0.9pp（11-06）／+2.2pp（11-09） |
| 頁面呈現 | 同一張卡出現兩次（不同長期／短中期角色） |
| `publish_manifest.tickers` | 24 筆含重複 |
| 歷史回看頁 | 必須自行去重（已做） |

**統計扭曲很小，聲明不實與重複呈現才是真正的問題。**

---

## 4. 已實作

### 4.1 選股層：long／short 互斥（2026-11-17 經 Walter 批准）

`scripts/market_screen.py` 新增 `pick_horizons(bucket, n)`：

```python
longs = [replace(c, horizon="long") for c in pick_long_term(candidates, n)]
long_tickers = {c.ticker for c in longs}
pool = pick_short_term(candidates, len(candidates))
shorts = [replace(c, horizon="short") for c in pool
          if c.ticker not in long_tickers][:n]
```

- short 名單跳過 long 已取走的名稱，改取該排序的**下一名**
- short 的分數仍是 `short_term_score`（不是沿用 long 分數）
- **邊界**：若該 bucket 的不重複名稱不足 6 個，short 會依 long 分數由低到高讓出名額，
  確保名額數仍是 24，並把讓出的名稱記錄下來（`reused`）在畫面輸出
- `screen_market()` 印出 `bucket exhausted, slot reused for ...` 以便稽核

**效果**：每日 24 個名額必定是 24 個不重複標的。

### 4.2 呈現層：統計去重 + 誠實揭露（保留為第二道防線）

| 位置 | 改動 |
|---|---|
| `render_full_watchlist.py::summarize_picks()` | 新增可測試函式：同一 ticker 只計一次；回傳名額數／不重複檔數／平均／勝率／重複清單 |
| 摘要卡「活躍 picks」 | 不重複時顯示 `24 檔`；有重複時顯示 `24 名額／23 檔` |
| 頁面標題與頁尾 | 同樣改用名額／檔數，不再硬寫「24 檔」 |
| 頁面新增揭露列 | 有重複時顯示黃色說明列，列出重複檔名與重疊名額數 |
| 平均報酬／勝率 | 改以不重複標的計算，停止雙重計數 |
| `tests/test_watchlist_overlap.py` | 4 個測試 |
| `tests/test_market_screen_exclusive.py` | 4 個測試（互斥、short 分數、bucket 名額不足時讓位、每 bucket 3+3） |

**沒有**加 DB 唯一鍵、**沒有**回寫既有資料列。

---

## 4.3 為什麼仍保留呈現層的揭露

即使選股層已互斥，認證層目前仍然只驗「每個 (bucket, horizon) 3 檔、總數 24」，
不驗標的是否重複。若未來有人改動選股邏輯，兩道防線都還在：
一邊讓頁面不會說錯話，一邊讓統計不會被雙重計數。

---

## 4.4 變更帶來的選股影響（實測）

互斥會讓 **short 名額往下移**：某檔原本同時是 long 與 short 首選時，
short 那一格改由該 bucket 的 short 次名接手。

以 2026-11-16 為例（`>1000` bucket，36 個候選）：

| | 發佈前 | 發佈後 |
|---|---|---|
| long | 3443, 2454, 2330 | 不變 |
| short | 3491, 6446, **3443** | 3491, 6446, **3661** |

short 分數：3491=2.2、6446=1.8、**3443=1.7**（被排除）、**3661=1.7**、6510=1.7。
同分依代號升序（`tie_break: ticker_ascending`）→ 3443 之後是 3661。

**影響可控**：每個有重複的日子只換掉 1～2 個 short 名額，且是確定性的「取下一名」，
不是隨機重排。四個 bucket 中當天只有 `>1000` 一個有重複。

要量化「每天換掉幾個名額」，歷史資料沒有存 short 候選池，無法回溯比較；
以 **2026-11-17 起的實際篩選**為準，觀察一個月後再回頭比較歷史績效。

---

## 5. 這份文件沒有回答的問題

- 為什麼 long 與 short 兩套評分會同時把同一檔排到前面（評分式相關性）尚未量化
- 2026-11-16 的 3443 當日 `change_pct = -9.9884`（跌停）卻拿到 long 分數 92.86，
  這是**另一個**評分問題（跌停仍給高分），本次未追查
- 18 次重複集中在 2026-09 與 2026-10 下旬，是否與當時的資料品質事件有關尚未查
- `market_screen_picks` 沒有 `(run_id, ticker)` 唯一鍵這件事本身仍存在
  （目前靠 DELETE-then-INSERT 的冪等性擋住，不是靠約束）

---

## 6. 重現方式

```powershell
C:\Python314\python.exe <workspace>\scripts\_debug\_duplicate_root_cause.py   # 每一組重複的 long/short 配對
C:\Python314\python.exe <workspace>\scripts\_debug\_overlap_impact.py       # 統計扭曲量化
C:\Python314\python.exe <workspace>\scripts\_debug\_long_short_overlap.py   # 線上清單的重複實況
C:\Python314\python.exe -m pytest tests/test_watchlist_overlap.py -q
```
