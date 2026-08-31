# -*- coding: utf-8 -*-
with open(r'C:\Users\icemo\Projects\tw-invest-suite\public\chips.html', 'rb') as f:
    c = f.read()
i3 = c.find(b'wizard-progress')
print('wizard-progress:', i3)
if i3 > 0:
    snippet = c[i3-300:i3+800]
    print(snippet.decode('utf-8', errors='replace'))
