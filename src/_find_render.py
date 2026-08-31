#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import re
with open(r'C:\Users\icemo\Projects\tw-invest-suite\public\chips.html', 'r', encoding='utf-8') as f:
    content = f.read()
# find renderWizardStep
m = re.search(r'function renderWizardStep\(\) \{', content)
if m:
    start = m.start()
    end = content.find('\n}\n', start)
    print(content[start:end+3])
