# ChatGPT review request: 12 個新上市 ticker 缺 company name

> **For**: ChatGPT (via Codex visible UI or web chatgpt.com)
> **From**: Walter Liu (via Mavis desktop)
> **Date**: 2026-09-04
> **Status**: pending (ChatGPT to review and respond)

---

## 📋 PROMPT (copy this into ChatGPT)

```
You are reviewing a debug finding for a Taiwan stock analysis platform
(tw-invest-suite, 1,962 tickers, MySQL tw_elec, GitHub Pages).

The 12 newly listed tickers below have OHLCV in `daily_data2_full` but
NO company name in any of the 4 local master tables
(industry_type / stock_info / stock_names / shares_master).

→ analyze/<ticker>.html pages render with NULL company name.

Root cause: `industry_type.Update_time = 2026-04-29 21:04:05` — no
auto-backfill since. The 12 are real, actively traded, but were listed
after 2026-04-29.

Mavis proposes:
  1. One-shot backfill the 12 into `industry_type` from FinMind
     `TaiwanStockInfo` (1 API call, 0.4s, 12/12 confirmed hit).
  2. Add a recurring cron `tw-invest-suite-industry-backfill` at 17:30
     (after daily close) that pulls full `TaiwanStockInfo` and
     INSERT...ON DUPLICATE KEY UPDATE.
  3. Optionally sync to stock_info / stock_names / shares_master.

The 12 tickers + FinMind data:
  3485  敘豐      電子零組件業
  4195  基米-創    生技醫療業
  4582  聚恆-創    綠能環保
  6945  圓祥生技   生技醫療業
  6983  華洋精機   其他電子類
  7768  頌勝科技   電子工業
  7772  耀穎      半導體業
  7803  雲象科技-創 生技醫療業
  7818  溢泰實業   綠能環保
  7819  精誠金融   資訊服務業
  7827  漢康-KY創  生技醫療業
  7842  天能綠電   綠能環保類

Full debug context: docs/chatgpt_debug/2026-09-04-01-debug-12-newly-listed-tickers.md

QUESTIONS for you:
  1. Is INSERT...ON DUPLICATE KEY UPDATE the right pattern, or should
     we use a staging table + review gate before promoting to
     industry_type?
  2. Should the new cron run at 17:30 (right after daily close) or
     earlier (e.g. 09:00 before market opens)?
  3. Should we add a Slack/Telegram alert when a new ticker is detected
     in daily_data2_full but missing from industry_type?
  4. Is industry_type the right master, or should we promote stock_info
     (which has ListedDate) to canonical?
  5. What edge cases am I missing? (e.g. delisted tickers, ticker
     renumbering, 上櫃 vs 上市 type mismatch)

OUTPUT FORMAT (return markdown only, no preamble):
  # <short title>
  > Submitted: 2026-09-04 by ChatGPT (visible UI)
  > Target: industry_type + cron + 12 tickers
  > Status: pending
  > Scope: db | cron | scripts

  ## Review of Mavis findings F1-F4
  ...

  ## Additional findings
  ### F<n>. <title>
  - File: <path>:<line>
  - Issue: ...
  - Suggested fix: ...
  - Priority: high | mid | low

  ## Questions back to Mavis
  ...

  ## Status
  *(Mavis will append implementation results after Walter approves)*
```

---

## 📂 Supporting context (paste this URL into ChatGPT if it can read files)

`docs/chatgpt_debug/2026-09-04-01-debug-12-newly-listed-tickers.md`

Key facts from that file:

- `industry_type` is the master table. Schema: `ticker varchar(10), company varchar(100), industry varchar(50), last_updated timestamp`
- Currently 1,962 rows, range 1101..9962, last updated 2026-04-29 21:04:05
- `daily_data2_full` latest date: 2026-09-03 (2,628 tickers, all 12 hit)
- `daily_data2_full.company` is filled by `src/_daily_backfill.py` from `industry_type.company` via JOIN
- `src/chip_rank.py` is the source of truth for chips.html rendering
- 5 existing crons: 22:25 daily-report, 22:30 yfinance, 23:00 health, 23:30 sync-legacy, 23:50 publish
- Project root: `C:\Users\icemo\Projects\tw-invest-suite`
- Skills dir (runtime scripts, not git): `C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\`
- 5 cron names use prefix `tw-invest-suite-*` (Task Scheduler)

---

## 📂 Project conventions (for ChatGPT to know)

- Language: 繁體中文 only
- Output filenames: 「／」 not `/`
- Volume: 1 張 = 1,000 股, use `Math.ceil(shares/1000)` when displaying
- FinMind sponsor token at `~/.finmind_token`, ~0.4s/call
- DB: localhost / root / 1234 / tw_elec
- MySQL convention: NULL → None in Python; 0/負值 → None for ratios
- Color convention: 紅=漲, 綠=跌 (Taiwan, opposite of US)
- Daily run uses `--no-yfinance --no-news` for batch speed; yfinance filled by separate 22:30 cron
- Handoff doc for general project context: `docs/handoff_chatgpt.md` (13.9KB, 15 sections)

---

## 🔄 Workflow reminder

1. You (Walter) copy the **PROMPT** block into ChatGPT (via Codex visible UI or web)
2. ChatGPT responds with the structured markdown review
3. You paste ChatGPT's response into a new file: `docs/chatgpt_debug/2026-09-04-NN-response-from-chatgpt-<topic>.md`
4. Mavis reads the response, implements findings (per Walter's approval for the batch)
5. Mavis appends "Status" section to track what was implemented
6. Mavis commits changes + updates this MD's Status section
