#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
with open(r'C:\Users\icemo\Projects\tw-invest-suite\public\chips.html', 'r', encoding='utf-8') as f:
    content = f.read()
# Find persona-q or persona section
m = re.search(r'(<div[^>]*id="persona-q"[^>]*>)', content)
if m:
    print('persona-q at:', m.start())
    # Find the start of persona cards
    start = m.start()
    # Find wizard section start
    end_m = re.search(r'(<div[^>]*id="wizard"[^>]*>)', content[start:])
    if end_m:
        end = start + end_m.start()
        print('wizard at:', end)
        snippet = content[start:end]
        # only print first 6000 chars
        print('=== first 6000 chars ===')
        print(snippet[:6000])
