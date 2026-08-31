#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
with open(r'C:\Users\icemo\Projects\tw-invest-suite\public\chips.html', 'r', encoding='utf-8') as f:
    content = f.read()
# Find first 2 persona cards
m = re.search(r'data-persona="streak3"', content)
if m:
    start = m.start()
    end = content.find('data-persona="same_buy"', m.end())
    print(content[start:end])
    print('---')
    # find newbie card
    m2 = re.search(r'data-persona="newbie"', content)
    if m2:
        s = m2.start()
        e = content.find('data-persona="ws_aqr"', m2.end())
        print(content[s:e])
