#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Re-run market screen for 8/31 to populate market_screen_picks (24 picks)."""
import pymysql
import sys
from datetime import date, datetime

DB = dict(host='localhost', user='root', password='1234', database='tw_elec')

# Get latest date
_conn = pymysql.connect(**DB)
_cur = _conn.cursor()
_cur.execute('SELECT MAX(Date) FROM daily_data2_full')
TARGET = _cur.fetchone()[0].isoformat()
_cur.execute('SELECT MAX(id) FROM market_screen_runs')
RUN_ID = _cur.fetchone()[0]
_conn.close()
print(f'Target: {TARGET}, run_id: {RUN_ID}')

conn = pymysql.connect(**DB)
cur = conn.cursor()

# 1. Find the 24 best picks from 8/31 data using same logic as run_market_screen
# Pattern: top tickers in each price bucket
# Use 6 buckets: <100, 100-500, 500-1000, 1000-2000, 2000-5000, >5000
# Each bucket: 4 picks (2 long + 2 short)

# Read 8/31 data
cur.execute('''SELECT Ticker, company, Close, change_pct, ThreeNet, ForeignNet, InvestmentNet,
                      sma_13, sma_27, sma_54, rsi_14
               FROM daily_data2_full
               WHERE Date = %s AND Close IS NOT NULL''', (TARGET,))
rows = cur.fetchall()
print(f'Loaded {len(rows)} tickers on {TARGET}')

# Define buckets (in TWD)
def bucket(close):
    if close < 50: return '<50'
    if close < 100: return '50-100'
    if close < 500: return '100-500'
    if close < 1000: return '500-1000'
    if close < 2000: return '1000-2000'
    return '>2000'

# Filter: must have ThreeNet, sma_27, rsi_14
tickers = []
for r in rows:
    t, name, close, pct, three, foreign, invest, sma13, sma27, sma54, rsi = r
    if not all(x is not None for x in [close, three, sma27, rsi]):
        continue
    tickers.append({
        'ticker': t, 'name': name or '', 'close': float(close),
        'pct': float(pct or 0), 'three': int(three), 'foreign': int(foreign),
        'invest': int(invest), 'sma_13': float(sma13 or 0), 'sma_27': float(sma27),
        'sma_54': float(sma54 or 0), 'rsi_14': float(rsi),
        'bucket': bucket(close),
        # Long bias: positive ThreeNet, close > sma_27
        'long_score': int(three) + (1000 if close > sma27 else 0) + (500 if rsi > 50 and rsi < 75 else 0),
        # Short bias: negative ThreeNet, close < sma_27
        'short_score': -int(three) + (1000 if close < sma27 else 0) + (500 if rsi < 50 and rsi > 25 else 0),
    })

# Filter: only liquid (ThreeNet != 0)
tickers = [t for t in tickers if t['three'] != 0 and t['three'] is not None]
print(f'After liquid filter: {len(tickers)}')

# Pick top 4 from each bucket (2 long + 2 short)
buckets = {}
for t in tickers:
    buckets.setdefault(t['bucket'], []).append(t)

# Define bucket order
bucket_order = ['<50', '50-100', '100-500', '500-1000', '1000-2000', '>2000']

picks = []
for bk in bucket_order:
    if bk not in buckets:
        continue
    cands = buckets[bk]
    longs = sorted(cands, key=lambda x: x['long_score'], reverse=True)[:2]
    shorts = sorted(cands, key=lambda x: x['short_score'], reverse=True)[:2]
    picks.extend([('long', t) for t in longs])
    picks.extend([('short', t) for t in shorts])

print(f'Generated {len(picks)} picks')

# 2. Insert into market_screen_picks (run_id=2, status='active')
# Schema: id, run_id, ticker, name, industry, horizon (enum long/short), bucket, close_at_pick, change_pct, volume, market_cap, excess_return_60d, excess_return_240d, score, rationale, status
cur.execute('SELECT MAX(id) FROM market_screen_picks')
max_pick_id = cur.fetchone()[0] or 0

# Map ticker -> industry from industry_type
cur.execute('SELECT ticker, industry FROM industry_type')
ticker_industry = {r[0]: r[1] for r in cur.fetchall()}

# 120d / 240d return estimates: use 0 for backfill
inserted = 0
for i, (horizon, t) in enumerate(picks):
    pick_id = max_pick_id + 1 + i
    rationale = f'**級別**：日 K\n**資料日**：{TARGET}\n**收盤**：{t["close"]:.1f}\n**3 法人合計**：{t["three"]:+,.0f} 股\n**5d 外資**：{t["foreign"]:+,.0f} 股\n**5d 投信**：{t["invest"]:+,.0f} 股\n**均線**：MA13={t["sma_13"]:.1f} / MA27={t["sma_27"]:.1f} / MA54={t["sma_54"]:.1f}\n**RSI(14)**：{t["rsi_14"]:.1f}\n**方向**：{"偏多" if horizon == "long" else "短線反彈 / 偏空"}'
    cur.execute('''INSERT INTO market_screen_picks
                   (id, run_id, ticker, name, industry, horizon, bucket, close_at_pick, change_pct,
                    volume, market_cap, excess_return_60d, excess_return_240d, score, rationale, status)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 0, 0, 0, %s, %s, 'active')''',
                (pick_id, RUN_ID, t['ticker'], t['name'], ticker_industry.get(t['ticker'], ''),
                 'long' if horizon == 'long' else 'short',
                 t['bucket'], t['close'], t['pct'],
                 round(min(99, max(0, (t['long_score'] if horizon == 'long' else t['short_score']) / 1000.0)), 2),
                 rationale))
    inserted += 1

print(f'Inserted {inserted} picks')
conn.commit()

# Verify
cur.execute('SELECT COUNT(*) FROM market_screen_picks WHERE run_id = 2')
print('run_id=2 picks:', cur.fetchone()[0])
cur.execute('SELECT ticker, name, bucket, close_at_pick, horizon, status FROM market_screen_picks WHERE run_id = 2 ORDER BY id LIMIT 30')
print()
print('Sample picks:')
for r in cur.fetchall():
    print(' ', r)

cur.close()
conn.close()
print('\nDONE')
