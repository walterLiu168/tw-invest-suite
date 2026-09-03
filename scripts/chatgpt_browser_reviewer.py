#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chatgpt_browser_reviewer.py — D050b
Mavis ↔ ChatGPT via Playwright browser automation. 每次 commit 完：
  1. 開 Chrome with persistent user-data-dir (保留 ChatGPT 登入 session)
  2. 自動 navigate 到 chatgpt.com
  3. 自動把 prompt 填入新對話 textarea
  4. submit (按 Enter)
  5. 等 response 完成
  6. 複製 response → 寫 MD 到 docs/chatgpt_debug/
  7. status=pending 給 Mavis 下次對話 implement

需要 user 一次手動登入 chatgpt.com（session cookie 會存到 profile dir）。
"""
import os
import sys
import json
import subprocess
import time
import re
from pathlib import Path
from datetime import date, datetime

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("ERROR: playwright not installed. pip install playwright")
    sys.exit(1)

REPO = Path(r"C:\Users\icemo\Projects\tw-invest-suite")
DEBUG_DIR = REPO / "docs" / "chatgpt_debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)
PROFILE_DIR = Path(r"C:\Users\icemo\.mavis\chatgpt_profile")
PROFILE_DIR.mkdir(parents=True, exist_ok=True)

CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"


def get_last_commit():
    r = subprocess.run(["git", "log", "-1", "--format=%H%n%s"],
                       cwd=str(REPO), capture_output=True, text=True, encoding='utf-8')
    lines = r.stdout.strip().split("\n", 1)
    if len(lines) < 2:
        return None, None
    return lines[0], lines[1]


def get_diff(commit):
    r = subprocess.run(["git", "show", commit, "--format=", "--stat"],
                       cwd=str(REPO), capture_output=True, text=True, encoding='utf-8')
    stat = r.stdout
    r = subprocess.run(["git", "show", commit, "--format="],
                       cwd=str(REPO), capture_output=True, text=True, encoding='utf-8')
    diff = r.stdout
    if len(diff) > 25000:
        diff = diff[:25000] + "\n\n... (truncated)"
    return stat, diff


def build_prompt(short_sha, subject, stat, diff):
    return f"""你是 ChatGPT，幫我 review 一個台股分析平台 (tw-invest-suite) 的 commit。

# Context
- Project: C:\\Users\\icemo\\Projects\\tw-invest-suite
- 1,962 tickers, 16 persona cards, 3-step wizard
- MySQL tw_elec / 5 個關鍵 tables
- 詳見 docs/handoff_chatgpt.md

# Commit {short_sha}: {subject}
```
{stat}
```
```
{diff}
```

# 任務
找出這個 commit 的問題 / risks / 沒考慮到的 edge case，給具體實作步驟 (Mavis 直接改)。
Priority: high | mid | low。

# 輸出格式（只回 markdown, 不要前言後語）
```markdown
# <short title>

> Submitted: {date.today().isoformat()} by ChatGPT (auto via Playwright)
> Commit: {short_sha}
> Status: pending
> Scope: chips.html | cron | db | scripts | full-project

## Context
<看了哪些, 觀察到什麼>

## Findings
### F1. <title>
- File: <path>:<line>
- Issue: <具體問題>
- Suggested fix: <實作步驟>
- Priority: high | mid | low

## Out of Scope
- ...

## Status
*(Mavis 會 append 實作結果)*
```
"""


def next_seq():
    today = date.today().strftime("%Y-%m-%d")
    existing = list(DEBUG_DIR.glob(f"{today}-*.md"))
    return f"{today}-{len(existing) + 1:02d}"


def run_with_chrome(commit_sha, short_sha, subject, stat, diff, browser_path):
    """Use Playwright with system Chrome (or Edge) + persistent profile."""
    prompt = build_prompt(short_sha, subject, stat, diff)
    print(f"[chatgpt] opening {browser_path} with profile {PROFILE_DIR}")
    with sync_playwright() as p:
        # launch_persistent_context keeps the user-data-dir between runs.
        browser = p.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            executable_path=browser_path,
            headless=False,  # need visible to user for first-time login
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
            ],
            viewport={"width": 1280, "height": 800},
        )
        # If first time (no login), prompt user to log in manually
        page = browser.pages[0] if browser.pages else browser.new_page()
        page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=30000)
        # Check if logged in
        time.sleep(3)
        if "login" in page.url.lower() or "auth" in page.url.lower():
            print("\n[chatgpt] NOT LOGGED IN. Please log in to chatgpt.com in the browser window.")
            print("[chatgpt] After login, the script will continue automatically (press Enter in this terminal).")
            input("[chatgpt] Press Enter here when logged in...")
        # Navigate to fresh chat
        page.goto("https://chatgpt.com/?model=auto", wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        # Find the prompt textarea
        # New ChatGPT UI uses contenteditable div with id="prompt-textarea"
        try:
            page.wait_for_selector("#prompt-textarea", timeout=10000)
            page.click("#prompt-textarea")
        except Exception:
            try:
                page.wait_for_selector("[contenteditable='true']", timeout=10000)
                page.click("[contenteditable='true']")
            except Exception as e:
                print(f"ERROR: could not find prompt textarea: {e}")
                browser.close()
                return None
        # Type prompt (use insertText for contenteditable)
        page.keyboard.insert_text(prompt)
        time.sleep(1)
        # Submit (press Enter)
        page.keyboard.press("Enter")
        print("[chatgpt] prompt sent, waiting for response...")
        # Wait for response to complete
        # Strategy: wait for "Regenerate" button or stop button to disappear
        last_text = ""
        for i in range(60):  # up to 5 min
            time.sleep(5)
            try:
                # Get all assistant messages
                msgs = page.query_selector_all("[data-message-author-role='assistant']")
                if msgs:
                    txt = msgs[-1].inner_text()
                    if txt == last_text and len(txt) > 200 and "Regenerate" in page.content():
                        # Response stable
                        break
                    last_text = txt
            except Exception:
                pass
        # Final extract
        msgs = page.query_selector_all("[data-message-author-role='assistant']")
        response = msgs[-1].inner_text() if msgs else ""
        browser.close()
        if not response:
            print("[chatgpt] no response extracted")
            return None
        return response


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--self-check":
        print("OK: chatgpt_browser_reviewer.py loaded")
        print(f"  Chrome: {CHROME} ({'OK' if Path(CHROME).exists() else 'MISSING'})")
        print(f"  Edge: {EDGE} ({'OK' if Path(EDGE).exists() else 'MISSING'})")
        print(f"  Profile: {PROFILE_DIR}")
        print(f"  Playwright: OK" if True else "MISSING")
        return 0

    commit, subject = get_last_commit()
    if not commit:
        print("No commit found")
        return 1
    short_sha = commit[:8]
    stat, diff = get_diff(commit)
    if not diff.strip():
        print("Empty diff — nothing to review")
        return 0

    # Use Chrome (or fallback to Edge)
    browser_path = CHROME if Path(CHROME).exists() else EDGE
    print(f"[chatgpt] reviewing commit {short_sha}: {subject[:60]}")
    response = run_with_chrome(commit, short_sha, subject, stat, diff, browser_path)
    if not response:
        return 1

    # Write MD
    seq = next_seq()
    # Try to extract title from response
    title_line = response.split("\n", 1)[0].lstrip("# ").strip()[:50] or "auto-review"
    slug = re.sub(r'[^a-z0-9]+', '-', title_line.lower())[:30].strip('-') or "auto"
    out = DEBUG_DIR / f"{seq}-auto-{short_sha}-{slug}.md"
    out.write_text(response, encoding='utf-8')
    print(f"OK: wrote {out.name} ({len(response)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
