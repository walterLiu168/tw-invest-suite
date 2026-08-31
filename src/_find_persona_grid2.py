#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys
with open(r'C:\Users\icemo\Projects\tw-invest-suite\public\chips.html', 'r', encoding='utf-8') as f:
    content = f.read()
# Find persona-q or persona section
import re
m = re.search(r'(<div[^>]*id="persona-q"[^>]*>)', content)
if not m:
    print('no persona-q')
    sys.exit(0)
print('persona-q at:', m.start())
start = m.start()
end_m = re.search(r'(<div[^>]*id="wizard"[^>]*>)', content[start:])
if not end_m:
    print('no wizard section')
    sys.exit(0)
end = start + end_m.start()
print('wizard at:', end)
snippet = content[start:end]
with open(r'C:\Users\icemo\Projects\tw-invest-suite\src\_persona_section.html', 'w', encoding='utf-8') as f:
    f.write(snippet)
print('wrote', len(snippet), 'chars to _persona_section.html')
