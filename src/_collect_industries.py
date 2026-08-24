"""Collect all unique yfinance industry + sector values"""
import json
from collections import Counter
from pathlib import Path

CACHE = Path(r'C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_cache')

industries = Counter()
sectors = Counter()
for f in CACHE.glob('*.json'):
    try:
        j = json.loads(f.read_text(encoding='utf-8'))
        yf = (j.get('yfinance') or {}).get('data') or {}
        if yf.get('industry'):
            industries[yf['industry']] += 1
        if yf.get('sector'):
            sectors[yf['sector']] += 1
    except Exception:
        pass

print('=== Sectors ===')
for s, c in sectors.most_common():
    print(f'  {c:4d}  {s}')

print()
print('=== Industries ===')
for i, c in industries.most_common():
    print(f'  {c:4d}  {i}')
