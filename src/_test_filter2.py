"""D032 Test 2: 完整流程測試"""
from playwright.sync_api import sync_playwright
import time

URL = "http://localhost:8765/chips.html"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(URL, wait_until="networkidle", timeout=15000)
    time.sleep(2)

    # 1. 展開 + 點 半導體 + AI (OR within concepts)
    page.locator("#filter-toggle-btn").click()
    time.sleep(0.3)
    page.locator('.fchip[data-val="半導體"]').click()
    page.locator('.fchip[data-val="AI 概念股"]').click()
    time.sleep(0.3)
    print(f"[1] 選 半導體 + AI: filter count={page.locator('#filter-cnt').text_content()}, match={page.locator('#match-cnt').text_content()}")
    page.screenshot(path="C:/Users/icemo/Projects/tw-invest-suite/src/_filter_active.png", full_page=False)

    # 2. 加 preset 連買≥3天
    page.locator('.fchip[data-preset="streak3"]').click()
    time.sleep(0.3)
    print(f"[2] + 連買≥3天 (AND): match={page.locator('#match-cnt').text_content()}")

    # 3. 切到 OR
    page.locator('#mode-toggle button[data-mode="OR"]').click()
    time.sleep(0.3)
    print(f"[3] 改 OR: match={page.locator('#match-cnt').text_content()}")

    # 4. 切回 AND + 開進階 + 加條件: 5 日外資 > 0
    page.locator('#mode-toggle button[data-mode="AND"]').click()
    page.locator("#adv-toggle").click()
    time.sleep(0.3)
    page.locator("#adv-add").click()
    time.sleep(0.3)
    # 第一個欄位已是 5 日外資 張
    page.locator('.adv-cond:nth-of-type(1) select[data-k="op"]').select_option('>')
    page.locator('.adv-cond:nth-of-type(1) input[data-k="value"]').fill('0')
    time.sleep(0.3)
    print(f"[4] + 5日外>0張 (AND): match={page.locator('#match-cnt').text_content()}")
    page.screenshot(path="C:/Users/icemo\Projects/tw-invest-suite/src\_filter_adv.png", full_page=False)

    # 5. 儲存策略
    page.locator("#preset-name").fill("AI 半導體動能")
    page.locator("#preset-save").click()
    page.on("dialog", lambda d: d.accept())
    time.sleep(0.5)
    print(f"[5] Saved preset 'AI 半導體動能'")

    # 6. 清除
    page.locator("#filter-clear").click()
    time.sleep(0.3)
    print(f"[6] After clear: filter count={page.locator('#filter-cnt').text_content()}, match={page.locator('#match-cnt').text_content()}")

    # 7. 載入策略
    page.locator("#preset-load").select_option("AI 半導體動能")
    page.locator("#preset-load-btn").click()
    time.sleep(0.3)
    print(f"[7] After load preset: filter count={page.locator('#filter-cnt').text_content()}, match={page.locator('#match-cnt').text_content()}")

    # 8. 重新整理頁面 (localStorage 還原)
    page.reload(wait_until="networkidle")
    time.sleep(2)
    page.locator("#filter-toggle-btn").click()
    time.sleep(0.3)
    print(f"[8] After reload: filter count={page.locator('#filter-cnt').text_content()}, match={page.locator('#match-cnt').text_content()}")
    # 確認 半導體 chip 仍亮著
    semi_on = page.locator('.fchip[data-val="半導體"]').evaluate("el => el.classList.contains('on')")
    print(f"[8] 半導體 chip still highlighted: {semi_on}")

    # 9. localStorage dump
    saved = page.evaluate("() => localStorage.getItem('tank-akali-filters-v1')")
    print(f"[9] localStorage: {saved}")
    presets = page.evaluate("() => localStorage.getItem('tank-akali-presets-v1')")
    print(f"[9] presets: {presets}")

    browser.close()
print("=== Done ===")
