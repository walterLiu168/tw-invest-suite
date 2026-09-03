Browser reviewer URL 與 session workflow 有阻斷性問題

Submitted: 2026-09-03 by ChatGPT (auto via Playwright)
Commit: 7dae8028
Status: pending
Scope: scripts | full-project

Context

Review 範圍為 commit 7dae8028 的 scripts/chatgpt_browser_reviewer.py 與 docs/handoff_chatgpt.md。

主要檢查：

Playwright persistent Chrome 啟動流程

ChatGPT login/session 保存

prompt navigation / submission

response completion detection

assistant response extraction

git diff 蒐集與 truncation

debug review 檔案命名與併發安全

failure handling / exit code

security 與長期可維護性

目前最大問題不是 review prompt 本身，而是 browser automation 有一個會直接阻止程式正常執行的 URL bug，另外 completion detection、login detection、persistent profile 與輸出 atomicity 也不足以支撐「每次 commit 自動 reviewer」這個用途。

Findings
F1. page.goto() 使用了 Markdown link，而不是 URL

File: scripts/chatgpt_browser_reviewer.py:111,124

Issue: 程式目前是：

page.goto("[https://chatgpt.com/](https://chatgpt.com/)", ...)

以及：

page.goto("[https://chatgpt.com/?model=auto](https://chatgpt.com/?model=auto)", ...)

這是 Markdown hyperlink syntax，不是合法 URL。Playwright 不會替它解析成 https://chatgpt.com/，因此 D050 在實際 browser run 很可能直接於 navigation 階段失敗。--self-check 也完全抓不到這個問題，所以目前 self-check PASS 並不代表 reviewer 可用。

Suggested fix:

改成：
page.goto("https://chatgpt.com/", ...)

fresh chat 同樣使用真正 URL，例如：
page.goto("https://chatgpt.com/", ...)

不要依賴 ?model=auto 作為「新對話」或 model selection contract；ChatGPT Web routing 屬於 UI implementation detail。

增加 bounded smoke test，至少真正啟動 browser 並驗證：

navigation 成功

hostname 是 chatgpt.com

prompt composer 能找到

--self-check 增加 URL constant validation，避免 Markdown/非法 scheme 再次被提交。

Priority: high

F2. Login detection 會把「未登入但停留在首頁」誤判成已登入

File: scripts/chatgpt_browser_reviewer.py:114-122

Issue: 現在只透過：

if "login" in page.url.lower() or "auth" in page.url.lower():

判斷是否登入。

ChatGPT 未登入狀態不一定會 redirect 到帶有 login / auth 的 URL；使用者可能仍停留在 chatgpt.com landing page。因此 script 可以錯誤認為已登入，然後繼續找 #prompt-textarea，最後以「找不到 textarea」這種錯誤結束，而不是正確提示 login。

此外，使用者完成登入後按 Enter，程式也沒有重新驗證 authenticated state。

Suggested fix:

不以 URL 作唯一 login signal。

建立 is_chat_ready(page)，以實際 composer 是否可用為主要 contract。

如果 composer 不存在，再偵測 login/signup UI。

手動登入後必須再次：

wait_for_load_state()

reload/navigate ChatGPT

wait_for_selector("#prompt-textarea")

若仍不存在，fail closed，回傳明確錯誤：
AUTH_OR_UI_NOT_READY

不要進入 submit 階段。

Priority: high

F3. Response completion 判定非常 brittle，可能提前擷取半份 answer 或固定等滿五分鐘

File: scripts/chatgpt_browser_reviewer.py:151-169

Issue: completion condition 是：

txt == last_text and len(txt) > 200 and "Regenerate" in page.content()

有數個問題：

response streaming 暫停五秒不代表已完成；

"Regenerate" 是 UI 文案，不是穩定 API contract；

UI 語言不同時可能沒有英文 Regenerate；

DOM 裡其他位置出現相同文字也可能造成 false positive；

ChatGPT UI 改版後 selector/text 即失效；

若 Regenerate 不存在，即使 answer 早已完成也會等完整 300 秒；

timeout 後程式仍直接把最後看到的文字當成功結果，不知道回答是否完整。

這會污染 docs/chatgpt_debug：partial answer 仍被標成正常 pending review。

Suggested fix:

封裝 wait_for_response_complete(page)。

submission 後先確認 assistant message 出現，而不是直接 polling。

優先觀察 generation/stop control 的「存在 → 消失」生命週期。

同時要求 assistant text 在連續數次 observation 中穩定，例如 3 次 × 2 秒。

設定明確 deadline。

deadline 到期時回傳 structured failure，不寫正式 review：
RESPONSE_TIMEOUT

若希望保留 partial response，寫 .partial.md，不可冒充正常 review。

Priority: high

F4. 沒有確認 prompt 是否真的成功送出

File: scripts/chatgpt_browser_reviewer.py:141-149

Issue: script 使用：

page.keyboard.press("Enter")

後就直接顯示：

[chatgpt] prompt sent

但沒有任何 post-condition。

ChatGPT composer 的 Enter 行為可能受到 UI、IME、focus、modal、附件狀態或未完成頁面載入影響。若 Enter 沒有 submit，程式仍會等待五分鐘，甚至可能擷取頁面上既有 assistant message。

Suggested fix:

在 insert 後確認 composer 包含預期 prompt fingerprint。

優先定位 send button 並 click；Enter 只作 fallback。

submit 後驗證：

composer 被清空，或

新 user message 出現在 conversation DOM。

為 prompt 產生 unique marker，例如：
Review-ID: 7dae8028-<timestamp>

必須確認 DOM 中最新 user message 包含 marker 才進入 response wait。

Priority: high

F5. 可能擷取到舊 conversation 的 assistant message

File: scripts/chatgpt_browser_reviewer.py:151-171

Issue: 最後直接：

msgs[-1]

取頁面最後一個 assistant message，但程式沒有建立 conversation baseline。

若：

navigation 沒建立真正 fresh chat；

submission 失敗；

previous chat 被 restore；

ChatGPT SPA 保留舊 state；

reviewer 就可能把舊 assistant 回答當成這個 commit 的 review。

Suggested fix:

submit 前記錄 assistant_count_before。

submit 後要求：
assistant_count_after > assistant_count_before

只接受這次新增的 assistant element。

同時確認本次 user prompt marker。

若沒有新增 assistant response，回傳 failure，不寫 .md。

Priority: high

F6. Persistent browser profile 是高價值 authentication state，但文件沒有安全邊界

File: scripts/chatgpt_browser_reviewer.py:32-33; docs/handoff_chatgpt.md:190-195

Issue: C:\Users\icemo\.mavis\chatgpt_profile 保存的是可持續登入 ChatGPT 的 browser profile。

文件只寫「session 保留」，卻沒有說明這是敏感 authentication state，也沒有 lifecycle / ACL / backup / git / log boundary。

如果 .mavis 被同步、備份、其他 process 掃描、錯誤 commit 或分享出去，風險高於一般 application cache。

Suggested fix:

handoff 明確標註：
chatgpt_profile = sensitive local auth state; never commit/copy/upload.

啟動時確認 profile 不位於 repo 內。

最少驗證 Windows directory ownership / permissions。

不把 cookie、local storage、profile dump 寫入 debug log。

提供 --reset-profile，只在 user 明確要求時刪除 local session。

README 加入 logout/revocation procedure。

Priority: high

F7. --no-sandbox 不應作為正常 Chrome automation 預設值

File: scripts/chatgpt_browser_reviewer.py:104-108

Issue: browser args 包含：

--no-sandbox

此 reviewer 會開啟外部網站，而且 persistent profile 內包含登入狀態。沒有證據顯示這個 Windows Desktop workflow 必須停用 Chrome sandbox，因此沒有必要降低 browser isolation。

--disable-blink-features=AutomationControlled 也不是 reviewer 功能所必要；它增加對 ChatGPT Web implementation 的耦合，並讓 automation 看起來刻意隱藏 automated state。

Suggested fix:

移除 --no-sandbox。

移除 --disable-blink-features=AutomationControlled。

移除非必要 --disable-infobars。

只保留有具體 compatibility evidence 的 browser args。

若未來某 environment 真需要特殊 flag，改成 explicit CLI opt-in，而非 global default。

Priority: high

F8. Chrome/Edge 都不存在時仍會選擇不存在的 Edge path

File: scripts/chatgpt_browser_reviewer.py:201-203

Issue:

browser_path = CHROME if Path(CHROME).exists() else EDGE

只檢查 Chrome。若 Chrome 不存在，無論 Edge 是否存在都直接使用 Edge path。

--self-check 雖然會顯示 MISSING，但正常 execution 不會 fail early。

Suggested fix:

建立 find_browser()：

Chrome exists → Chrome

else Edge exists → Edge

else raise controlled error

main return non-zero：
BROWSER_NOT_FOUND

可考慮 Windows 常見 Chrome x86/x64 路徑，但不要無限制 filesystem scan。

Priority: mid

F9. Git subprocess 完全沒有檢查 return code

File: scripts/chatgpt_browser_reviewer.py:42-65

Issue: get_last_commit() / get_diff() 只讀 stdout，沒有：

check=True

return code validation

stderr reporting

Git executable missing、repo path錯誤、bad object、repository corruption 等都可能最後被錯誤呈現成 No commit found 或 Empty diff。

更嚴重的是 Empty diff — nothing to review return 0，可能讓 scheduler/Mavis 把實際 git failure 當成功。

Suggested fix:

寫共用 run_git(*args)。

驗證 returncode == 0。

stderr 做 bounded logging。

git failure → return non-zero。

將：

no commit

empty diff

git command failure

分成不同狀態。

Priority: mid

F10. 固定截斷前 25,000 characters 會系統性漏掉 diff 後半部

File: scripts/chatgpt_browser_reviewer.py:57-65

Issue:

diff = diff[:25000]

大 commit 只保留 patch 開頭，因此 reviewer 無法知道後面發生什麼，但 prompt 仍要求「review 這個 commit」。

這會產生 selection bias：git ordering 較前面的 files 會一直被 review，後面的 files 永遠看不到。對 future full-project review 特別危險。

Suggested fix:

不要 silent truncate。

prompt 明確標示：
Diff truncated: yes

先取得 git diff-tree --name-only，確保所有 changed files 都列入 Context。

對 patch 建立 bounded per-file budget，而不是全部額度給第一批 files。

大 commit 可拆成多個 review rounds：

part 1/N

part 2/N

最後再做 aggregation review。

至少將 truncation metadata 寫進 output，避免 Mavis 把它當 complete review。

Priority: mid

F11. next_seq() 有 collision / overwrite race

File: scripts/chatgpt_browser_reviewer.py:89-92,211-216

Issue:

len(existing) + 1

不是可靠 sequence generator。

例如已有：

2026-09-03-01.md

2026-09-03-03.md

len == 2，下一個又會算出 03。

兩個 reviewer 同時執行也可以取得同一 sequence。之後 write_text() 會直接覆寫既有檔案。

Suggested fix:

parse existing numeric sequence，使用 max(seq) + 1。

寫檔前使用 exclusive create：
open(..., "x", encoding="utf-8")

collision 時重新 allocate sequence。

更簡單可將 timestamp 加入 filename。

永遠不要 silent overwrite existing review artifact。

Priority: mid

F12. Response filename slug 對中文 title 幾乎永遠退化成 auto

File: scripts/chatgpt_browser_reviewer.py:212-215

Issue:

re.sub(r'[^a-z0-9]+', '-', title_line.lower())

只保留 ASCII a-z0-9。

此 workflow 明確使用繁體中文 prompt，因此 ChatGPT title 很可能是中文，結果大量 filename 都成為：

...-auto-7dae8028-auto.md

雖然 sequence 暫時避免部分 collision，但可讀性與 traceability 很差。

Suggested fix:

filename 不必依賴 LLM title。

建議固定：
<seq>-auto-<sha>.md

title 保留在 Markdown 文件內。

若真的需要 slug，可使用 Unicode-safe slugging，但不是必要 complexity。

Priority: low

F13. commit_sha parameter 沒有使用，介面已開始產生 drift

File: scripts/chatgpt_browser_reviewer.py:95

Issue: run_with_chrome(commit_sha, short_sha, ...) 的 commit_sha 完全沒有被使用。

目前只是小問題，但對只有 229 lines 的新 script 已出現 dead parameter，代表 interface 與 implementation 沒同步收斂。

Suggested fix:

若不需要 full SHA，刪除 parameter。

或在 prompt metadata / tracing 中使用 full SHA。

配合 lint/static check 擋住 unused imports / arguments。

Priority: low

F14. 多個 imports 未使用，self-check 的 Playwright 判斷是假檢查

File: scripts/chatgpt_browser_reviewer.py:17-25,181-188

Issue: os, json, datetime 沒有使用。

更重要的是：

print(f" Playwright: OK" if True else "MISSING")

永遠輸出 OK。雖然 module import 失敗時 script 在頂部會直接退出，但這個 self-check code 本身仍是 misleading，也不能確認 browser executable actually launchable。

Suggested fix:

刪除 unused imports。

把 self-check 分成：

Python module import

repo exists / .git exists

browser executable exists

debug dir writable

profile dir writable

如果要稱作 browser self-check，應做 bounded launch/close smoke test。

Priority: low

F15. Browser exception 沒有統一處理，容易留下難以判讀的 crash

File: scripts/chatgpt_browser_reviewer.py:95-175

Issue: 目前只 catch prompt textarea lookup 相關 exception。

launch_persistent_context()、page.goto()、insert_text()、press()、final query_selector_all() 等任何一步出錯都可能直接 traceback。

同時 browser.close() 並沒有以 finally 保證執行。

對預期由 Mavis 自動呼叫的 reviewer，這不夠 deterministic。

Suggested fix:

run_with_chrome() 外層增加 try/finally。

browser.close() 放 finally。

不要 broad exception 全部吞掉；轉成 bounded error categories：

BROWSER_LAUNCH_FAILED

NAVIGATION_FAILED

AUTH_NOT_READY

COMPOSER_NOT_FOUND

SUBMIT_FAILED

RESPONSE_TIMEOUT

EXTRACTION_FAILED

stderr 顯示 category + 簡短原因。

所有 failure return non-zero。

Priority: mid

F16. 沒有防止 reviewer review 自己產生的 review commit，可能形成 feedback loop

File: scripts/chatgpt_browser_reviewer.py:190-207

Issue: script 永遠取 git log -1。

若未來 Mavis workflow 是：

commit code

ChatGPT review

寫 docs/chatgpt_debug/*.md

Mavis implement

commit review/debug artifact

reviewer 再自動 trigger 時，很可能開始 review docs/chatgpt_debug 自己，而不是 application change，甚至形成連續自我 review。

D050 的 handoff 已描述「每次 commit 完」自動跑，因此這不是純理論 edge case。

Suggested fix:

reviewer 應接受 explicit commit SHA：
chatgpt_browser_reviewer.py --commit <sha>

automation caller 決定哪個 commit 要 review，不由 script 猜 HEAD。

加入 exclusion policy：

pure docs/chatgpt_debug/** commit → skip

reviewer-generated artifact commit → skip

在 output 記錄 full source commit SHA。

optional marker：
[skip-chatgpt-review]
供 maintenance commit 使用。

Priority: high

F17. 缺乏 duplicate/idempotency gate，同一 commit 可以被無限重複 review

File: scripts/chatgpt_browser_reviewer.py:190-216

Issue: 沒有先檢查 7dae8028 是否已存在 review。

retry、manual rerun、scheduler duplicate invocation 都會送出新的 ChatGPT conversation 並產生新的 MD。

最後 Mavis 可能同時看到數份同 commit、不完全一致的 pending findings，不知道哪份 authoritative。

Suggested fix:

執行前搜尋：
*-auto-<short_sha>-*.md

default behavior：
已存在 successful review → skip。

只有 explicit --force 才重新 review。

force rerun 文件中加入：
Supersedes: <previous file>

最好以 full SHA 作 canonical identity，不只 8-char SHA。

Priority: mid

F18. 文件宣稱「自動 prompt + 讀 response + 寫 MD」過度描述目前可靠度

File: docs/handoff_chatgpt.md:190-195

Issue: handoff 現在描述成已完成能力：

session 保留

自動 prompt

讀 response

寫 MD

但目前沒有看到 browser integration test / bounded smoke evidence，而且實作還存在 F1 的 navigation blocker。

因此 documentation 把「implemented」與「validated」混為一談，後續 Mavis/Codex 可能錯誤假設 D050 已 production-ready。

Suggested fix:

在 F1-F5 修完並 smoke PASS 前改成：
experimental / local-only / browser-UI-dependent

增加 Validation 區塊：

self-check PASS

browser launch PASS

authenticated composer PASS

one prompt round-trip PASS

output MD PASS

明確寫：
ChatGPT Web UI selectors are not a stable API contract.

驗證完成後再標成 usable。

Priority: high

Out of Scope

沒有 review chips.html、wizard、16 persona cards 或 MySQL 五個關鍵 tables 的商業邏輯，因為本 commit 沒有修改它們。

沒有驗證 docs/chatgpt_debug/README.md 與 2026-09-03-01-full-project-review.md，因為未包含在本次 diff。

沒有實際啟動 Playwright/Chrome；以上為 commit-level static review。

沒有判斷 ChatGPT Web UI 未來 selector 是否會變更，只確認目前程式對 UI implementation detail 有高度耦合。

不建議 D050 現階段接到每次 commit 的 unconditional automation；至少先修 F1、F2、F3、F4、F5、F6、F7、F16，再跑一次真實 end-to-end smoke。

下一步適合由 Mavis 先做一個 D051: harden chatgpt_browser_reviewer 小 commit，只處理上述 high findings，不同時改 tw-invest-suite 主程式邏輯。

## Status

- ✅ **D051a** (commit `6cbd220`): F1 (URL), F2 (login), F4 (submit confirmation) done. F6/F7 deferred to README Security notes.
- 🟡 D051b/c remaining: F3 (stable-text completion), F5 (baseline assistant count), F8-F11, F15-F18.