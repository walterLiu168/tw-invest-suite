#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pymysql
conn = pymysql.connect(host='localhost', user='root', password='1234', database='tw_elec')
cur = conn.cursor()
print('=== Final Sanity 9/1 ===')
for tbl in ['daily_data2_full', 'daily_data', 'daily_data2', 'chip_daily', 'chipscore_daily']:
    cur.execute(f'SELECT MAX(Date), COUNT(*) FROM {tbl}')
    r = cur.fetchone()
    cur.execute(f'SELECT COUNT(*) FROM {tbl} WHERE Date = %s', ('2026-09-01',))
    n = cur.fetchone()[0]
    print(f'  {tbl:20} MAX={r[0]}, 9/1={n}')
cur.execute('SELECT run_date, run_at, picks_count FROM market_screen_runs ORDER BY id DESC LIMIT 3')
print()
print('market_screen_runs:')
for r in cur.fetchall():
    print(f'  {r}')
cur.execute("SELECT run_id, COUNT(*), SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) FROM market_screen_picks GROUP BY run_id ORDER BY run_id DESC")
print()
print('picks per run:')
for r in cur.fetchall():
    print(f'  run_id={r[0]} total={r[1]} active={r[2]}')
cur.close()
conn.close()
