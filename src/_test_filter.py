"""D032 Test: 驗證 chips.html filter 面板工作正常"""
from playwright.sync_api import sync_playwright
import time

URL = "http://localhost:8765/chips.html"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    console_msgs = []
    page.on("console", lambda msg: console_msgs.append(f"[{msg.type}] {msg.text}"))
    page.on("pageerror", lambda err: console_msgs.append(f"[ERROR] {err}"))
    page.goto(URL, wait_until="networkidle", timeout=15000)
    time.sleep(2)

    print("=== Page loaded ===")
    print("Title:", page.title())

    # 1. 確認 filter 面板存在 (但 hidden)
    panel = page.locator("#filter-panel")
    is_hidden = panel.is_hidden()
    print(f"\n[1] Filter panel hidden by default: {is_hidden}")

    # 2. 點擊展開
    page.locator("#filter-toggle-btn").click()
    time.sleep(0.5)
    is_hidden_after = panel.is_hidden()
    print(f"[2] After click, panel hidden: {is_hidden_after}")

    # 3. 確認概念 chips 數量
    concept_chips = page.locator('.fchip[data-tag="concept"]').count()
    preset_chips = page.locator('.fchip[data-preset]').count()
    industry_options = page.locator("#filter-industry option").count()
    print(f"[3] Concept chips: {concept_chips}, Preset chips: {preset_chips}, Industries: {industry_options}")

    # 4. 點一個概念 chip (半導體)
    page.locator('.fchip[data-val="半導體"]').click()
    time.sleep(0.3)
    cnt_text = page.locator("#filter-cnt").text_content()
    match_text = page.locator("#match-cnt").text_content()
    print(f"[4] After click 半導體: filter count={cnt_text}, match count={match_text}")

    # 5. 確認 card 有被隱藏
    visible_cards = page.locator('.tab-content.active .card:visible').count()
    hidden_cards = page.locator('.tab-content.active .card:not(:visible)').count()
    print(f"[5] Visible cards: {visible_cards}, Hidden cards: {hidden_cards}")

    # 6. 加 OR 模式
    page.locator('#mode-toggle button[data-mode="OR"]').click()
    time.sleep(0.3)
    match_text_or = page.locator("#match-cnt").text_content()
    print(f"[6] After OR mode, match count: {match_text_or}")

    # 7. 加 5 日外資 ≥ 100 億
    page.locator("#adv-toggle").click()
    time.sleep(0.3)
    page.locator("#adv-add").click()
    time.sleep(0.3)
    # Field 1 已是 5 日外資 (張). 改 op 為 >=
    page.locator('.adv-cond:nth-of-type(1) select[data-k="op"]').select_option('>=')
    page.locator('.adv-cond:nth-of-type(1) input[data-k="value"]').fill('100000000')
    time.sleep(0.3)
    match_text_adv = page.locator("#match-cnt").text_content()
    print(f"[7] After 5d_外 >= 100000000 張, match count: {match_text_adv}")

    # 8. 切換 tab 看 filter 是否還在套用
    page.locator('.tab[data-tab="all-sell"]').click()
    time.sleep(0.3)
    sell_match = page.locator("#match-cnt").text_content()
    sell_visible = page.locator('.tab-content.active .card:visible').count()
    print(f"[8] Switch to all-sell tab: match={sell_match}, visible cards={sell_visible}")

    # 9. 切換到法人分項深度
    page.locator('.tab[data-tab="depth"]').click()
    time.sleep(0.3)
    depth_visible = page.locator('.tab-content.active .depth-row:not(.depth-head):visible').count()
    print(f"[9] Switch to depth tab: visible rows={depth_visible}")

    # 10. 清除全部
    page.locator("#filter-clear").click()
    time.sleep(0.3)
    cnt_after_clear = page.locator("#filter-cnt").text_content()
    print(f"[10] After clear: filter count={cnt_after_clear}")

    # 11. 截圖
    page.screenshot(path="C:/Users/icemo/Projects/tw-invest-suite/src/_filter_test.png", full_page=False)
    print("\n=== Screenshot saved ===")

    # 12. localStorage 檢查
    saved = page.evaluate("() => localStorage.getItem('tank-akali-filters-v1')")
    print(f"[12] localStorage saved: {saved}")

    print("\n=== Console messages ===")
    for m in console_msgs[:20]:
        print(" ", m)

    browser.close()
print("=== Done ===")
