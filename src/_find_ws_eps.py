#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
with open(r'C:\Users\icemo\Projects\tw-invest-suite\public\chips.html', 'r', encoding='utf-8') as f:
    content = f.read()
m = re.search(r'data-persona="ws_eps"', content)
if m:
    end = content.find('</button>', m.end()) + len('</button>')
    # find the close of the main persona-row-inner
    end_idx = content.find('</div></div>', end)
    print('ws_eps ends at', end, 'closing div at', end_idx)
    # show 6 lines after
    lines = content[end:end_idx+10].split('\n')
    for i, l in enumerate(lines[:15]):
        print(f'{i}: {l[:200]}')
