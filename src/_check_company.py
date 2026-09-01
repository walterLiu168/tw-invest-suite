#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pymysql
conn = pymysql.connect(host='localhost', user='root', password='1234', database='tw_elec')
cur = conn.cursor()
cur.execute('SELECT COUNT(*), SUM(CASE WHEN company IS NULL THEN 1 ELSE 0 END) FROM daily_data2 WHERE Date = %s', ('2026-06-15',))
r = cur.fetchone()
print(f'daily_data2 6/15: total={r[0]}, company_null={r[1]}')
cur.execute('SELECT COUNT(*), SUM(CASE WHEN company IS NULL THEN 1 ELSE 0 END) FROM daily_data WHERE Date = %s', ('2026-04-22',))
r = cur.fetchone()
print(f'daily_data 4/22: total={r[0]}, company_null={r[1]}')
cur.execute("SELECT TABLE_NAME, COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'tw_elec' AND COLUMN_NAME IN ('company', 'name', 'stock_name', 'cname')")
for r in cur.fetchall():
    print(' ', r)
