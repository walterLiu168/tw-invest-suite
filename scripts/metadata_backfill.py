#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
metadata_backfill.py — D052c
Stage-and-promote metadata backfill for industry_type from FinMind TaiwanStockInfo.

Per design (see docs/chatgpt_debug/2026-09-04-04-verify-chatgpt-claims.md):
  1. Fetch FinMind TaiwanStockInfo (all rows, default ~365 days)
  2. Filter: date = current_date, type IN ('twse', 'tpex'),
     stock_name/industry_category not NULL/empty
  3. Allowlist mode (--batch=12) or full mode (--all)
  4. For each ticker, count distinct industry_category on current_date:
     - 1 distinct category -> promote to industry_type
     - 2+ distinct categories -> quarantine (manual review)
  5. Name-based filter: reject ETF/ETN/warrant (extra protection)
  6. Insert into:
     - industry_type (promote)
     - metadata_quarantine (fail)
     - metadata_staging (audit trail of raw rows)

Usage:
  python metadata_backfill.py --batch=3485,4195,...,7842
  python metadata_backfill.py --all   # recurring job, all twse/tpex 普通股
  python metadata_backfill.py --batch=3485 --dry-run
"""
import argparse
import os
import sys
import json
import ssl
import time
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

import pymysql

try:
    import certifi
    _CA_FILE = certifi.where()
except ImportError:
    _CA_FILE = None  # fall back to system trust store

# ----- config -----
DB = dict(host="localhost", user="root", password="1234", database="tw_elec",
          connect_timeout=10, charset="utf8mb4")
TOKEN_FILE = Path.home() / ".finmind_token"
API = "https://api.finmindtrade.com/api/v4/data"
DATASET = "TaiwanStockInfo"
SOURCE_NAME = "finmind_taiwan_stock_info"

ETF_KEYWORDS = ["ETF", "ETN", "權證", "認購", "認售", "warrant", "牛證", "熊證",
                "受益憑證", "存託憑證", "TDR"]


def get_token():
    p = TOKEN_FILE
    if not p.exists():
        print(f"ERROR: {p} missing", file=sys.stderr)
        sys.exit(2)
    raw = p.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        raw = raw[3:]
    return raw.decode("utf-8").strip()


def fetch_finmind():
    """Fetch TaiwanStockInfo. Returns list of dicts."""
    # Use certifi CA bundle if available; otherwise system trust store.
    # IMPORTANT: do NOT disable verification — FinMind cert chain is fine if
    # we point at the right bundle (Windows system store is sometimes missing
    # the Subject Key Identifier that newer OpenSSL expects).
    if _CA_FILE:
        ctx = ssl.create_default_context(cafile=_CA_FILE)
    else:
        ctx = ssl.create_default_context()
    url = f"{API}?dataset={DATASET}&token={get_token()}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mavis/1.0"})
    raw = urllib.request.urlopen(req, timeout=30, context=ctx).read()
    data = json.loads(raw)
    if data.get("status") != 200 or data.get("msg") != "success":
        raise RuntimeError(f"FinMind error: status={data.get('status')} msg={data.get('msg')}")
    return data["data"]


def ensure_tables(cur):
    """Create staging + quarantine tables if missing. Idempotent."""
    cur.execute("""
        CREATE TABLE IF NOT EXISTS metadata_staging (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            run_id VARCHAR(40) NOT NULL,
            fetched_at DATETIME NOT NULL,
            source VARCHAR(40) NOT NULL,
            ticker VARCHAR(10) NOT NULL,
            stock_name VARCHAR(100),
            industry_category VARCHAR(80),
            type VARCHAR(20),
            source_date DATE,
            INDEX (run_id), INDEX (ticker)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS metadata_quarantine (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            run_id VARCHAR(40) NOT NULL,
            inserted_at DATETIME NOT NULL,
            ticker VARCHAR(10) NOT NULL,
            stock_name VARCHAR(100),
            type VARCHAR(20),
            source_date DATE,
            candidate_categories JSON,
            reason TEXT NOT NULL,
            resolved_at DATETIME NULL,
            resolved_to_industry VARCHAR(80) NULL,
            INDEX (run_id), INDEX (ticker), INDEX (resolved_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def insert_staging(cur, run_id, rows):
    if not rows:
        return 0
    vals = [(run_id, row["_fetched_at"], SOURCE_NAME, row["stock_id"],
             row.get("stock_name"), row.get("industry_category"),
             row.get("type"), row.get("date"))
            for row in rows]
    cur.executemany("""INSERT INTO metadata_staging
                       (run_id, fetched_at, source, ticker, stock_name,
                        industry_category, type, source_date)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""", vals)
    return len(vals)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--batch", help="comma-separated ticker allowlist (e.g. 3485,4195)")
    ap.add_argument("--all", action="store_true", help="process all twse/tpex 普通股")
    ap.add_argument("--dry-run", action="store_true", help="no DB writes")
    ap.add_argument("--run-id", default=date.today().isoformat() + "-" + str(int(time.time())))
    args = ap.parse_args()

    if not args.batch and not args.all:
        print("ERROR: must pass --batch=... or --all", file=sys.stderr)
        sys.exit(2)

    allowlist = None
    if args.batch:
        allowlist = {t.strip() for t in args.batch.split(",") if t.strip()}
        print(f"[metadata-backfill] run_id={args.run_id} mode=batch size={len(allowlist)}")
    else:
        print(f"[metadata-backfill] run_id={args.run_id} mode=all")

    # ---- Pre-load existing state (idempotency for recurring runs) ----
    # Skip tickers that are already resolved: either already in industry_type
    # (promoted) or already in metadata_quarantine with resolved_at IS NULL
    # (still pending review). This prevents the staging/quarantine tables from
    # accumulating duplicate rows on every recurring run.
    conn = pymysql.connect(**DB)
    cur = conn.cursor()
    ensure_tables(cur)
    conn.commit()
    cur.execute("SELECT ticker FROM industry_type")
    already_promoted = {r[0] for r in cur.fetchall()}
    cur.execute("SELECT DISTINCT ticker FROM metadata_quarantine WHERE resolved_at IS NULL")
    already_quarantined = {r[0] for r in cur.fetchall()}
    conn.close()
    if allowlist is not None:
        skipped = sorted(t for t in allowlist if t in already_promoted or t in already_quarantined)
        if skipped:
            print(f"[metadata-backfill] skipping {len(skipped)} already-resolved tickers: {skipped}")
            allowlist -= set(skipped)
            if not allowlist:
                print("[metadata-backfill] all allowlist tickers already resolved. nothing to do.")
                return 0

    print(f"[metadata-backfill] fetching FinMind {DATASET}...")
    rows = fetch_finmind()
    print(f"[metadata-backfill] fetched {len(rows)} raw rows")
    fetched_at = time.strftime("%Y-%m-%d %H:%M:%S")

    # Tag fetched time on each row for staging
    for r in rows:
        r["_fetched_at"] = fetched_at

    # Filter: skip literal "None" date, keep only current_date
    valid = [r for r in rows if r.get("date") and r["date"] != "None"]
    if not valid:
        print("ERROR: no rows with valid date", file=sys.stderr)
        sys.exit(1)
    current_date = max(r["date"] for r in valid)
    print(f"[metadata-backfill] current_date = {current_date}  ({len(valid)} rows on/after)")

    # Keep only current_date rows
    on_date = [r for r in valid if r["date"] == current_date]
    print(f"[metadata-backfill] rows on current_date: {len(on_date)}")

    # ROW-LEVEL filter: drop non twse/tpex (e.g. emerging history) BEFORE
    # per-ticker group. This is the correct filter order — anything left after
    # this is known to be a currently listed 普通股. (See D052c review F4 fix.)
    before_type = len(on_date)
    on_date = [r for r in on_date if r.get("type") in ("twse", "tpex")]
    dropped = before_type - len(on_date)
    if dropped:
        print(f"[metadata-backfill] dropped {dropped} rows with type not in (twse, tpex)")

    # Apply allowlist if --batch
    if allowlist is not None:
        on_date = [r for r in on_date if r["stock_id"] in allowlist]
        missing = allowlist - {r["stock_id"] for r in on_date}
        if missing:
            print(f"[metadata-backfill] WARN: {len(missing)} allowlist tickers absent on current_date: {sorted(missing)}")
        print(f"[metadata-backfill] after allowlist filter: {len(on_date)} rows")

    # Per-ticker grouping on current_date
    by_ticker = defaultdict(list)
    for r in on_date:
        by_ticker[r["stock_id"]].append(r)

    promote = []  # [(ticker, stock_name, industry_category, type, source_date)]
    quarantine = []  # [(ticker, stock_name, type, source_date, candidate_categories, reason)]

    for ticker in sorted(by_ticker):
        rows_t = by_ticker[ticker]
        types = {r["type"] for r in rows_t if r.get("type")}
        names = {r["stock_name"] for r in rows_t if r.get("stock_name")}
        cats = {r["industry_category"] for r in rows_t if r.get("industry_category")}
        # Use any row for type/name/date (all should be same ticker on same date)
        any_row = rows_t[0]
        type_v = any_row.get("type") or ""
        name_v = next(iter(names), None)
        date_v = any_row.get("date")

        # Required-field check
        if not name_v or not cats:
            quarantine.append((ticker, name_v, type_v, date_v, sorted(cats),
                              f"missing required field (name={name_v}, cats={cats})"))
            continue
        if not (types & {"twse", "tpex"}):
            quarantine.append((ticker, name_v, type_v, date_v, sorted(cats),
                              f"type not in (twse, tpex): {types}"))
            continue
        # ETF/ETN/warrant name check
        etf_hit = [kw for kw in ETF_KEYWORDS if kw in name_v]
        if etf_hit:
            quarantine.append((ticker, name_v, type_v, date_v, sorted(cats),
                              f"name contains suspicious keyword: {etf_hit}"))
            continue
        # Multi-category: quarantine entire ticker (user rule)
        if len(cats) > 1:
            quarantine.append((ticker, name_v, type_v, date_v, sorted(cats),
                              f"multi-category on current_date: {sorted(cats)}"))
            continue
        # Single category -> promote
        cat_v = next(iter(cats))
        promote.append((ticker, name_v, cat_v, type_v, date_v))

    print(f"\n[metadata-backfill] PROMOTE candidates: {len(promote)}")
    for t, n, c, ty, d in promote:
        print(f"  + {t}  {n}  [{c}]  type={ty}")
    print(f"\n[metadata-backfill] QUARANTINE candidates: {len(quarantine)}")
    for t, n, ty, d, cs, reason in quarantine:
        print(f"  ! {t}  {n}  type={ty}  -> {reason}")

    if args.dry_run:
        print("\n[metadata-backfill] DRY-RUN: no DB writes")
        return 0

    # DB write
    conn = pymysql.connect(**DB)
    cur = conn.cursor()
    try:
        # ensure_tables already called in preflight; this is a no-op
        pass

        # 1. Insert ALL on_date rows to staging (audit trail)
        # (Use all current_date rows, not just filtered, for full audit)
        all_current_date = [r for r in valid if r["date"] == current_date]
        if allowlist is not None:
            all_current_date = [r for r in all_current_date if r["stock_id"] in allowlist]
        n = insert_staging(cur, args.run_id, all_current_date)
        print(f"\n[metadata-backfill] inserted {n} rows to metadata_staging")

        # 2. Promote
        if promote:
            for ticker, name, cat, ty, src_date in promote:
                cur.execute("""INSERT INTO industry_type (ticker, company, industry, last_updated)
                               VALUES (%s, %s, %s, NOW())
                               ON DUPLICATE KEY UPDATE
                                 company = VALUES(company),
                                 industry = VALUES(industry),
                                 last_updated = NOW()""",
                            (ticker, name, cat))
            print(f"[metadata-backfill] promoted {len(promote)} tickers to industry_type")

        # 3. Quarantine
        if quarantine:
            for ticker, name, ty, src_date, cats, reason in quarantine:
                cur.execute("""INSERT INTO metadata_quarantine
                               (run_id, inserted_at, ticker, stock_name, type, source_date,
                                candidate_categories, reason)
                               VALUES (%s, NOW(), %s, %s, %s, %s, %s, %s)""",
                            (args.run_id, ticker, name, ty, src_date,
                             json.dumps(cats, ensure_ascii=False), reason))
            print(f"[metadata-backfill] quarantined {len(quarantine)} tickers")

        conn.commit()

        # 4. Verify post-state
        cur.execute("SELECT COUNT(*) FROM industry_type")
        new_total = cur.fetchone()[0]
        cur.execute("""SELECT COUNT(*) FROM industry_type
                       WHERE ticker IN ({})""".format(",".join(["%s"]*len(allowlist)))
                    if allowlist else "SELECT 0",
                    list(allowlist) if allowlist else [])
        in_master = cur.fetchone()[0] if allowlist else 0
        cur.execute("""SELECT COUNT(*) FROM metadata_quarantine
                       WHERE resolved_at IS NULL""")
        open_quar = cur.fetchone()[0]

        print(f"\n[metadata-backfill] POST-STATE:")
        print(f"  industry_type total:        {new_total}")
        print(f"  allowlist in master:        {in_master}/{len(allowlist) if allowlist else 0}")
        print(f"  open quarantine (cumulative): {open_quar}")

    except Exception as e:
        conn.rollback()
        print(f"ERROR: {e}", file=sys.stderr)
        raise
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
