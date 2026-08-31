#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
with open(r'C:\Users\icemo\Projects\tw-invest-suite\public\chips.html', 'r', encoding='utf-8') as f:
    content = f.read()
# find PERSONAS declaration
m = re.search(r'var PERSONAS\s*=\s*\{', content)
if m:
    start = m.start()
    # find end of declaration (closing brace at indent 0)
    depth = 0
    i = start
    while i < len(content):
        c = content[i]
        if c == '{': depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break
        i += 1
    print(content[start:min(end, start+2500)])
