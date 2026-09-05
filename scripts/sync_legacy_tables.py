#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_legacy_tables.py — D052h-fixup
Sync latest date from daily_data2_full -> 4 legacy tables:
  1. daily_data  (26 cols)
  2. daily_data2 (35 cols)
  3. chip_daily  (5 cols)
  4. chipscore_daily (12 cols)

D052h-fixup changes from runtime:
  - Self-contained (no runtime import, no monkey-patch)
  - Step 5 (close market_screen_picks) is NOT executed; that job is done
    by market_screen_runner.py. This is the versioned skip-close interface.
  - Returns exit code via sys.exit.
  - SQL column lists MATCH runtime exactly (verified against information_schema).
"""
import sys
import logging
import traceback
from datetime import datetime
from pathlib import Path

import pymysql

SCRIPT_VERSION = "D052h-fixup-1"
__SKIP_CLOSE_PICKS = True  # versioned: market_screen_runner handles closes

DB = dict(host='localhost', user='root', password='1234', database='tw_elec',
          connect_timeout=10, charset='utf8mb4')

LOG_DIR = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"sync_legacy_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

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


# SQL strings match runtime's sync_legacy_tables.py exactly (verified
# against information_schema on 2026-09-05).
SQL_DAILY_DATA = """
INSERT INTO daily_data
  (Ticker, Date, Open, High, Low, Close, Volume, ForeignBuy, ForeignSell, ForeignNet,
   InvestmentBuy, InvestmentSell, InvestmentNet, DealerBuy, DealerSell, DealerNet,
   ThreeNet, SharesOutstanding_shares, MarginBalance, ShortBalance, DayTradeVol,
   DayTradeBuyAmt, DayTradeSellAmt, ForeignRatio, ForeignShare, company)
  SELECT Ticker, Date, Open, High, Low, Close, Volume, ForeignBuy, ForeignSell, ForeignNet,
         InvestmentBuy, InvestmentSell, InvestmentNet, DealerBuy, DealerSell, DealerNet,
         ThreeNet, SharesOutstanding_shares, MarginBalance, ShortBalance, DayTradeVol,
         DayTradeBuyAmt, DayTradeSellAmt, ForeignRatio, ForeignShare, company
  FROM daily_data2_full WHERE Date = %s
"""

SQL_DAILY_DATA2 = """
INSERT INTO daily_data2
SELECT * FROM daily_data2_full WHERE Date = %s
"""

SQL_CHIP_DAILY = """
INSERT INTO chip_daily (Ticker, Date, ForeignNet, InvestmentNet, DealerNet)
SELECT Ticker, Date, ForeignNet, InvestmentNet, DealerNet
FROM daily_data2_full WHERE Date = %s
"""

SQL_CHIPSCORE_DAILY = """
INSERT INTO chipscore_daily
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
  FROM daily_data2_full f WHERE f.Date = %s
"""


def sync_one(cur, target, step_name, sql):
    log.info(f'[{step_name}] DELETE+INSERT for {target}')
    cur.execute(f'DELETE FROM {step_name} WHERE Date = %s', (target,))
    deleted = cur.rowcount
    cur.execute(sql, (target,))
    inserted = cur.rowcount
    log.info(f'  deleted {deleted}, inserted {inserted}')
    return inserted


def main():
    log.info('=' * 60)
    log.info(f'sync_legacy_tables.py v={SCRIPT_VERSION} daily 23:30 cron')
    if __SKIP_CLOSE_PICKS:
        log.info('  SKIP_CLOSE_PICKS=True (market_screen_runner handles closes)')
    log.info('=' * 60)

    exit_code = 0
    conn = pymysql.connect(**DB)
    try:
        cur = conn.cursor()

        # Step 0: get target date
        cur.execute('SELECT MAX(Date) FROM daily_data2_full')
        row = cur.fetchone()
        if not row or not row[0]:
            log.error('daily_data2_full is empty -> abort')
            return 1
        target = row[0]
        log.info(f'Target date: {target}')

        cur.execute('SELECT COUNT(*) FROM daily_data2_full WHERE Date = %s', (target,))
        n_full = cur.fetchone()[0]
        if n_full == 0:
            log.error(f'daily_data2_full has no data for {target} -> abort')
            return 1
        log.info(f'daily_data2_full rows for {target}: {n_full}')

        # Step 1: daily_data
        try:
            sync_one(cur, target, 'daily_data', SQL_DAILY_DATA)
        except Exception as e:
            log.error(f'daily_data sync failed: {e}')
            return 1

        # Step 2: daily_data2
        try:
            sync_one(cur, target, 'daily_data2', SQL_DAILY_DATA2)
        except Exception as e:
            log.error(f'daily_data2 sync failed: {e}')
            return 1

        # Step 3: chip_daily
        try:
            sync_one(cur, target, 'chip_daily', SQL_CHIP_DAILY)
        except Exception as e:
            log.error(f'chip_daily sync failed: {e}')
            return 1

        # Step 4: chipscore_daily
        try:
            sync_one(cur, target, 'chipscore_daily', SQL_CHIPSCORE_DAILY)
        except Exception as e:
            log.error(f'chipscore_daily sync failed: {e}')
            return 1

        conn.commit()

        # Step 5 SKIPPED per D052h-fixup
        if __SKIP_CLOSE_PICKS:
            log.info('[5/5] SKIPPED close-picks (market_screen_runner handles it)')

        # Summary
        log.info('=' * 60)
        log.info('Summary:')
        for tbl in ['daily_data2_full', 'daily_data', 'daily_data2', 'chip_daily', 'chipscore_daily']:
            cur.execute(f'SELECT MAX(Date), COUNT(*) FROM {tbl}')
            r = cur.fetchone()
            log.info(f'  {tbl:25} MAX={r[0]}, total={r[1]}')

    except Exception as e:
        log.error(f'sync_legacy_tables.py FATAL: {e}')
        traceback.print_exc()
        exit_code = 1
    finally:
        conn.close()

    log.info(f'=== sync_legacy_tables.py done (exit {exit_code}) ===')
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
