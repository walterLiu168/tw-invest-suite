# T4 Health-Check 編碼修正報告

**日期**: 2026-09-11  
**狀態**: 全部 4 議題 done

---

## 議題清單與最終結果

| 議題 | 解法 | 最終驗證 |
|---|---|---|
| T1 23:50 publish 撞 daily-report | schedule 改 00:30 daily | `Get-ScheduledTask tw-invest-suite-publish` StartBoundary = 2026-09-11T00:30:00+08:00 ✓ |
| T2 manifest build 失敗 | 看 `publish_ghpages_20260910_235002.log` 找 root cause | T1 修了 race；9/10 manifest 6,150 bytes 9/11 09:55:27 寫入；GitHub Pages 9/10 data 1.7MB 200 OK ✓ |
| T3 Stage 5 margin_scan 15min 不夠 | runtime 改 180m | `run_daily.ps1:294` `To=180*60`；runtime SHA == git SHA `b43c8466...` ✓ |
| T4 health-check 仍 1 | **schtasks output encoding 自動偵測** | manual + cron 雙跑 rc=0 ✓ |

---

## T4 Root Cause (9/11 investigation)

### 現象
- health-check 從 interactive session 跑：`rc=0`，所有 task state=Ready
- health-check 從 Task Scheduler context 跑：`rc=1`，所有 13 個 task `state='?'` 或 `state='MISSING'`
- 同一個 Python 3.14.5、同一個 script、同一個 working_dir

### 真因
**schtasks /Query 輸出 encoding 依 calling context 而定**：
- Interactive PowerShell：英文 labels (`Status:`, `Last Run Time:`) + UTF-8 bytes
- Task Scheduler context (schtasks 透過 service 啟動)：繁體中文 labels (`狀態:`, `上次執行時間:`, `上次結果:`) + cp950 bytes

舊 parser 只認英文 labels。Task Scheduler context 的中文 labels 透過 utf-8 decode 後變成 mojibake (`嚙踝蕭嚙?`)，`line.startswith("Status:")` 永遠 False → `info["state"]` 留在初始值 `?` → 所有 task 被標 `NOT READY (?)` → 13 個 failure → `rc=1`。

### Debug 證據
從 T4 debug log (cron 11:06:06 run, rc=1):
```
RAW schtasks[OpenAlice ExDividend 1335] err='missing Status: (out_len=1564)'
  out_first_500='\n嚙踝蕭嚙? \\\n嚙瘩嚙踝蕭嚙磕嚙踝蕭:  DESKTOP-5LONC19\n
  嚙線嚙瑾嚙磕嚙踝蕭:  \\OpenAlice ExDividend 1335\n
  嚙磊嚙踝蕭嚙踝蕭嚙踝蕭伅嚙?  2026/9/11 嚙磊嚙踝蕭 01:35:00\n
  嚙踝蕭嚙璀:  嚙瞇嚙踝蕭\n...'
```
- `嚙踝蕭嚙?` = mojibake of 狀態 (Status)
- `嚙磊嚙踝蕭` = mojibake of 上午/下午
- `嚙瞇嚙踝蕭` = mojibake of 就緒 (Ready)

### 修正
1. **`_detect_schtasks_encoding()`**: 第一次呼叫 schtasks probe，用 utf-8 → cp950 → big5 → mbcs → cp936 順序試 decode，**找到含 `Status:` 或 `狀態:` 的 encoding 就 cache**。
2. **`get_task_info()`**: 用 probe 決定的 encoding decode 後，**同時認英文與中文 labels** (`Status:` / `狀態:`, `Last Run Time:` / `上次執行時間:`, `Last Task Result:` / `上次結果:`)。
3. **State 判斷加中文值**: `info["state"] not in ("Ready", "Running", "就緒", "執行中", "正在執行", "Running.")`
4. **保留 retry 機制**: 2 次 retry × 8s timeout，遇到 UnicodeDecodeError 自動重 probe。

### 驗證
- **Manual** (interactive PowerShell from `_debug/` dir, 11:13): `rc=0`, duration=27s, failures=0
- **Cron** (Start-ScheduledTask, 11:11:11 → 11:12:07): `LastTaskResult=0` ✓
- **Cron 第二次** (next daily 23:00): schedule 不變，per-process encoding cache 在每次 invoke 重置（每次都是新 process），每次 probe 都會命中

---

## Runtime ↔ Git Sync

| File | runtime SHA | git SHA | match |
|---|---|---|---|
| `scripts/_debug/check_openalice_health.py` | `F92CE9BEC921C06B3EC1228C8EB3CC5993A158535A07A847DA35C9FD461A4602` | `F92CE9BEC921C06B3EC1228C8EB3CC5993A158535A07A847DA35C9FD461A4602` | ✓ |

514 lines runtime 已同步到 git。

---

## 待 follow-up

- [ ] 9/11 23:00 health-check 觀察 — 應 rc=0
- [ ] 9/12 00:05 postflight 觀察 — canonical_fails 應降至 0 (T1 schedule fix)
- [ ] 9/12 00:30 publish 觀察 — 第一個 D054-contracted nightly
