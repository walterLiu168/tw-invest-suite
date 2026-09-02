#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D045b: Backfill latest date to 5 tables (excluding daily_data2_full which is already latest)"""
import pymysql
import sys
from datetime import date, datetime

DB = dict(host='localhost', user='root', password='1234', database='tw_elec')

conn = pymysql.connect(**DB)
cur = conn.cursor()

# Find the latest date in daily_data2_full
cur.execute('SELECT MAX(Date) FROM daily_data2_full')
TARGET = cur.fetchone()[0]
print(f'Target date: {TARGET}')

# ============================================================
# Step 1: 補 daily_data2_full.company (用 industry_type)
# ============================================================
print('\n[1] daily_data2_full.company backfill')
cur.execute('''UPDATE daily_data2_full f
               JOIN industry_type i ON f.Ticker = i.ticker
               SET f.company = i.company
               WHERE f.Date = %s AND f.company IS NULL''', (TARGET,))
print(f'  Updated: {cur.rowcount} (industry_type join)')
conn.commit()
cur.execute('SELECT COUNT(*) FROM daily_data2_full WHERE Date = %s AND company IS NULL', (TARGET,))
null_after = cur.fetchone()[0]
print(f'  Still null: {null_after}')

# ============================================================
# Step 2: daily_data
# ============================================================
print('\n[2] daily_data')
cur.execute('SELECT COUNT(*) FROM daily_data WHERE Date = %s', (TARGET,))
before = cur.fetchone()[0]
print(f'  before: {before}')
cur.execute('DELETE FROM daily_data WHERE Date = %s', (TARGET,))
cur.execute('''INSERT INTO daily_data
  (Ticker, Date, Open, High, Low, Close, Volume, ForeignBuy, ForeignSell, ForeignNet,
   InvestmentBuy, InvestmentSell, InvestmentNet, DealerBuy, DealerSell, DealerNet,
   ThreeNet, SharesOutstanding_shares, MarginBalance, ShortBalance, DayTradeVol,
   DayTradeBuyAmt, DayTradeSellAmt, ForeignRatio, ForeignShare, company)
  SELECT Ticker, Date, Open, High, Low, Close, Volume, ForeignBuy, ForeignSell, ForeignNet,
         InvestmentBuy, InvestmentSell, InvestmentNet, DealerBuy, DealerSell, DealerNet,
         ThreeNet, SharesOutstanding_shares, MarginBalance, ShortBalance, DayTradeVol,
         DayTradeBuyAmt, DayTradeSellAmt, ForeignRatio, ForeignShare, company
  FROM daily_data2_full WHERE Date = %s''', (TARGET,))
print(f'  inserted: {cur.rowcount}')
conn.commit()

# ============================================================
# Step 3: daily_data2
# ============================================================
print('\n[3] daily_data2')
cur.execute('DELETE FROM daily_data2 WHERE Date = %s', (TARGET,))
cur.execute('INSERT INTO daily_data2 SELECT * FROM daily_data2_full WHERE Date = %s', (TARGET,))
print(f'  inserted: {cur.rowcount}')
conn.commit()

# ============================================================
# Step 4: chip_daily
# ============================================================
print('\n[4] chip_daily')
cur.execute('DELETE FROM chip_daily WHERE Date = %s', (TARGET,))
cur.execute('''INSERT INTO chip_daily (Ticker, Date, ForeignNet, InvestmentNet, DealerNet)
               SELECT Ticker, Date, ForeignNet, InvestmentNet, DealerNet
               FROM daily_data2_full WHERE Date = %s''', (TARGET,))
print(f'  inserted: {cur.rowcount}')
conn.commit()

# ============================================================
# Step 5: chipscore_daily
# ============================================================
print('\n[5] chipscore_daily')
cur.execute('DELETE FROM chipscore_daily WHERE Date = %s', (TARGET,))
cur.execute('''INSERT INTO chipscore_daily
  (Date, Ticker, Inv_FirstIn, Inv_BuyPercent, Inv_FirstBigBuy, VolumeBurst,
   BollingerBreakout, KD_GoldenCross, ForeignBuyRatio, InvestBuyRatio, ChipScore)
  SELECT
    f.Date, f.Ticker,
    CASE WHEN f.InvestmentNet > 0 THEN 1 ELSE 0 END,
    CASE WHEN (f.InvestmentBuy + f.InvestmentSell) > 0 THEN f.InvestmentBuy / (f.InvestmentBuy + f.InvestmentSell) ELSE 0 END,
    CASE WHEN f.InvestmentNet > 5000000 THEN 1 ELSE 0 END,
    0,
    CASE WHEN f.Close > f.sma_27 * 1.05 THEN 1 ELSE 0 END,
    0,
    CASE WHEN (f.ForeignBuy + f.ForeignSell) > 0 THEN f.ForeignBuy / (f.ForeignBuy + f.ForeignSell) ELSE 0 END,
    CASE WHEN (f.ForeignBuy + f.InvestmentBuy + f.DealerBuy) > 0 THEN f.InvestmentBuy / (f.ForeignBuy + f.InvestmentBuy + f.DealerBuy) ELSE 0 END,
    (CASE WHEN f.InvestmentNet > 0 THEN 1 ELSE 0 END) * 0.20 +
    (CASE WHEN f.InvestmentNet > 5000000 THEN 1 ELSE 0 END) * 0.15 +
    (CASE WHEN f.Close > f.sma_27 * 1.05 THEN 1 ELSE 0 END) * 0.15 +
    (CASE WHEN (f.ForeignBuy + f.ForeignSell) > 0 THEN f.ForeignBuy / (f.ForeignBuy + f.ForeignSell) ELSE 0 END) * 0.25 +
    (CASE WHEN (f.InvestmentBuy + f.InvestmentSell) > 0 THEN f.InvestmentBuy / (f.InvestmentBuy + f.InvestmentSell) ELSE 0 END) * 0.25
  FROM daily_data2_full f WHERE f.Date = %s''', (TARGET,))
print(f'  inserted: {cur.rowcount}')
conn.commit()

# ============================================================
# Step 6: market_screen — close 8/31 run, add 9/1 run
# ============================================================
print('\n[6] market_screen')
# Mark previous 24 picks (run_id=2) as closed (for performance tracking)
cur.execute("UPDATE market_screen_picks SET status = 'closed' WHERE run_id = (SELECT id FROM market_screen_runs WHERE run_date < %s AND run_date = (SELECT MAX(run_date) FROM market_screen_runs WHERE run_date < %s))", (TARGET, TARGET))
# That was wrong - just close all picks where run_id is the most recent run before TARGET
cur.execute('''UPDATE market_screen_picks
               SET status = 'closed'
               WHERE run_id = (
                 SELECT id FROM (
                   SELECT id FROM market_screen_runs
                   WHERE run_date < %s
                   ORDER BY run_date DESC LIMIT 1
                 ) AS t
               )''', (TARGET,))
print(f'  closed previous picks: {cur.rowcount}')
conn.commit()

# Get max run id
cur.execute('SELECT MAX(id) FROM market_screen_runs')
max_id = (cur.fetchone()[0] or 0) + 1

# Insert new run
cur.execute('''INSERT INTO market_screen_runs (id, run_date, run_at, total_tickers, picks_count, notes)
               VALUES (%s, %s, NOW(), %s, %s, %s)''',
            (max_id, TARGET, 1957, 24, f'auto-saved by backfill_{TARGET}'))
print(f'  new run_id: {max_id}')
conn.commit()
conn.close()
print('\nDONE — re-run _rerun_screen.py with TARGET=this to populate picks')
