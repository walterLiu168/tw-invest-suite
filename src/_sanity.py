#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import pymysql
conn = pymysql.connect(host='localhost', user='root', password='1234', database='tw_elec')
cur = conn.cursor()
print('=== Final Sanity Check ===')
print('Today: 2026-09-01 (need 8/31 data)')
print()
for tbl in ['daily_data2_full', 'daily_data', 'daily_data2', 'chip_daily', 'chipscore_daily']:
    cur.execute(f'SELECT MAX(Date), COUNT(*) FROM {tbl}')
    r = cur.fetchone()
    cur.execute(f'SELECT COUNT(*) FROM {tbl} WHERE Date = %s', ('2026-08-31',))
    n = cur.fetchone()[0]
    print(f'  {tbl:20} MAX={r[0]}, total={r[1]}, 8/31={n}')
cur.execute('SELECT run_date, run_at, total_tickers, picks_count FROM market_screen_runs ORDER BY id DESC LIMIT 3')
print()
print('market_screen_runs (latest 3):')
for r in cur.fetchall():
    print(f'  {r}')
cur.execute("SELECT COUNT(*), SUM(CASE WHEN horizon = 'long' THEN 1 ELSE 0 END), SUM(CASE WHEN horizon = 'short' THEN 1 ELSE 0 END) FROM market_screen_picks WHERE run_id = 2")
r = cur.fetchone()
print(f'  market_screen_picks run_id=2: total={r[0]}, long={r[1]}, short={r[2]}')
cur.close(); conn.close()
