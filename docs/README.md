# tw-invest-suite 文件中心

文件版本：2026-09-21
文件責任人：Project Manager / Release Owner
適用範圍：`C:\Users\icemo\Projects\tw-invest-suite` 的 canonical 原始碼、Windows Scheduler、公開報告與 Telegram 發布鏈。

## 先讀哪一份

| 讀者 | 入口 |
|---|---|
| 公開使用者 | [Public Release Manual](public-release-manual.md) |
| 值班／維運人員 | [Operations and Maintenance Guide](operations-maintenance.md) |
| 開發者、架構審查者 | [System Design Book](system-design-book.md) |
| 接手的 AI agent 或工程師 | [Python Code Reference](python-code-reference.md) |
| 發布負責人 | [Public Release Checklist](public-release-checklist.md) |
| 法務／依賴審查 | [Third-party notices](third-party-notices.md) |

## 現況摘要

截至 2026-09-19，D056-3 報告窗口已完成一次完整的端到端認證：

- `nightly_id=51fa87e75ca748b28f3bc4921901bae4`
- `data_date=2026-09-18`、`run_id=25`
- `1,974` renders、`1,937` fresh、`2,035` artifacts、`50` all-report artifacts
- required stages 全部成功，`degraded_stages=0`
- GitHub Pages、Groove `2038/2038`、Telegram chips `message_id=1397` 均已驗證
- `pipeline_state.py verify`、`final_acceptance_summary.py`、compile audit 通過

這是「目前本機部署的營運認證」，不是表示整個資料倉儲所有 240 個物件或所有歷史年份都已統計驗證。公開發布前仍須完成 [Public Release Checklist](public-release-checklist.md) 的安全與可部署性項目。

## 文件與程式的來源邊界

1. **Canonical repository**：`C:\Users\icemo\Projects\tw-invest-suite`
2. **Scheduler/runtime mirror**：`C:\Users\icemo\.claude\skills\tw-invest-suite\scripts`
3. **Public site workspace**：`C:\Groove-Lab`
4. **AI-Telegram/OpenAlice**：`D:\CODEX\AI-Telegram`
5. **歷史 scratch/debug**：`scripts\_debug`、`src\_*.py`、repo 根目錄 `_*.py`；不得註冊成 production task。

文件中的命令只以目前已認證的入口為準。舊文件若與本文件衝突，以本文件與最新的 `_codex-work-state` 證據為準。

## 證據索引

- [Data and code integrity audit](../.codex-work-state/data-code-integrity-audit-20260919.md)
- [Self-complete status](../.codex-work-state/self-complete-status.md)
- [Pipeline contract](pipeline-reference.md)
- [Historical decision log](decision-log.md)
- [Historical debug/handoff archive](chatgpt_debug/README.md)

## 文件更新規則

- 每次改變 stage、排程、資料契約、發布目標或 Telegram idempotency，都要同步更新 Design Book、Operations Guide、Python Code Reference。
- 每次新認證都要記錄 `nightly_id`、`data_date`、`run_id`、artifact count、remote verification、Telegram message id。
- 不在公開文件寫入 token、密碼、chat id、cookie、私有 URL 或本機使用者名稱以外的秘密。
- 舊內容保留作為決策與事故歷史，但必須標為 historical，不能當成目前安裝指示。
