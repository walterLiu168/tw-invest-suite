#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pymysql
from datetime import date
import json
import re

conn = pymysql.connect(host='localhost', user='root', password='1234', database='tw_elec')
cur = conn.cursor()
print('Today:', date.today())
print()
print('=== Latest dates in each table ===')
for tbl in ['daily_data2_full', 'daily_data', 'daily_data2', 'chip_daily', 'chipscore_daily']:
    cur.execute(f'SELECT MAX(Date), COUNT(*) FROM {tbl}')
    r = cur.fetchone()
    cur.execute(f'SELECT COUNT(*) FROM {tbl} WHERE Date = %s', ('2026-09-01',))
    n9 = cur.fetchone()[0]
    cur.execute(f'SELECT COUNT(*) FROM {tbl} WHERE Date = %s', ('2026-08-31',))
    n8 = cur.fetchone()[0]
    print(f'  {tbl:20} MAX={r[0]} (total={r[1]})  9/1={n9}  8/31={n8}')
print()
print('=== market_screen_runs ===')
cur.execute('SELECT id, run_date, run_at, total_tickers, picks_count FROM market_screen_runs ORDER BY id DESC LIMIT 3')
for r in cur.fetchall():
    print(f'  id={r[0]} run_date={r[1]} run_at={r[2]} tickers={r[3]} picks={r[4]}')
print()
print('=== chips.json date ===')
with open(r'C:\Users\icemo\Projects\tw-invest-suite\public\data\chips.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
date_v = data.get('date')
print(f'  date: {date_v}')
print()
print('=== watchlist.html date ===')
with open('public/watchlist.html', 'r', encoding='utf-8') as f:
    content = f.read()
m = re.search(r'資料日\s*(\d{4}-\d{2}-\d{2})', content)
print(f'  data date: {m.group(1) if m else "N/A"}')
m2 = re.search(r'最後更新\s*([\dT:]+)', content)
print(f'  last update: {m2.group(1) if m2 else "N/A"}')
cur.close()
conn.close()
