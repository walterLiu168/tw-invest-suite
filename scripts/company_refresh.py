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
import json
from pathlib import Path
from datetime import date, timedelta

import pymysql

DB = dict(host="localhost", user="root", password="1234", database="tw_elec",
          connect_timeout=10, charset="utf8mb4")


def name_repairs(current, rows):
    """Only repair replacement-character names from a fresh, unique listed name."""
    valid = []
    for row in rows:
        try:
            source_date = date.fromisoformat(str(row.get('date')))
        except ValueError:
            continue
        if source_date <= date.today():
            valid.append((source_date, row))
    if not valid:
        raise ValueError('No dated company-name source')
    latest = max(day for day, _ in valid)
    if (date.today() - latest).days > 7:
        raise ValueError('Company-name source is stale')
    repairs = []
    for ticker, old in sorted(current.items()):
        if '\ufffd' not in (old or ''):
            continue
        names = {str(r.get('stock_name') or '').strip() for day, r in valid
                 if day == latest and r.get('stock_id') == ticker
                 and r.get('type') in ('twse', 'tpex')}
        if len(names) != 1 or not next(iter(names)) or '\ufffd' in next(iter(names)):
            raise ValueError(f'Company-name source unavailable/ambiguous: {ticker}')
        repairs.append({'ticker':ticker,'before':old,'after':next(iter(names)),
                        'source_date':latest.isoformat()})
    return repairs


def repair_names(cur, dry_run=False, rows=None):
    cur.execute('SELECT ticker, company FROM industry_type')
    current = dict(cur.fetchall())
    if not any('\ufffd' in (name or '') for name in current.values()):
        return []
    if rows is None:
        from metadata_backfill import fetch_finmind
        rows = fetch_finmind()
    repairs = name_repairs(current, rows)
    if not dry_run:
        # Persist original values before any mutation; no schema changes.
        audit = Path(__file__).parent / '_debug' / ('company_name_repair_' + str(time.time_ns()) + '.json')
        audit.parent.mkdir(exist_ok=True)
        audit.write_text(json.dumps({'source':'FinMind TaiwanStockInfo','repairs':repairs},
                                   ensure_ascii=False,indent=2),encoding='utf-8')
        for item in repairs:
            cur.execute('UPDATE industry_type SET company=%s WHERE ticker=%s AND company=%s',
                        (item['after'],item['ticker'],item['before']))
            if cur.rowcount != 1:
                raise ValueError('Company-name source changed during repair')
    return repairs


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

    # Phase 5 (D052h): --days must be positive integer
    if args.days <= 0:
        print(f"ERROR: --days must be > 0 (got {args.days})", file=sys.stderr)
        sys.exit(2)

    # Phase 5 (D052h): --date must parse cleanly; use parameterized SQL
    if args.date:
        try:
            from datetime import datetime as _dt
            _dt.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            print(f"ERROR: --date must be YYYY-MM-DD (got {args.date!r})", file=sys.stderr)
            sys.exit(2)

    conn = pymysql.connect(**DB)
    cur = conn.cursor()
    try:
        repairs = repair_names(cur, args.dry_run)
    except Exception as exc:
        conn.rollback()
        conn.close()
        print(f'[company-refresh] company-name repair failed: {type(exc).__name__}',file=sys.stderr)
        return 1
    print(f'[company-refresh] canonical encoding repairs: {len(repairs)}')

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
        conn.commit()
        print("[company-refresh] nothing to do")
        conn.close()
        return 0

    # Update via JOIN. Use UPDATE ... JOIN syntax (MySQL).
    # L (D052h): source i.company must be non-blank — don't overwrite
    # valid daily_data2_full.company with NULL/blank from industry_type.
    t0 = time.time()
    cur.execute(f"""
        UPDATE daily_data2_full d
        JOIN industry_type i ON d.ticker = i.ticker
        SET d.company = i.company
        WHERE {date_filter}
          AND i.company IS NOT NULL
          AND TRIM(i.company) <> ''
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
