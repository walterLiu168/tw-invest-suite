# ChatGPT Debug → Mavis (Coder) Workflow

> **Roles**:
> - **ChatGPT = manager / debugger / advisor** — 看完 code 找問題、給建議
> - **Mavis = coder / implementer** — 讀 MD 建議，動手 implement

---

## File Naming

```
docs/chatgpt_debug/YYYY-MM-DD-NN-short-topic.md
```

- `YYYY-MM-DD` — date
- `NN` — 流水號 (01, 02, ...)
- `short-topic` — 英文短描述 (例: `wizard-persona-broken`, `cron-stale-finmind`)

範例：
- `2026-09-03-01-full-project-review.md`
- `2026-09-04-01-finhedge-news-cache.md`

---

## MD 結構（ChatGPT 寫）

```markdown
# 標題 (簡短描述問題)

> Submitted: 2026-09-03 by ChatGPT
> Status: pending  ← 由 Mavis 改成 done / partial / skipped
> Scope: full-project | chips.html | cron | db | scripts

## Context
- 看了哪些檔（清單）
- 觀察到什麼問題（error log / 截圖 / 數據）
- 為什麼這是問題（影響範圍）

## Findings
### F1. <short title>
- File: public/chips.html:1234
- Issue: 這個 function 會 throw null.addEventListener error
- Suggested fix: 把 syncUI() 改為 noop 或 guard with `if (el)`
- Priority: high | mid | low

### F2. ...

## Out of Scope
- (optional) ChatGPT 看了但沒進來的東西

---

## Status  ← Mavis 加這 section

| # | Status | Commit | Notes |
|---|--------|--------|-------|
| F1 | ✅ done | aef9e0b | stubbed syncUI() |
| F2 | 🟡 partial | aef9e0b | 修了一半，剩 edge case |
| F3 | ❌ skipped | - | out of scope, file in different repo |
```

---

## Mavis Behavior

1. **每次對話開始**：自動 scan `docs/chatgpt_debug/` 找 `Status: pending` 的 MD
2. 列出清單，問 user 要先 implement 哪個（或全部）
3. 實作 → commit + push
4. 更新原 MD 的 `## Status` section 標 ✅ / 🟡 / ❌
5. 在對話裡 inline 簡短回報

---

## Quick Commands

```powershell
# 列出所有 pending MD
Get-ChildItem C:\Users\icemo\Projects\tw-invest-suite\docs\chatgpt_debug\*.md | 
  Select-String "Status: pending" -SimpleMatch

# 開最新 MD
notepad (Get-ChildItem C:\Users\icemo\Projects\tw-invest-suite\docs\chatgpt_debug\*.md -File |
  Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
```

---

## Related Docs

- `docs/handoff_chatgpt.md` — 完整 handoff doc (project overview, schemas, crons)
- `docs/decision-log.md` — D001-D035 設計決策
- `docs/architecture.md` — 8 頁面 + DB + cron 架構
