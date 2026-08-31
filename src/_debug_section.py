#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
with open(r'C:\Users\icemo\Projects\tw-invest-suite\public\chips.html', 'r', encoding='utf-8') as f:
    content = f.read()
# find persona-row and end
m = re.search(r'<div class="persona-row">', content)
if not m:
    print('no persona-row')
    raise SystemExit(0)
start = m.start()
# find wizard section
end_m = re.search(r'<div[^>]*id="wizard"[^>]*>', content[start:])
if not end_m:
    print('no wizard')
    raise SystemExit(0)
end = start + end_m.start()
section = content[start:end]
# count <div and </div>
n_open = len(re.findall(r'<div\b', section))
n_close = len(re.findall(r'</div>', section))
print(f'section size: {len(section)}, open div: {n_open}, close div: {n_close}')
# show first 1000 chars and last 500 chars
print('=== first 600 ===')
print(section[:600])
print()
print('=== last 800 ===')
print(section[-800:])
