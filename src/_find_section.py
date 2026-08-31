#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
with open(r'C:\Users\icemo\Projects\tw-invest-suite\public\chips.html', 'r', encoding='utf-8') as f:
    content = f.read()

matches = list(re.finditer(r'data-persona="streak3"', content))
if not matches:
    print('not found')
    raise SystemExit(0)
m = matches[0]
lines = content.split('\n')
start_line = content[:m.start()].count('\n')
# print 30 lines around it
print('streak3 card at line', start_line+1)
for i in range(max(0, start_line-15), min(len(lines), start_line+50)):
    print(f'{i+1:4d}: {lines[i]}')
