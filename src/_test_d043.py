#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D043 wizard 3 步 + persona cards 重排 + 風格標籤"""
from playwright.sync_api import sync_playwright

URL = 'https://groovelab.dev/chips.html#wizard'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={'width': 1400, 'height': 1200})
    page = ctx.new_page()
    page.goto(URL, wait_until='networkidle', timeout=40000)
    page.wait_for_timeout(3000)
    page.evaluate("localStorage.removeItem('tank-akali-active-persona-v1')")
    page.reload(wait_until='networkidle')
    page.wait_for_timeout(3000)

    # Take initial screenshot - 16 cards with tags
    page.screenshot(path='_d043_01_initial.png', full_page=True)

    # Verify card order
    cards = page.evaluate("""Array.from(document.querySelectorAll('.persona-card')).map(c => ({
        persona: c.getAttribute('data-persona'),
        name: c.querySelector('.name').textContent,
        tags: Array.from(c.querySelectorAll('.tags span')).map(t => t.textContent)
    }))""")
    print('=== Card order ===')
    for i, c in enumerate(cards):
        print(f'  {i+1:2d}. [{c["persona"]:10}] {c["name"]:8} tags={c["tags"]}')

    # Open wizard via newbie card
    page.evaluate("if (typeof showWizard === 'function') showWizard();")
    page.wait_for_timeout(800)
    page.screenshot(path='_d043_02_wizard_step1.png', full_page=False)
    print('=== Step 1 ===')
    print('Title:', page.evaluate("document.getElementById('wiz-title').textContent"))
    print('Sub:', page.evaluate("document.getElementById('wiz-sub').textContent"))
    print('Step num:', page.evaluate("document.getElementById('wiz-step-num').textContent"))
    print('Total steps:', page.evaluate("getWizardSteps().length"))

    # Select 看多
    page.evaluate("""
      const opts = document.querySelectorAll('#wiz-options .wizard-opt');
      for (const o of opts) if (o.textContent.includes('看多')) o.click();
    """)
    page.wait_for_timeout(300)
    page.click('#wiz-next')
    page.wait_for_timeout(500)
    page.screenshot(path='_d043_03_wizard_step2.png', full_page=False)
    print('=== Step 2 ===')
    print('Title:', page.evaluate("document.getElementById('wiz-title').textContent"))
    print('Sub:', page.evaluate("document.getElementById('wiz-sub').textContent"))

    # Select 短線
    page.evaluate("""
      const opts = document.querySelectorAll('#wiz-options .wizard-opt');
      for (const o of opts) if (o.textContent.includes('短線')) o.click();
    """)
    page.wait_for_timeout(300)
    page.click('#wiz-next')
    page.wait_for_timeout(500)
    page.screenshot(path='_d043_04_wizard_step3.png', full_page=False)
    print('=== Step 3 (recommend) ===')
    print('Title:', page.evaluate("document.getElementById('wiz-title').textContent"))
    print('Sub:', page.evaluate("document.getElementById('wiz-sub').textContent"))
    recs = page.evaluate("""Array.from(document.querySelectorAll('#wiz-options .wizard-recommend-card')).map(c => ({
        persona: c.getAttribute('data-persona'),
        name: c.querySelector('.name').textContent
    }))""")
    print('Recommended cards:', recs)

    # Click first recommended card
    page.evaluate("document.querySelector('#wiz-options .wizard-recommend-card').click()")
    page.wait_for_timeout(1500)
    page.screenshot(path='_d043_05_after_recommend.png', full_page=False)
    print('=== After recommend click ===')
    print('Wizard hidden:', page.evaluate("document.getElementById('wizard').hidden"))
    print('Active persona:', page.evaluate("document.querySelector('.persona-card.active')?.getAttribute('data-persona')"))
    print('Intention:', page.evaluate("document.getElementById('sum-intention').textContent"))
    print('Apply count:', page.evaluate("document.getElementById('sum-cnt').textContent"))
    browser.close()
