# tw-invest-suite — Handoff Doc (for ChatGPT)

> **Last updated**: 2026-09-03 (handoff from Mavis session to ChatGPT for debugging)
> **Goal**: Help the next AI session pick up where we left off and continue debugging/improving.

---

## 1. TL;DR — What's This Project

`tw-invest-suite` (坦克阿卡利) is a **Taiwan stock market analysis platform** with:

- **8 static HTML pages** (read-only, no auth) — `chips.html` is the main chips ranking page
- **1,962 tickers** × 14 skills × 18 「大師」 technical/fundamental analysis
- **OHLCV + 法人 + 融資券 + 30+ features** data in MySQL `tw_elec`
- **Auto daily pipeline** that pulls data from FinMind (sponsor tier) + yfinance + OpenAlice distributed scheduler
- **GitHub Pages** static deploy + **groovelab.dev** local server (Cloudflare Tunnel)

**Live URLs**:
- https://walterliu168.github.io/tw-invest-suite/
- https://groovelab.dev/

---

## 2. User Profile (Walter Liu — the owner)

- **Walter Liu** (GitHub: `walterLiu168`)
- **繁體中文** only — no simplified, use 「／」 not `/`
- Prefers direct, concise, businesslike communication
- Cares about: data freshness daily, web auto-deploy, accurate 收盤 numbers
- Domain: GitHub Pages (`walterliu168.github.io/tw-invest-suite`) + groovelab.dev (Cloudflare Tunnel)

---

## 3. Three Root Directories (CRITICAL — this confuses everyone)

| Path | Purpose | Git? |
|------|---------|------|
| `C:\Users\icemo\Projects\tw-invest-suite\` | **GitHub mirror** — version controlled, what `git push` deploys to GitHub Pages | ✅ Yes |
| `C:\Users\icemo\.claude\skills\tw-invest-suite\` | **Runtime scripts** — actual Python that runs (yfinance, FinMind, render, publish) | ❌ No (gitignored) |
| `C:\Groove-Lab\` | **Live HTML + analyze/** + Cloudflare Tunnel to groovelab.dev | ❌ No |
| `D:\CODEX\AI-Telegram\` | **OpenAlice** — FinMind 5m/price/inst/margin/daytrade 5 phases, news refresh, RSS | ❌ No |

⚠️ **When user asks "is it live?"**: check BOTH GitHub Pages AND groovelab.dev.
⚠️ **Edit chips.html**: must sync from `Projects\tw-invest-suite\public\chips.html` → `Groove-Lab\chips.html` AFTER every commit.

---

## 4. MySQL Database

```
host:     localhost
user:     root
password: 1234
database: tw_elec
```

**238 tables**. Key ones for this project:

| Table | Purpose | Currently updated? |
|-------|---------|-------------------|
| `daily_data2_full` | **PRIMARY** OHLCV + 法人 + 融資 + 技術指標 (35 cols) | ✅ Daily 17:35 OpenAlice |
| `daily_data` | Legacy subset of daily_data2_full (26 cols) | ✅ Now via cron (D046, 23:30) |
| `daily_data2` | Same schema as daily_data2_full (35 cols) | ✅ Now via cron (D046, 23:30) |
| `chip_daily` | 三大法人淨買超 (5 cols) | ✅ Now via cron (D046, 23:30) |
| `chipscore_daily` | 12-dim chip signals (12 cols) | ✅ Now via cron (D046, 23:30) |
| `market_screen_runs` | 每跑一次 +1 row (id, run_date, picks_count) | ✅ Hand-rolled |
| `market_screen_picks` | 24 picks per run (12 long + 12 short) | ✅ Hand-rolled |
| `industry_type` | 1962 ticker → company + industry (master) | ✅ Stable |
| `shares_master` | 1 ticker → SharesOutstanding (for market cap) | - |
| `stock_news` | 2.3M rows of news (cnyes + FinMind) | ✅ Refresh Every 2h |
| `news_sentiment_daily` | - | - |
| `eric_company_map`, `stock_names` | name lookups | - |
| `fact_daily_indicators` | - | (empty) |
| `ai_raw_daily`, `ai_features_daily`, `ai_daily_performance` | - | (empty) |

---

## 5. Daily Pipeline (as of 2026-09-03)

```
17:35  OpenAlice Daily OHLCV 1735         → daily_data2_full (TaiwanStockPrice)
17:55  OpenAlice Daily OHLCV Retry 1755   → retry
18:00  OpenAlice News Refresh ×12 cron    → stock_news (TaiwanStockNews)
20:15  OpenAlice Daily Institutional 2015 → daily_data2_full (TaiwanStockInstitutionalInvestorsBuySell)
21:15  OpenAlice Daily Margin Short 2115  → daily_data2_full (TaiwanStockMarginPurchaseShortSale)
21:45  OpenAlice Daily DayTrade 2145      → daily_data2_full (TaiwanStockDayTrading)
22:25  tw-invest-suite-daily-report       → run_daily.ps1 (render + push to OLD stock-report repo)
22:30  tw-invest-suite-yfinance (D047)     → yfinance_daily.py (PE/PB/market cap for 1962 tickers)
23:00  tw-invest-suite-health-check
23:30  tw-invest-suite-sync-legacy (D046) → sync_legacy_tables.py (4 legacy tables)
23:50  tw-invest-suite-publish (D047)     → publish_ghpages.py (push tw-invest-suite repo)
```

**Note**: `run_daily.ps1` Stage 99 publishes to OLD `walterliu168/stock-report` repo, NOT `walterliu168/tw-invest-suite`. That's why we added D047 23:50 cron separately.

---

## 6. Git History (recent)

```
aef9e0b D047: yfinance 22:30 cron + publish_ghpages 23:50 cron
2e6286a D046: sync_legacy_tables cron 23:30 — daily sync 4 legacy tables
97f02c3 D045b: backfill 9/1 to all 6 tables (9/1 收盤)
97f02c3 D045: backfill 8/31 + D044 拿掉我的篩選+加強 store UI
9c0df4c D043: persona 重排 + wizard 3 步 + 風格標籤
b975a9d D042: wizard 4-step: 11 persona + direction + range + sort (clean)
cfa43a7 D041: wizard+persona 自動套用 sort dropdown
b78aa53 D040: sort dropdown 擴充 8 個選項
ec8e3be D039: fix: ws_eps card position + fmt_shares 股→張
dd521a9 D038d: EPS FinMind full market + ws_eps persona
eb13998 D038: moat (護城河) + news sentiment (cnyes)
b7abcf0 D037c: 4 wizard features
dd3ae31 D037b: 4 Wall Street personas
4932d01 D037: wizard 4-step branching
... (D001-D036 in docs/decision-log.md)
```

Full history: `cd C:\Users\icemo\Projects\tw-invest-suite && git log --oneline | head -50`

---

## 7. Key Files / MDs to Read

### 7.1 Decision log (D001-D035)
- `C:\Users\icemo\Projects\tw-invest-suite\docs\decision-log.md` (7.9KB)
- **MUST READ** — documents all design decisions chronologically

### 7.2 Architecture
- `C:\Users\icemo\Projects\tw-invest-suite\docs\architecture.md` (9.3KB)
- How the 8 pages + database + scripts + cron fit together

### 7.3 Data schema
- `C:\Users\icemo\Projects\tw-invest-suite\docs\data-schema.md` (5.1KB)
- All key table column definitions

### 7.4 Schedule
- `C:\Users\icemo\Projects\tw-invest-suite\docs\schedule.md` (3.0KB)
- Old cron list — **NOTE: out of date**, use Section 5 above

### 7.5 Skills
- `C:\Users\icemo\Projects\tw-invest-suite\docs\skills.md` (4.3KB)
- Which 14 skills the system uses

### 7.6 SKILL.md (the project)
- `C:\Users\icemo\.claude\skills\tw-invest-suite\SKILL.md` (9.5KB)
- The Claude skill spec for this project

### 7.7 TODO
- `C:\Users\icemo\.claude\skills\tw-invest-suite\TODO.md` (2.5KB)
- Pending improvements

### 7.8 main chips.html
- `C:\Users\icemo\Projects\tw-invest-suite\public\chips.html` (1.7MB — server-rendered 1962 cards)
- The "main product" — 8 tabs, 16 persona cards, 3-step wizard, store UI

---

## 8. Persona Cards (D043 — currently live)

Order (新手精靈 first, then by direction):

| Row | Cards | Direction |
|-----|-------|-----------|
| 1 | 🆕 新手精靈 / 法人連買 [短波長] / 土洋同買 [短波長] / 外資大買 [短波] / 量能爆發 [短] / 外資停留 [波長] / 金融存股 [長] / AQR 雙優勢 [波長] | Multi |
| 2 | JT 動能王 [短波] / 法人鎖碼 [波長] / 空方避雷 [波長] / 弱勢退場 [波長] / 跌深反彈 [短] / 護城河之王 [長] / 新聞利多 [短波] / EPS 成長 [波長] | Multi |

**Wizard 3 步** (D043):
1. 方向 (看多/看空/全部)
2. 時段 (短線/波段/長期)
3. 3 張推薦 persona cards 點任一即套用

---

## 9. Known Issues (待辦)

| Priority | Issue | Status |
|----------|-------|--------|
| 🔴 High | FinMind PE 3/1962 (Stage 2 in run_daily.ps1) | Broken — 之前 daily run 從不跑這 stage; 現改由 tw-invest-suite-yfinance cron 22:30 跑 yfinance (不跑 FinMind PE) |
| 🔴 High | FinMind News 0/1962 (Stage 2) | Same — D038 已改用 cnyes news_score fallback |
| 🟡 Mid | run_daily.ps1 Stage 99 推到舊 stock-report repo | Workaround: D047 23:50 cron 推 tw-invest-suite |
| 🟡 Mid | daily_data2_full.company 12 個新上市缺 | 12 個 ticker 不在 industry_type，skip (not critical) |
| 🟢 Low | Public analyze/ 1,961 HTML 缺 D044/D045 D-codes | 1,961 個 analyze.html 還是舊版，沒 D044 改動 |
| 🟢 Low | D034 chips.html tabs 計數是 chips.json 原始 bucket 數 | 不是 PENDING 過濾後的計數 |

---

## 10. Reusable Scripts (git-committed to `src/`)

| File | Purpose |
|------|---------|
| `src/_daily_backfill.py` | Backfill latest date to 4 legacy tables (manual emergency use) |
| `src/_rerun_screen.py` | Re-generate 24 picks for latest run_id |
| `src/_sync_legacy_tables.py` | Same as D046 — manual run |
| `src/_yfinance_daily.py` | Same as D047 — manual run |
| `src/_publish_ghpages_daily.ps1` | Same as D047 — manual run |
| `src/_d043_patch.py` | D043 persona reorder patch |
| `src/_d044_patch.py` | D044 拿掉我的篩選 patch |
| `src/_morning_check.py` | Sanity check all tables, cron, web artifacts |

---

## 11. Prompt for ChatGPT (next session)

```
You are continuing work on a Taiwan stock analysis platform called tw-invest-suite
(坦克阿卡利). Please read the handoff document at:

C:\Users\icemo\Projects\tw-invest-suite\docs\handoff_chatgpt.md

Then read these MDs in order:
1. C:\Users\icemo\Projects\tw-invest-suite\docs\decision-log.md
2. C:\Users\icemo\Projects\tw-invest-suite\docs\architecture.md
3. C:\Users\icemo\Projects\tw-invest-suite\docs\data-schema.md
4. C:\Users\icemo\.claude\skills\tw-invest-suite\SKILL.md
5. C:\Users\icemo\.claude\skills\tw-invest-suite\TODO.md

Then sanity check:
- python -c "import pymysql; c=pymysql.connect(host='localhost',user='root',password='1234',database='tw_elec'); cur=c.cursor(); cur.execute('SELECT MAX(Date), COUNT(*) FROM daily_data2_full'); print(cur.fetchone())"
  → Should be (today's date or yesterday, ~3600000)
- schtasks /query /fo csv | Select-String "tw.invest|OpenAlice"
  → Should list: 22:25 daily-report, 22:30 yfinance, 23:00 health, 23:30 sync-legacy, 23:50 publish
- Open https://walterliu168.github.io/tw-invest-suite/chips.html — 16 persona cards, 3-step wizard
- Open https://walterliu168.github.io/tw-invest-suite/watchlist.html — 24 picks

User profile:
- Walter Liu (GitHub walterLiu168)
- 繁體中文 only
- Prefers direct, concise communication

Current focus (open issues):
1. FinMind PE/News 0% — workaround is yfinance (22:30 cron)
2. run_daily.ps1 Stage 99 推舊 repo — workaround is publish_ghpages cron (23:50)
3. Public analyze/ 1,961 HTML 缺 D044/D045 D-codes

When debugging:
- Always check BOTH GitHub Pages AND groovelab.dev
- After every chips.html change: sync to Groove-Lab, run publish_ghpages.py
- Commit + push to main → manual run publish_ghpages.py (now via 23:50 cron)
- Daily data must be up to date by 10pm (user requirement)
- 1,962 tickers — daily_data2_full.company 12 個 null 是新上市，skip
```

---

## 12. Quick Commands Cheat Sheet

```powershell
# Check daily data freshness
cd C:\Users\icemo\Projects\tw-invest-suite\src
python _morning_check.py

# Sanity check 5 個關鍵 tables
python -c "import pymysql; c=pymysql.connect(host='localhost',user='root',password='1234',database='tw_elec'); cur=c.cursor(); [print(t, cur.execute(f'SELECT MAX(Date), COUNT(*) FROM {t}')) or print('  ', cur.fetchone()) for t in ['daily_data2_full','daily_data','daily_data2','chip_daily','chipscore_daily']]"

# List all tw-invest-suite crons
schtasks /query /fo csv | Select-String "tw.invest"

# Manual trigger yfinance (D047)
cd C:\Users\icemo\.claude\skills\tw-invest-suite\scripts
.\yfinance_daily.ps1

# Manual publish to GitHub Pages (D047)
cd C:\Users\icemo\Projects\tw-invest-suite\scripts
python publish_ghpages.py

# Manual backfill 4 legacy tables (D046)
cd C:\Users\icemo\Projects\tw-invest-suite\src
python _daily_backfill.py

# Manual re-render 24 picks (D045)
python _rerun_screen.py
# then python render_watchlist_html.py (in scripts/)
```

---

## 13. Error Patterns to Watch

| Error | Cause | Fix |
|-------|-------|-----|
| `NullPointerException` on `getElementById('filter-cnt')` etc. | chips.html D044 patch 沒清乾淨，D032 elements 被刪但 JS 還在 reference | 已 stub 5 個 D032 function (bindUI, renderAdv, syncUI, previewFilter, buildIndustryList, showAutoApplyNotice) |
| `Cannot set properties of null` on summary-bar | D044 拿掉 sum-pname/sum-conds/sum-cnt | 確認 summary-bar 內 3 個 element 還在 |
| `tank-akali-saved-strategies` 0 strategies | localStorage 跨 domain 沒 sync | 確認 D035 localStorage 是 per-domain (groovelab.dev vs github.io 各自) |
| `Out of range value for column 'score'` (market_screen_picks) | score 沒 normalize | 已 normalize to 0-100 (`round(min(100, max(0, score/1000)), 2)`) |
| FinMind API rate limit (0.23s/call sponsor) | 1,962 tickers × 5 datasets = ~10,000 calls × 0.23s = ~38 min | 排程分階段 17:35/20:15/21:15/21:45 |
| yfinance 0/1962 (DEAD state) | 20+ consecutive failures | D047 22:30 cron + FinMind fallback |

---

## 14. If You Get Stuck

1. **Latest 2 commits**: `git log --oneline -5`
2. **Last daily run log**: `Get-Content C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug\daily_run_20260903.log -Tail 50`
3. **Cron status**: `schtasks /query /fo csv | Select-String "tw.invest"`
4. **DB status**: `python _morning_check.py` (in `src/`)
5. **GitHub Pages status**: `curl -I https://walterliu168.github.io/tw-invest-suite/chips.html`
6. **groovelab status**: `curl -I https://groovelab.dev/chips.html`

---

**Remember**:
- Walter wants daily latest trading day data ready by 10pm
- Wizard 3-step + 16 persona cards + 拿掉我的篩選 = current chips.html design
- Watch for: chips.html working but watcher/crons breaking
- Always sync Groove-Lab + GitHub Pages after chips.html change
- 5 個關鍵 tables 必須 daily up-to-date: daily_data2_full, daily_data, daily_data2, chip_daily, chipscore_daily
