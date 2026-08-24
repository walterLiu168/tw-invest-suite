"""Fix fmt_shares double-minus bug"""
from pathlib import Path

p = Path(r'C:\Users\icemo\Projects\tw-invest-suite\src\chip_rank.py')
s = p.read_text(encoding='utf-8')
old = '''def fmt_shares(n):
    """股 → 張"""
    if n is None:
        return "—"
    lots = n / 1000.0
    sign = "+" if n > 0 else ("−" if n < 0 else "")
    if abs(lots) >= 10000:
        return f"{sign}{lots/10000:.1f}萬張"
    if abs(lots) >= 1000:
        return f"{sign}{lots/1000:.1f}k張"
    return f"{sign}{int(lots)}張"'''
new = '''def fmt_shares(n):
    """股 -> 張 (no double-minus)"""
    if n is None:
        return "—"
    lots = n / 1000.0
    a = abs(lots)
    if n > 0:
        if a >= 10000: return f"+{a/10000:.1f}萬張"
        if a >= 1000:  return f"+{a/1000:.1f}k張"
        return f"+{int(a)}張"
    if n < 0:
        if a >= 10000: return f"\u2212{a/10000:.1f}萬張"
        if a >= 1000:  return f"\u2212{a/1000:.1f}k張"
        return f"\u2212{int(a)}張"
    return "0張"'''
if old in s:
    p.write_text(s.replace(old, new), encoding='utf-8')
    print('FIXED')
else:
    print('NOT FOUND, skip')
