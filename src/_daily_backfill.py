#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""D045: Backfill 8/31 data to 6 tables
- daily_data2_full: 補 company from industry_type
- daily_data: insert 8/31 from daily_data2_full
- daily_data2: insert 8/31 from daily_data2_full
- chip_daily: insert 8/31 from daily_data2_full
- chipscore_daily: insert 8/31 (basic values from existing schema, ChipScore=0 fallback)
"""
import pymysql
import sys
from datetime import date

DB = dict(host='localhost', user='root', password='1234', database='tw_elec')
TARGET_DATE = '2026-08-31'

conn = pymysql.connect(**DB)
cur = conn.cursor()

print(f'=== Backfilling {TARGET_DATE} to 6 tables ===\n')

# ============================================================
# Step 1: 補 daily_data2_full.company (用 industry_type)
# ============================================================
print('[1] daily_data2_full.company backfill')
cur.execute('SELECT COUNT(*) FROM daily_data2_full WHERE Date = %s AND company IS NULL', (TARGET_DATE,))
null_count = cur.fetchone()[0]
print(f'  before: {null_count} records without company')

# JOIN update
cur.execute('''
    UPDATE daily_data2_full f
    JOIN industry_type i ON f.Ticker = i.ticker
    SET f.company = i.company
    WHERE f.Date = %s AND f.company IS NULL
''', (TARGET_DATE,))
conn.commit()
cur.execute('SELECT COUNT(*) FROM daily_data2_full WHERE Date = %s AND company IS NULL', (TARGET_DATE,))
null_after = cur.fetchone()[0]
print(f'  after:  {null_after} records without company (filled {null_count - null_after})')

# ============================================================
# Step 2: daily_data 8/31 from daily_data2_full
# ============================================================
print('\n[2] daily_data backfill')
# daily_data cols: Ticker, Date, Open, High, Low, Close, Volume, ForeignBuy, ForeignSell, ForeignNet,
#                  InvestmentBuy, InvestmentSell, InvestmentNet, DealerBuy, DealerSell, DealerNet,
#                  ThreeNet, SharesOutstanding_shares, MarginBalance, ShortBalance, DayTradeVol,
#                  DayTradeBuyAmt, DayTradeSellAmt, ForeignRatio, ForeignShare, company
cur.execute('SELECT COUNT(*) FROM daily_data WHERE Date = %s', (TARGET_DATE,))
before = cur.fetchone()[0]
print(f'  before: {before} records on {TARGET_DATE}')

# delete existing
cur.execute('DELETE FROM daily_data WHERE Date = %s', (TARGET_DATE,))
# insert from daily_data2_full
cur.execute('''
    INSERT INTO daily_data
    (Ticker, Date, Open, High, Low, Close, Volume, ForeignBuy, ForeignSell, ForeignNet,
     InvestmentBuy, InvestmentSell, InvestmentNet, DealerBuy, DealerSell, DealerNet,
     ThreeNet, SharesOutstanding_shares, MarginBalance, ShortBalance, DayTradeVol,
     DayTradeBuyAmt, DayTradeSellAmt, ForeignRatio, ForeignShare, company)
    SELECT Ticker, Date, Open, High, Low, Close, Volume, ForeignBuy, ForeignSell, ForeignNet,
           InvestmentBuy, InvestmentSell, InvestmentNet, DealerBuy, DealerSell, DealerNet,
           ThreeNet, SharesOutstanding_shares, MarginBalance, ShortBalance, DayTradeVol,
           DayTradeBuyAmt, DayTradeSellAmt, ForeignRatio, ForeignShare, company
    FROM daily_data2_full
    WHERE Date = %s
''', (TARGET_DATE,))
conn.commit()
cur.execute('SELECT COUNT(*), SUM(CASE WHEN company IS NULL THEN 1 ELSE 0 END) FROM daily_data WHERE Date = %s', (TARGET_DATE,))
r = cur.fetchone()
print(f'  after:  {r[0]} records ({r[1]} without company)')

# ============================================================
# Step 3: daily_data2 8/31 from daily_data2_full (同 schema)
# ============================================================
print('\n[3] daily_data2 backfill')
cur.execute('SELECT COUNT(*) FROM daily_data2 WHERE Date = %s', (TARGET_DATE,))
before = cur.fetchone()[0]
print(f'  before: {before} records on {TARGET_DATE}')

cur.execute('DELETE FROM daily_data2 WHERE Date = %s', (TARGET_DATE,))
cur.execute('''
    INSERT INTO daily_data2
    SELECT * FROM daily_data2_full WHERE Date = %s
''', (TARGET_DATE,))
conn.commit()
cur.execute('SELECT COUNT(*), SUM(CASE WHEN company IS NULL THEN 1 ELSE 0 END) FROM daily_data2 WHERE Date = %s', (TARGET_DATE,))
r = cur.fetchone()
print(f'  after:  {r[0]} records ({r[1]} without company)')

# ============================================================
# Step 4: chip_daily 8/31
# ============================================================
print('\n[4] chip_daily backfill')
cur.execute('SELECT COUNT(*) FROM chip_daily WHERE Date = %s', (TARGET_DATE,))
before = cur.fetchone()[0]
print(f'  before: {before} records on {TARGET_DATE}')

cur.execute('DELETE FROM chip_daily WHERE Date = %s', (TARGET_DATE,))
cur.execute('''
    INSERT INTO chip_daily (Ticker, Date, ForeignNet, InvestmentNet, DealerNet)
    SELECT Ticker, Date, ForeignNet, InvestmentNet, DealerNet
    FROM daily_data2_full WHERE Date = %s
''', (TARGET_DATE,))
conn.commit()
cur.execute('SELECT COUNT(*) FROM chip_daily WHERE Date = %s', (TARGET_DATE,))
print(f'  after:  {cur.fetchone()[0]} records')

# ============================================================
# Step 5: chipscore_daily 8/31 (simplified)
# ============================================================
print('\n[5] chipscore_daily backfill (simplified)')
cur.execute('SELECT COUNT(*) FROM chipscore_daily WHERE Date = %s', (TARGET_DATE,))
before = cur.fetchone()[0]
print(f'  before: {before} records on {TARGET_DATE}')

# Compute scores from daily_data2_full + chipscore daily aggregation
# Inv_FirstIn: 1 if InvestmentNet > 0 (投信買超)
# Inv_BuyPercent: InvestmentBuy / (InvestmentBuy+InvestmentSell) * 100
# Inv_FirstBigBuy: 1 if InvestmentNet > 5_000_000 (5M TWD)
# VolumeBurst: 1 if Volume > avg 5d
# BollingerBreakout: 1 if Close > sma_27 * 1.05
# KD_GoldenCross: skip (need K,D data) — 0
# ForeignBuyRatio: ForeignBuy / (ForeignBuy+ForeignSell) * 100
# InvestBuyRatio: InvestmentBuy / (ForeignBuy+InvestmentBuy+DealerBuy) * 100
# ChipScore: weighted sum

cur.execute('DELETE FROM chipscore_daily WHERE Date = %s', (TARGET_DATE,))
cur.execute('''
    INSERT INTO chipscore_daily
    (Date, Ticker, Inv_FirstIn, Inv_BuyPercent, Inv_FirstBigBuy, VolumeBurst,
     BollingerBreakout, KD_GoldenCross, ForeignBuyRatio, InvestBuyRatio, ChipScore)
    SELECT
      f.Date, f.Ticker,
      CASE WHEN f.InvestmentNet > 0 THEN 1 ELSE 0 END AS Inv_FirstIn,
      CASE WHEN (f.InvestmentBuy + f.InvestmentSell) > 0
           THEN f.InvestmentBuy / (f.InvestmentBuy + f.InvestmentSell) ELSE 0 END AS Inv_BuyPercent,
      CASE WHEN f.InvestmentNet > 5000000 THEN 1 ELSE 0 END AS Inv_FirstBigBuy,
      0 AS VolumeBurst,
      CASE WHEN f.Close > f.sma_27 * 1.05 THEN 1 ELSE 0 END AS BollingerBreakout,
      0 AS KD_GoldenCross,
      CASE WHEN (f.ForeignBuy + f.ForeignSell) > 0
           THEN f.ForeignBuy / (f.ForeignBuy + f.ForeignSell) ELSE 0 END AS ForeignBuyRatio,
      CASE WHEN (f.ForeignBuy + f.InvestmentBuy + f.DealerBuy) > 0
           THEN f.InvestmentBuy / (f.ForeignBuy + f.InvestmentBuy + f.DealerBuy) ELSE 0 END AS InvestBuyRatio,
      -- ChipScore: weighted sum
      (CASE WHEN f.InvestmentNet > 0 THEN 1 ELSE 0 END) * 0.20 +
      (CASE WHEN f.InvestmentNet > 5000000 THEN 1 ELSE 0 END) * 0.15 +
      (CASE WHEN f.Close > f.sma_27 * 1.05 THEN 1 ELSE 0 END) * 0.15 +
      (CASE WHEN (f.ForeignBuy + f.ForeignSell) > 0
            THEN f.ForeignBuy / (f.ForeignBuy + f.ForeignSell) ELSE 0 END) * 0.25 +
      (CASE WHEN (f.InvestmentBuy + f.InvestmentSell) > 0
            THEN f.InvestmentBuy / (f.InvestmentBuy + f.InvestmentSell) ELSE 0 END) * 0.25
      AS ChipScore
    FROM daily_data2_full f
    WHERE f.Date = %s
''', (TARGET_DATE,))
conn.commit()
cur.execute('SELECT COUNT(*) FROM chipscore_daily WHERE Date = %s', (TARGET_DATE,))
print(f'  after:  {cur.fetchone()[0]} records')

# ============================================================
# Final summary
# ============================================================
print('\n=== Final Summary ===')
for tbl in ['daily_data2_full', 'daily_data', 'daily_data2', 'chip_daily', 'chipscore_daily']:
    cur.execute(f'SELECT MAX(Date), COUNT(*) FROM {tbl}')
    r = cur.fetchone()
    print(f'  {tbl:20} MAX(date)={r[0]}, total={r[1]}')

print()
cur.execute('SELECT MAX(Date), COUNT(*) FROM daily_data2_full WHERE company IS NOT NULL')
r = cur.fetchone()
print(f'  daily_data2_full with company: {r[1]} on {r[0]}')
cur.close()
conn.close()
print('\nDONE')
