#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D042 wizard 4-step test via Playwright on groovelab.dev"""
from playwright.sync_api import sync_playwright

URL = 'https://groovelab.dev/chips.html#wizard'

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={'width': 1400, 'height': 1100})
    page = ctx.new_page()
    page.goto(URL, wait_until='networkidle', timeout=30000)
    page.wait_for_timeout(2500)
    # Clear any active persona first
    page.evaluate("localStorage.removeItem('tank-akali-active-persona-v1')")
    page.reload(wait_until='networkidle')
    page.wait_for_timeout(2500)
    # Click newbie persona card to open wizard
    page.evaluate("""if (typeof showWizard === 'function') showWizard();""")
    page.wait_for_timeout(800)
    page.screenshot(path='_d042_step1_persona.png', full_page=False)
    print('=== Step 1 (persona) ===')
    print('Title:', page.evaluate("document.getElementById('wiz-title').textContent"))
    print('Sub:', page.evaluate("document.getElementById('wiz-sub').textContent"))
    print('Step num:', page.evaluate("document.getElementById('wiz-step-num').textContent"))
    print('Total steps:', page.evaluate("getWizardSteps().length"))
    # capture options
    opts = page.evaluate("Array.from(document.querySelectorAll('#wiz-options .wizard-opt')).map(b => b.textContent)")
    print('Options:', opts)
    # Click first persona
    page.evaluate("document.querySelector('#wiz-options .wizard-opt').click()")
    page.wait_for_timeout(400)
    page.click('#wiz-next')
    page.wait_for_timeout(600)
    page.screenshot(path='_d042_step2_direction.png', full_page=False)
    print('=== Step 2 (direction) ===')
    print('Title:', page.evaluate("document.getElementById('wiz-title').textContent"))
    print('Sub:', page.evaluate("document.getElementById('wiz-sub').textContent"))
    print('Step num:', page.evaluate("document.getElementById('wiz-step-num').textContent"))
    # Click 偏多
    page.evaluate("""
      const opts = document.querySelectorAll('#wiz-options .wizard-opt');
      for (const o of opts) if (o.textContent.includes('偏多')) o.click();
    """)
    page.wait_for_timeout(300)
    page.click('#wiz-next')
    page.wait_for_timeout(600)
    page.screenshot(path='_d042_step3_range.png', full_page=False)
    print('=== Step 3 (range) ===')
    print('Title:', page.evaluate("document.getElementById('wiz-title').textContent"))
    print('Sub:', page.evaluate("document.getElementById('wiz-sub').textContent"))
    print('Step num:', page.evaluate("document.getElementById('wiz-step-num').textContent"))
    # Click 全市場
    page.evaluate("""
      const opts = document.querySelectorAll('#wiz-options .wizard-opt');
      for (const o of opts) if (o.textContent.includes('全市場')) o.click();
    """)
    page.wait_for_timeout(300)
    page.click('#wiz-next')
    page.wait_for_timeout(600)
    page.screenshot(path='_d042_step4_sort.png', full_page=False)
    print('=== Step 4 (sort) ===')
    print('Title:', page.evaluate("document.getElementById('wiz-title').textContent"))
    print('Sub:', page.evaluate("document.getElementById('wiz-sub').textContent"))
    print('Step num:', page.evaluate("document.getElementById('wiz-step-num').textContent"))
    # Click 護城河 ↓
    page.evaluate("""
      const opts = document.querySelectorAll('#wiz-options .wizard-opt');
      for (const o of opts) if (o.textContent.includes('護城河')) o.click();
    """)
    page.wait_for_timeout(300)
    page.click('#wiz-go')
    page.wait_for_timeout(1200)
    page.screenshot(path='_d042_step_done.png', full_page=False)
    print('=== After GO ===')
    print('Wizard hidden:', page.evaluate("document.getElementById('wizard').hidden"))
    print('Intention:', page.evaluate("document.getElementById('sum-intention').textContent"))
    print('Apply count:', page.evaluate("document.getElementById('sum-cnt').textContent"))
    # check JS errors during run
    print('Total steps getWizardSteps returns:', page.evaluate("getWizardSteps().length"))
    browser.close()
print('Screenshots saved: _d042_step1_persona.png, _d042_step2_direction.png, _d042_step3_range.png, _d042_step4_sort.png, _d042_step_done.png')
