#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
company_refresh.py — D052f
Refresh daily_data2_full.company from industry_type for recent dates.
Per ChatGPT F6, do NOT use src/_daily_backfill.py (has destructive ops).
This script only updates the company column via JOIN.

Usage:
  python company_refresh.py                     # refresh last 7 days
  python company_refresh.py --days=30           # refresh last 30 days
  python company_refresh.py --all               # refresh ALL dates (one-time cleanup)
  python company_refresh.py --dry-run
  python company_refresh.py --date=2026-09-04   # single date
"""
import argparse
import sys
import time
from datetime import date, timedelta

import pymysql

DB = dict(host="localhost", user="root", password="1234", database="tw_elec",
          connect_timeout=10, charset="utf8mb4")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7,
                    help="refresh last N days (default 7)")
    ap.add_argument("--all", action="store_true",
                    help="refresh ALL dates (one-time cleanup)")
    ap.add_argument("--date", help="single date (YYYY-MM-DD)")
    ap.add_argument("--dry-run", action="store_true",
                    help="count but do not update")
    args = ap.parse_args()

    conn = pymysql.connect(**DB)
    cur = conn.cursor()

    # Build WHERE clause for date filter
    if args.date:
        date_filter = f"d.Date = '{args.date}'"
    elif args.all:
        date_filter = "1=1"
    else:
        cutoff = (date.today() - timedelta(days=args.days)).isoformat()
        date_filter = f"d.Date >= '{cutoff}'"

    # Count what we're about to update
    cur.execute(f"""
        SELECT COUNT(*) FROM daily_data2_full d
        JOIN industry_type i ON d.ticker = i.ticker
        WHERE {date_filter}
          AND (d.company IS NULL OR TRIM(d.company) = '' OR d.company != i.company)
    """)
    would_update = cur.fetchone()[0]

    cur.execute(f"""
        SELECT COUNT(*) FROM daily_data2_full d
        WHERE {date_filter}
    """)
    total_in_range = cur.fetchone()[0]

    cur.execute(f"""
        SELECT COUNT(*) FROM daily_data2_full d
        LEFT JOIN industry_type i ON d.ticker = i.ticker
        WHERE {date_filter} AND i.ticker IS NULL
    """)
    no_industry = cur.fetchone()[0]

    print(f"[company-refresh] scope: {date_filter}")
    print(f"  rows in range:           {total_in_range}")
    print(f"  rows missing industry:   {no_industry}  (not in industry_type, skipped)")
    print(f"  rows needing company fix: {would_update}")

    if args.dry_run:
        print("[company-refresh] DRY-RUN: no DB writes")
        conn.close()
        return 0

    if would_update == 0:
        print("[company-refresh] nothing to do")
        conn.close()
        return 0

    # Update via JOIN. Use UPDATE ... JOIN syntax (MySQL).
    t0 = time.time()
    cur.execute(f"""
        UPDATE daily_data2_full d
        JOIN industry_type i ON d.ticker = i.ticker
        SET d.company = i.company
        WHERE {date_filter}
          AND (d.company IS NULL OR TRIM(d.company) = '' OR d.company != i.company)
    """)
    affected = cur.rowcount
    elapsed = time.time() - t0
    conn.commit()
    conn.close()

    print(f"[company-refresh] updated {affected} rows in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
