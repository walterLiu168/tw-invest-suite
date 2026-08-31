#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
with open(r'C:\Users\icemo\Projects\tw-invest-suite\public\chips.html', 'r', encoding='utf-8') as f:
    content = f.read()
# find wizard-dot
for m in re.finditer(r'wizard-dot', content):
    start = max(0, m.start() - 80)
    end = min(len(content), m.end() + 100)
    line_no = content[:m.start()].count('\n') + 1
    print(f'L{line_no}: {content[start:end]}')
    print('---')
