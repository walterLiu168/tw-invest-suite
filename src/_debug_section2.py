#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
with open(r'C:\Users\icemo\Projects\tw-invest-suite\public\chips.html', 'r', encoding='utf-8') as f:
    content = f.read()
# find persona-row
m = re.search(r'<div class="persona-row">', content)
print('persona-row at:', m.start() if m else 'NOT FOUND')
# find wizard - try various patterns
for pat in [r'<div[^>]*id="wizard"', r'wizard', r'<section[^>]*wizard']:
    m2 = re.search(pat, content)
    if m2:
        print(f'pattern {pat!r} at:', m2.start())
# Also find what's right after the persona-row-inner with all cards
# look for the summary-bar (next major section)
m3 = re.search(r'class="summary-bar"', content)
print('summary-bar at:', m3.start() if m3 else 'NOT FOUND')
