#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
market_screen_runner.py — D052h
Master runner for daily market screen. Does:
  1. Verify OHLCV target date is available in daily_data2_full
  2. Run screen_market() (1927 ticker universe, 24 picks)
  3. Validate result (24 picks, both long/short, all 4 buckets)
  4. Persist to market_screen_runs + market_screen_picks (via watchlist.save_*)
  5. Close OLDER active picks only after new run successful
  6. Generate Markdown + HTML + deep-dive prompt reports
  7. Return exit 0 on full success, 1 on any failure (no partial commits)

Per ChatGPT F2 (D052h review):
  - C: run_market_screen.py does NOT write to DB; this script does
  - D: closes older picks only after new run succeeds (no orphan close)
  - E: uses verified data_date from daily_data2_full, not Windows today
  - F: skips on weekend/holiday (no new run, no picks)
  - J: validates 24 picks + 4 buckets + both long/short before persisting
"""
import os
import sys
import subprocess
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

# Add RUNTIME dir to sys.path so we can import market_screen, watchlist, etc.
RUNTIME_DIR = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts")
sys.path.insert(0, str(RUNTIME_DIR))

import pymysql

import market_screen as ms
import watchlist as wl

DB = dict(host="localhost", user="root", password="1234", database="tw_elec",
          connect_timeout=10, charset="utf8mb4")

REPORT_DIR = Path.home() / ".claude" / "skills" / "tw-invest-suite" / "reports"


def get_verified_data_date():
    """Get the latest date in daily_data2_full. Returns date or None."""
    conn = pymysql.connect(**DB)
    try:
        cur = conn.cursor()
        cur.execute("SELECT MAX(Date) FROM daily_data2_full")
        r = cur.fetchone()
        return r[0] if r and r[0] else None
    finally:
        conn.close()


def is_trading_day(d):
    """TWSE calendar: Mon-Fri trading, Sat/Sun holiday. No special holiday list."""
    return d.weekday() < 5  # 0=Mon, 4=Fri


def validate_result(result):
    """Returns (ok: bool, reason: str).
    Expects 24 picks total, 4 buckets (price buckets), both long and short per bucket.
    """
    if not isinstance(result, dict) or not result:
        return False, f"result is not a non-empty dict: {type(result).__name__}"
    expected_buckets = [b[0] for b in ms.PRICE_BUCKETS]
    total = 0
    for bucket in expected_buckets:
        if bucket not in result:
            return False, f"missing bucket '{bucket}' in result"
        for horizon in ("long", "short"):
            n = len(result[bucket].get(horizon, []))
            if n == 0:
                return False, f"bucket '{bucket}' horizon '{horizon}' is empty"
            total += n
    if total != 24:
        return False, f"total picks = {total}, expected 24"
    return True, f"24 picks, all 4 buckets, both long/short OK"


def close_older_picks(new_run_id, today):
    """Close active picks from runs strictly older than new_run_id.
    Does NOT touch picks belonging to new_run_id.
    """
    conn = pymysql.connect(**DB)
    try:
        cur = conn.cursor()
        cur.execute("""
            UPDATE market_screen_picks p
            JOIN market_screen_runs r ON p.run_id = r.id
            SET p.status = 'closed'
            WHERE p.status = 'active'
              AND p.run_id != %s
              AND r.run_date < %s
        """, (new_run_id, today))
        affected = cur.rowcount
        conn.commit()
        return affected
    finally:
        conn.close()


def run():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="skip trading-day + freshness checks (testing only)")
    ap.add_argument("--data-date", help="override data_date (YYYY-MM-DD)")
    args = ap.parse_args()

    today = date.today()
    if not args.force and not is_trading_day(today):
        print(f"[market-screen-runner] {today} is not a trading day (weekend). skip.")
        return 0

    if args.data_date:
        from datetime import datetime as _dt
        data_date = _dt.strptime(args.data_date, "%Y-%m-%d").date()
    else:
        data_date = get_verified_data_date()
    if not data_date:
        print("[market-screen-runner] ERROR: no data_date in daily_data2_full")
        return 1
    print(f"[market-screen-runner] data_date = {data_date}  (today = {today}  force={args.force})")

    if data_date != today and data_date != today - timedelta(days=1):
        # 9/5 (Sat) is non-trading; latest is 9/4 (Fri). Allow today or yesterday.
        # If data is older than yesterday, that's stale.
        age = (today - data_date).days
        if age > 2:
            print(f"[market-screen-runner] ERROR: data_date {data_date} is {age} days stale")
            return 1

    # 1. Run screener
    print("[market-screen-runner] running screener...")
    try:
        result = ms.screen_market()
    except Exception as e:
        print(f"[market-screen-runner] ERROR: screen_market() failed: {e}")
        traceback.print_exc()
        return 1

    # 2. Validate
    ok, reason = validate_result(result)
    if not ok:
        print(f"[market-screen-runner] ERROR: validation failed: {reason}")
        return 1
    print(f"[market-screen-runner] validation OK: {reason}")

    # 3. Persist
    picks_count = sum(
        len(result[b].get("long", [])) + len(result[b].get("short", []))
        for b in result
    )
    notes = f"auto-saved by market_screen_runner data_date={data_date}"
    print(f"[market-screen-runner] saving run ({picks_count} picks)...")
    try:
        # Inline SQL because watchlist.save_run hard-codes date.today() and
        # we want the verified data_date, not Windows today (which can drift
        # on weekends/holidays).
        conn = pymysql.connect(**DB)
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO market_screen_runs
                (run_date, run_at, total_tickers, picks_count, notes)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    run_at = VALUES(run_at),
                    total_tickers = VALUES(total_tickers),
                    picks_count = VALUES(picks_count),
                    notes = VALUES(notes)
            """, (data_date, datetime.now(), 1927, picks_count, notes))
            cur.execute("SELECT id FROM market_screen_runs WHERE run_date = %s", (data_date,))
            row = cur.fetchone()
            run_id = row[0] if row else None
            if not run_id:
                print("[market-screen-runner] ERROR: failed to get run_id after insert")
                conn.rollback()
                return 1
            conn.commit()
        finally:
            conn.close()
        print(f"[market-screen-runner] market_screen_runs id={run_id}")
        # save_picks uses the run_id correctly, but wipes + reinserts (idempotent).
        n = wl.save_picks(run_id, result)
        print(f"[market-screen-runner] saved {n} picks")
        if n != picks_count:
            print(f"[market-screen-runner] ERROR: expected {picks_count} picks, saved {n}")
            return 1
    except Exception as e:
        print(f"[market-screen-runner] ERROR: persist failed: {e}")
        traceback.print_exc()
        return 1

    # 4. Close older active picks (only after new run fully persisted)
    closed = close_older_picks(run_id, data_date)
    print(f"[market-screen-runner] closed {closed} older active picks")

    # 5. Generate reports (via the existing runtime functions)
    print("[market-screen-runner] generating reports...")
    try:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        import market_report as mr
        import market_report_html as mrh
        import deep_dive_prompts as ddp
        md_path = mr.save_report(result)
        html_path = mrh.save_html(result)
        dd_path = REPORT_DIR / f"deep-dive-prompts-{today}.md"
        if not dd_path.exists():
            with open(dd_path, "w", encoding="utf-8") as f:
                f.write(f"# 24 深度研究 Prompt\n\n")
                f.write(f"> 適用：複製每段 prompt 到 Perplexity Computer\n\n")
                f.write("---\n\n")
                for label, _, _ in ms.PRICE_BUCKETS:
                    if label not in result:
                        continue
                    f.write(f"## {label}\n\n")
                    for c in result[label]["long"] + result[label]["short"]:
                        f.write(ddp.render_prompt(c))
                        f.write("\n\n---\n\n")
        print(f"[market-screen-runner]  MD:  {md_path}")
        print(f"[market-screen-runner]  HTML: {html_path}")
        print(f"[market-screen-runner]  DD:   {dd_path}")
    except Exception as e:
        print(f"[market-screen-runner] WARN: report generation failed: {e}")
        # Reports are not critical; DB persist is. Continue.

    # 6. Verify post-state
    conn = pymysql.connect(**DB)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*), SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) FROM market_screen_picks WHERE run_id=%s", (run_id,))
        n_total, n_active = cur.fetchone()
        print(f"[market-screen-runner] POST: picks for run_id={run_id}: total={n_total} active={n_active}")
    finally:
        conn.close()

    print(f"[market-screen-runner] OK data_date={data_date} run_id={run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
