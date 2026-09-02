#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_legacy_tables.py — D046 daily 23:30 cron
Sync latest date from daily_data2_full → 4 legacy tables:
  1. daily_data     (26 cols basic OHLCV + 3 institutional)
  2. daily_data2    (35 cols same schema as daily_data2_full)
  3. chip_daily     (5 cols: Ticker, Date, ForeignNet, InvestmentNet, DealerNet)
  4. chipscore_daily (12 cols: computed from daily_data2_full)

Designed to be idempotent: DELETE existing rows for target date, then INSERT fresh.
"""
import os
import sys
import logging
from datetime import datetime
from pathlib import Path

import pymysql

# ============================================================
# Config
# ============================================================
DB = dict(host='localhost', user='root', password='1234', database='tw_elec')
LOG_DIR = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug")
LOG_FILE = LOG_DIR / f"sync_legacy_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)


def main():
    log.info('=' * 60)
    log.info('sync_legacy_tables.py — daily 23:30 cron')
    log.info('=' * 60)

    conn = pymysql.connect(**DB)
    cur = conn.cursor()

    # ============================================================
    # Step 0: get target date (latest in daily_data2_full)
    # ============================================================
    cur.execute('SELECT MAX(Date) FROM daily_data2_full')
    row = cur.fetchone()
    if not row or not row[0]:
        log.error('daily_data2_full is empty — abort')
        return 1
    target = row[0]
    log.info(f'Target date: {target}')

    # Verify daily_data2_full has data for target
    cur.execute('SELECT COUNT(*) FROM daily_data2_full WHERE Date = %s', (target,))
    n = cur.fetchone()[0]
    log.info(f'daily_data2_full records on {target}: {n}')

    # ============================================================
    # Step 1: daily_data (26 cols)
    # ============================================================
    log.info('[1/4] daily_data')
    cur.execute('DELETE FROM daily_data WHERE Date = %s', (target,))
    cur.execute('''INSERT INTO daily_data
      (Ticker, Date, Open, High, Low, Close, Volume, ForeignBuy, ForeignSell, ForeignNet,
       InvestmentBuy, InvestmentSell, InvestmentNet, DealerBuy, DealerSell, DealerNet,
       ThreeNet, SharesOutstanding_shares, MarginBalance, ShortBalance, DayTradeVol,
       DayTradeBuyAmt, DayTradeSellAmt, ForeignRatio, ForeignShare, company)
      SELECT Ticker, Date, Open, High, Low, Close, Volume, ForeignBuy, ForeignSell, ForeignNet,
             InvestmentBuy, InvestmentSell, InvestmentNet, DealerBuy, DealerSell, DealerNet,
             ThreeNet, SharesOutstanding_shares, MarginBalance, ShortBalance, DayTradeVol,
             DayTradeBuyAmt, DayTradeSellAmt, ForeignRatio, ForeignShare, company
      FROM daily_data2_full WHERE Date = %s''', (target,))
    log.info(f'  inserted: {cur.rowcount}')
    conn.commit()

    # ============================================================
    # Step 2: daily_data2 (35 cols, same as daily_data2_full)
    # ============================================================
    log.info('[2/4] daily_data2')
    cur.execute('DELETE FROM daily_data2 WHERE Date = %s', (target,))
    cur.execute('INSERT INTO daily_data2 SELECT * FROM daily_data2_full WHERE Date = %s', (target,))
    log.info(f'  inserted: {cur.rowcount}')
    conn.commit()

    # ============================================================
    # Step 3: chip_daily (5 cols)
    # ============================================================
    log.info('[3/4] chip_daily')
    cur.execute('DELETE FROM chip_daily WHERE Date = %s', (target,))
    cur.execute('''INSERT INTO chip_daily (Ticker, Date, ForeignNet, InvestmentNet, DealerNet)
                   SELECT Ticker, Date, ForeignNet, InvestmentNet, DealerNet
                   FROM daily_data2_full WHERE Date = %s''', (target,))
    log.info(f'  inserted: {cur.rowcount}')
    conn.commit()

    # ============================================================
    # Step 4: chipscore_daily (12 cols, computed)
    # ============================================================
    log.info('[4/4] chipscore_daily')
    cur.execute('DELETE FROM chipscore_daily WHERE Date = %s', (target,))
    cur.execute('''INSERT INTO chipscore_daily
      (Date, Ticker, Inv_FirstIn, Inv_BuyPercent, Inv_FirstBigBuy, VolumeBurst,
       BollingerBreakout, KD_GoldenCross, ForeignBuyRatio, InvestBuyRatio, ChipScore)
      SELECT
        f.Date, f.Ticker,
        CASE WHEN f.InvestmentNet > 0 THEN 1 ELSE 0 END,
        CASE WHEN (f.InvestmentBuy + f.InvestmentSell) > 0
             THEN f.InvestmentBuy / (f.InvestmentBuy + f.InvestmentSell) ELSE 0 END,
        CASE WHEN f.InvestmentNet > 5000000 THEN 1 ELSE 0 END,
        0,
        CASE WHEN f.Close > f.sma_27 * 1.05 THEN 1 ELSE 0 END,
        0,
        CASE WHEN (f.ForeignBuy + f.ForeignSell) > 0
             THEN f.ForeignBuy / (f.ForeignBuy + f.ForeignSell) ELSE 0 END,
        CASE WHEN (f.ForeignBuy + f.InvestmentBuy + f.DealerBuy) > 0
             THEN f.InvestmentBuy / (f.ForeignBuy + f.InvestmentBuy + f.DealerBuy) ELSE 0 END,
        (CASE WHEN f.InvestmentNet > 0 THEN 1 ELSE 0 END) * 0.20 +
        (CASE WHEN f.InvestmentNet > 5000000 THEN 1 ELSE 0 END) * 0.15 +
        (CASE WHEN f.Close > f.sma_27 * 1.05 THEN 1 ELSE 0 END) * 0.15 +
        (CASE WHEN (f.ForeignBuy + f.ForeignSell) > 0
              THEN f.ForeignBuy / (f.ForeignBuy + f.ForeignSell) ELSE 0 END) * 0.25 +
        (CASE WHEN (f.InvestmentBuy + f.InvestmentSell) > 0
              THEN f.InvestmentBuy / (f.InvestmentBuy + f.InvestmentSell) ELSE 0 END) * 0.25
      FROM daily_data2_full f WHERE f.Date = %s''', (target,))
    log.info(f'  inserted: {cur.rowcount}')
    conn.commit()

    # ============================================================
    # Step 5: market_screen — close prior active picks (so watchlist.html rotates)
    # Skip if no market_screen_picks table or fails — non-critical
    # ============================================================
    log.info('[5/5] market_screen (close prior + new run)')
    try:
        # Close all currently active picks (they were from previous run_date)
        cur.execute("UPDATE market_screen_picks SET status = 'closed' WHERE status = 'active'")
        log.info(f'  closed {cur.rowcount} prior picks')
        conn.commit()
    except Exception as e:
        log.warning(f'  market_screen close failed: {e}')

    # ============================================================
    # Summary
    # ============================================================
    log.info('=' * 60)
    log.info('Summary:')
    for tbl in ['daily_data2_full', 'daily_data', 'daily_data2', 'chip_daily', 'chipscore_daily']:
        cur.execute(f'SELECT MAX(Date), COUNT(*) FROM {tbl}')
        r = cur.fetchone()
        log.info(f'  {tbl:20} MAX={r[0]}, total={r[1]}')
    log.info('=' * 60)
    log.info(f'OK — log: {LOG_FILE}')

    cur.close()
    conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
