#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
with open(r'C:\Users\icemo\Projects\tw-invest-suite\public\chips.html', 'r', encoding='utf-8') as f:
    content = f.read()
# find wizard-actions
for m in re.finditer(r'wizard-actions', content):
    start = max(0, m.start() - 50)
    end = min(len(content), m.end() + 200)
    line_no = content[:m.start()].count('\n') + 1
    print(f'L{line_no}: {content[start:end]}')
    print('---')
