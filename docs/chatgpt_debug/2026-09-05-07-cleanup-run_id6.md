# Cleanup market_screen_runs residue — pending Walter approval

> **狀態：PENDING (待 Walter 核准後執行)**
> 由 D052h-fixup2 F6 提出。
> 這份 MD 僅記錄需要的 SQL 與刪除前/後的證據。
> **不自動執行**；請 Walter 看完之後決定。

## 為什麼要清

`market_screen_runs` 與 `market_screen_picks` 內目前有 3 筆 9/5 測試階段注入的殘留 run (`id=3, 4, 6`)。它們都是 D052h-fixup 與 D052h-fixup2 開發期間用 `--force --data-date=...` 留下的。

**D052h-fixup3 新增事實**：run_id=4 對應 9/4 資料，但因 `mr.save_report` / `mrh.save_html` 用 `datetime.now()` 命名檔案，9/4 的 MD/HTML 實際被命名為 `market-screen-2026-09-05.{md,html}`（執行當下 9/5 Sat）。

- `market-screen-2026-09-04.md`：**不存在**（實際位於 `market-screen-2026-09-05.md`）
- `market-screen-2026-09-04.html`：**不存在**（同上）
- `deep-dive-prompts-2026-09-04.md`：存在（DD generation 一開始就使用 data_date）

D052h-fixup3 已把 `data_date` 參數加進 `mr.save_report` / `mrh.save_html`，未來 daily run / `--force` / repair 全部會用 data_date 命名。但**已經誤命名的 9/5 檔案仍留在 `~/.claude/skills/tw-invest-suite/reports/`**。

**重要警告**：**不要**用 `python market_screen_runner.py --force --data-date=2026-09-04` 來「重新生成 9/4 artifacts」當作 cleanup 手段。`--force --data-date=...` 會重跑 `ms.screen_market()` 並**改寫 production DB**（建立新一筆 `market_screen_runs` + 24 picks，可能 close 既有 active picks）。這違反「不要 DELETE production DB」與「不污染 production 狀態」的 fixup4 紀律。

正確做法：若要清理 9/5 誤命名的 artifacts，直接在檔案層刪除 `~/.claude/skills/tw-invest-suite/reports/market-screen-2026-09-05.{md,html}`（與對應的 `deep-dive-prompts-2026-09-05.md` 留或不留都行，DD 內容也是 9/4 資料）。下次 18:20 真的跑 daily run 時，新版的 renderer（`data_date=2026-09-07` 之類）會自然產出正確命名的 artifact。

**postflight 目前仍未檢查 market-screen MD/HTML/DD 存在性**：postflight 只檢查 24 active picks、company_null、industry_count、quarantine、publish_artifact、tasks。不會看到 `market-screen-2026-09-04.{md,html}` 缺失。9/5 誤命名的 artifact 問題必須靠人工或下次 daily run 自然覆蓋。

| id | run_date | run_at | picks active | 性質 | 建議 |
|---|---|---|---|---|---|
| 3 | 2026-09-01 | 2026-09-05 18:33:35 | 0 | backdated residue（D052h-fixup2 F5 已擋下，但這筆是 D052h-fixup 階段留下的） | 刪 |
| 4 | 2026-09-04 | 2026-09-05 18:34:24 | 24 | 9/4 真實資料的 re-run，但 run_at 是測試時段。下次 18:20 會自然 close 並建立新 run。 | 視決策 |
| 6 | 2026-09-02 | 2026-09-05 18:00:41 | 0 | backdated residue（D052h-fixup 階段 F5 尚未實作） | 刪 |

legit（不要動）：

| id | run_date | run_at | picks active | 性質 |
|---|---|---|---|---|
| 1 | 2026-08-12 | 2026-08-12 18:04:40 | 0 | 8/12 真實 run（早於新架構） |
| 2 | 2026-08-31 | 2026-09-01 14:21:19 | 0 | 8/31 真實 run（早於新架構） |

D052h-fixup2 F5 之後，這種「用最新 snapshot 寫回舊日期」的覆寫已經擋下（`override_date != latest_date` 直接 exit 1）。但測試階段留下的殘留還在 DB 裡，必須由人工確認後刪除。

## 為什麼不自己刪

- 這 3 筆雖然是測試殘留，但它們已經是 production `market_screen_runs` 的真實 row，D052h-fixup2 的紀律是**不在沒有 owner 授權時動 production**。
- 刪除連帶 `market_screen_picks` 共 72 row（24 × 3），可逆但仍須 owner sign-off。
- 之後若 postflight 或 audit 撈到這 3 筆，會誤判當天有兩份真實 24-picks run。

## 刪除前證據（SELECT）

```sql
-- 1. 確認這 3 筆仍在 + 內容
SELECT id, run_date, run_at, total_tickers, picks_count, LEFT(notes, 80)
FROM market_screen_runs WHERE id IN (3, 4, 6) ORDER BY id;

-- 2. 列出每筆的 picks 數量
SELECT run_id, COUNT(*) total,
       SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) active_n
FROM market_screen_picks WHERE run_id IN (3, 4, 6)
GROUP BY run_id ORDER BY run_id;

-- 3. 確認 market_screen_runs 還有 id=1, 2 是真實歷史
SELECT id, run_date, run_at, total_tickers, picks_count
FROM market_screen_runs ORDER BY id;

-- 4. 確認 24 active picks 來源
SELECT run_id, COUNT(*) total, SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) active
FROM market_screen_picks GROUP BY run_id ORDER BY run_id;

-- 5. 確認沒有任何 artifact 用 2026-09-01 / 2026-09-02 (id=3, 6) 命名
--    （id=4 的 2026-09-04 對應的 MD/HTML 實際上不存在 — D052h-fixup3 前的
--     renderer 用 datetime.now() 命名，所以 9/4 run 寫到了 9/5 檔案。
--     market-screen-2026-09-05.{md,html} 是 9/4 資料的誤命名 artifact。）
SELECT * FROM information_schema.tables
WHERE table_schema='tw_elec' AND table_name='reports';  -- sanity only
-- 改用檔案系統檢查：
--   C:\Users\icemo\.claude\skills\tw-invest-suite\reports\
--     market-screen-2026-09-01.* 應該沒有
--     market-screen-2026-09-02.* 應該沒有
--     market-screen-2026-09-04.* 不存在（D052h-fixup3 前的 date contract bug）
--     market-screen-2026-09-05.* 存在（誤命名，內容是 9/4 資料）
```

預期結果：

- step 1：3 列，分別是 9/1、9/4、9/2 的 run，picks_count 都是 24。
- step 2：id=3 有 24 / 0 active；id=4 有 24 / 24 active；id=6 有 24 / 0 active。
- step 3：id = 1, 2, 3, 4, 6 共 5 列。
- step 4：id=4 有 24 / 24 active；其它都 0 / 0。
- step 5：reports 目錄下**沒有** `market-screen-2026-09-04.*`；有 `market-screen-2026-09-05.{md,html}`（誤命名）。

## 刪除（transactional）

**選項 A — 只刪純 residue（推薦）**：

```sql
START TRANSACTION;

-- 6. 刪 id=3 (9/1) 與 id=6 (9/2) 的 picks
DELETE FROM market_screen_picks WHERE run_id IN (3, 6);

-- 7. 刪 id=3 與 id=6 兩筆 run
DELETE FROM market_screen_runs WHERE id IN (3, 6);

-- 8. 立即驗證
SELECT COUNT(*) AS remaining_residue_runs
FROM market_screen_runs WHERE id IN (3, 6);
-- 預期：0

SELECT COUNT(*) AS remaining_residue_picks
FROM market_screen_picks WHERE run_id IN (3, 6);
-- 預期：0

-- 9. 全表仍應有 24/24 active（id=4 仍保留）
SELECT run_id, COUNT(*) total, SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) active
FROM market_screen_picks GROUP BY run_id ORDER BY run_id;
-- 預期：id=4 24/24

COMMIT;
-- 或發現問題：ROLLBACK;
```

**選項 B — 連 id=4 一起清，準備讓下次 18:20 自然重跑**：

```sql
START TRANSACTION;

DELETE FROM market_screen_picks WHERE run_id IN (3, 4, 6);
DELETE FROM market_screen_runs WHERE id IN (3, 4, 6);

SELECT COUNT(*) AS remaining_runs_in_3_4_6
FROM market_screen_runs WHERE id IN (3, 4, 6);
-- 預期：0

SELECT COUNT(*) AS remaining_active
FROM market_screen_picks WHERE status = 'active';
-- 預期：0 (因為 id=4 是唯一 active，刪了之後就沒 active)

COMMIT;

-- 之後由 18:20 market_screen_daily.ps1 自然建出新 run
-- 前提：metadata_backfill_daily.ps1 18:10 先寫了 metadata_target_2026-09-08_OK.marker
```

**選項 C — 不刪**：

留著這 3 筆，後續 audit 腳本需顯式排除。下次 18:20 自然 close id=4 並建新 run；id=3 與 id=6 已經 active=0，無實際影響。

## 刪除後驗證

```sql
-- A. 重跑 SELECT step 1-4
-- B. market_screen_picks 應當有 24/24 active（若選 A）或 0 active（若選 B）
SELECT run_id, COUNT(*) total, SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) active
FROM market_screen_picks GROUP BY run_id;
-- A 預期：id=4 24/24
-- B 預期：空

-- C. 跑 postflight_daily.py 確認 market_screen check
python C:\Users\icemo\Projects\tw-invest-suite\scripts\postflight_daily.py
-- A 預期：market_screen pass
-- B 預期：market_screen fail（直到下次 18:20 建立新 run）
```

## 風險評估

- `market_screen_picks` 沒有 FK 強制連到 `market_screen_runs.id`（觀察 runtime 行為後），所以兩個 DELETE 順序顛倒也安全；但保持 `picks → runs` 順序比較語義清楚。
- 沒有任何對外 artifact（`reports/market-screen-2026-09-01.*` 與 `market-screen-2026-09-02.*`）存在；id=4 對應 9/4 資料，但當初 D052h-fixup3 前用舊版 renderer 產出時，MD/HTML 檔名是用 `datetime.now()` 寫的（執行當下 9/5），所以實體檔案是 `market-screen-2026-09-05.{md,html}`（**誤命名**）。DD 倒是從一開始就傳 data_date，所以 `deep-dive-prompts-2026-09-04.md` 存在。
- 若 Walter 想保留審計軌跡，建議刪除前先做：
  ```sql
  CREATE TABLE market_screen_runs_audit_2026_09_05 AS
  SELECT * FROM market_screen_runs WHERE id IN (3, 4, 6);
  CREATE TABLE market_screen_picks_audit_2026_09_05 AS
  SELECT * FROM market_screen_picks WHERE run_id IN (3, 4, 6);
  ```
  然後再跑 transaction。

## 建議決策

- **選項 A（推薦）**：刪 id=3 與 id=6 純 residue，保留 id=4 為 9/4 真實 run（active=24）。下次 18:20 會自然 close id=4 並建新 run。
- 選項 B：全部清空，等下次 18:20 自然重建。最乾淨但有短暫的「無 24 active picks」窗口。
- 選項 C：不刪，留著 audit。

我建議 A，最安全。等 Walter 同意後我跑。

## 記錄

- 建立：2026-09-05 18:35 by Mavis (D052h-fixup2 F6)
- 等待：Walter sign-off
- 預計執行時間：< 5 秒
