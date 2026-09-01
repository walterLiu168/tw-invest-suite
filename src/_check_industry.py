#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pymysql
conn = pymysql.connect(host='localhost', user='root', password='1234', database='tw_elec')
cur = conn.cursor()
# industry_type schema
cur.execute('DESCRIBE industry_type')
print('industry_type schema:')
for r in cur.fetchall():
    print(' ', r)
cur.execute('SELECT COUNT(*), SUM(CASE WHEN company IS NULL THEN 1 ELSE 0 END) FROM industry_type')
print('industry_type:', cur.fetchone())
cur.execute('SELECT * FROM industry_type LIMIT 3')
print('industry_type sample:')
for r in cur.fetchall():
    print(' ', r)
print()
# Check daily_data2_full 8/31 ticker overlap with daily_data2 6/15
cur.execute('SELECT COUNT(*) FROM daily_data2 WHERE Date = %s', ('2026-06-15',))
total_old = cur.fetchone()[0]
cur.execute('SELECT COUNT(*) FROM daily_data2_full WHERE Date = %s', ('2026-08-31',))
total_new = cur.fetchone()[0]
cur.execute('''SELECT COUNT(*) FROM daily_data2_full f
               LEFT JOIN daily_data2 d ON f.Ticker = d.Ticker AND d.Date = %s
               WHERE f.Date = %s AND f.company IS NULL AND d.company IS NOT NULL''', ('2026-06-15', '2026-08-31'))
overlap = cur.fetchone()[0]
print(f'8/31 records can be filled from 6/15 by ticker: {overlap}/{total_new} ({overlap/total_new*100:.1f}%)')
