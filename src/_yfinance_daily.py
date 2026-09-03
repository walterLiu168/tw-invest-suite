#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
yfinance_daily.py — D047 daily 22:30 cron
Fetches yfinance .info for all 1962 tickers (PE/PB/div yield/market cap/etc).
Caches in cache_manager (TTL 1d).
- 2 workers, 0.5-1.5s jitter per call
- 20 consecutive failures → yfinance marked DEAD → all remaining skip yfinance + use FinMind fallback
- Per-ticker .json cache files in _cache/yfinance/
"""
import os
import sys
import time
import logging
from pathlib import Path

import pymysql

# Setup
ROOT = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts")
sys.path.insert(0, str(ROOT))

LOG_DIR = ROOT / "_debug"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"yfinance_{time.strftime('%Y%m%d_%H%M%S')}.log"

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

import yfinance_batch as yfb
import cache_manager as cm


def get_all_tickers():
    """Read all 4-digit tickers from industry_type (1962)."""
    conn = pymysql.connect(host='localhost', user='root', password='1234',
                            database='tw_elec', connect_timeout=10)
    cur = conn.cursor()
    cur.execute("SELECT ticker FROM industry_type "
                "WHERE ticker REGEXP '^[0-9]{4}$|^[0-9]{4}[A-Z]$'")
    rows = [r[0] for r in cur.fetchall()]
    conn.close()
    return rows


def main():
    log.info('=' * 60)
    log.info('yfinance_daily.py — daily 22:30 cron')
    log.info('=' * 60)

    tickers = get_all_tickers()
    log.info(f'Total tickers: {len(tickers)}')

    # Reset state
    yfb.reset()

    t0 = time.time()
    log.info('Starting batch_fetch (workers=2, jitter 0.5-1.5s)...')

    # Wrap batch_fetch with progress logging
    results = yfb.batch_fetch(tickers, workers=2)

    elapsed = time.time() - t0
    log.info(f'batch_fetch done in {elapsed:.0f}s ({elapsed/60:.1f}min)')

    # Summary
    success = sum(1 for v in results.values() if v.get('_source') == 'yfinance')
    fallback = sum(1 for v in results.values() if v.get('_source') == 'fallback')
    error = sum(1 for v in results.values() if v.get('_source') == 'error')
    cache_hit = success  # yfinance source = fresh
    dead = yfb.is_dead()
    log.info(f'  fresh yfinance: {success}')
    log.info(f'  fallback (FinMind): {fallback}')
    log.info(f'  error: {error}')
    log.info(f'  yfinance DEAD: {dead}')

    log.info('=' * 60)
    log.info(f'OK — log: {LOG_FILE}')
    return 0 if not dead else 2


if __name__ == '__main__':
    sys.exit(main())
