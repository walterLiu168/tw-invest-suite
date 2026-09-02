#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pymysql
conn = pymysql.connect(host='localhost', user='root', password='1234', database='tw_elec')
cur = conn.cursor()
cur.execute("SELECT run_id, COUNT(*), SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) FROM market_screen_picks GROUP BY run_id")
for r in cur.fetchall():
    print(f'  run_id={r[0]} total={r[1]} active={r[2]}')
cur.execute('SELECT MAX(id) FROM market_screen_picks')
print('max pick id:', cur.fetchone()[0])
cur.execute("SELECT run_id, ticker, name, status FROM market_screen_picks WHERE run_id = 3 ORDER BY id")
print()
print('run_id=3 picks:')
for r in cur.fetchall():
    print(f'  {r}')
cur.close()
conn.close()
