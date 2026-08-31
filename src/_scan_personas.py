#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
with open(r'C:\Users\icemo\Projects\tw-invest-suite\public\chips.html', 'r', encoding='utf-8') as f:
    content = f.read()
# Find all persona cards
matches = list(re.finditer(r'data-persona="([^"]+)"', content))
keys = [m.group(1) for m in matches]
print('Persona card order (in HTML):')
for i, k in enumerate(keys):
    print(f'  {i+1}. {k}')
print()
# Find persona-card grid container
m = re.search(r'(<div[^>]*class="persona-card-grid"[^>]*>)(.*?)(</div>\s*</div>\s*<div[^>]*class="(persona-q|wizard|filter))', content, re.DOTALL)
if m:
    print('=== Grid container (start 1000 chars) ===')
    print(m.group(2)[:1000])
