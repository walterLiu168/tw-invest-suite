#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pymysql
conn = pymysql.connect(host='localhost', user='root', password='1234', database='tw_elec')
cur = conn.cursor()
# Check stock_names schema
cur.execute('DESCRIBE stock_names')
for r in cur.fetchall():
    print(' ', r)
print()
cur.execute('SELECT COUNT(*) FROM stock_names')
print('stock_names total:', cur.fetchone()[0])
# Sample
cur.execute('SELECT * FROM stock_names LIMIT 5')
print('stock_names sample:')
for r in cur.fetchall():
    print(' ', r)
print()
# Check daily_data2 6/15 sample
cur.execute('SELECT Ticker, company FROM daily_data2 WHERE Date = %s LIMIT 5', ('2026-06-15',))
print('daily_data2 6/15 sample:')
for r in cur.fetchall():
    print(' ', r)
