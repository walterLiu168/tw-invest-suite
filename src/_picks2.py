#!/usr/bin/env python3
import pymysql
conn = pymysql.connect(host='localhost', user='root', password='1234', database='tw_elec')
cur = conn.cursor()
cur.execute("SELECT run_id, COUNT(*), SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) FROM market_screen_picks GROUP BY run_id ORDER BY run_id")
for r in cur.fetchall():
    print(f'  run_id={r[0]} total={r[1]} active={r[2]}')
cur.execute("SELECT ticker, name, bucket, horizon, close_at_pick, status FROM market_screen_picks WHERE run_id = 3 ORDER BY id LIMIT 12")
print()
print('run_id=3 (9/1) long picks:')
for r in cur.fetchall():
    print(f'  {r}')
cur.close()
conn.close()
