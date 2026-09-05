#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
market_screen_runner.py — D052h-fixup
Master runner for daily market screen. Does:
  1. Verify trading day (weekday) AND data_date == today AND ticker count >= 1900
  2. Skip if market_screen_runs already has a successful run for data_date
  3. Run screen_market() (1927 ticker universe, 24 picks)
  4. Validate result (24 picks, both long/short, all 4 buckets)
  5. SINGLE DB transaction: upsert run + replace picks + close older picks
  6. Generate Markdown + HTML + deep-dive prompt reports (all same data_date)
  7. Exit 0 only on full success; any failure rolls back DB and exits 1

Per D052h-fixup:
  - Freshness: data_date MUST == today on trading day. No yesterday, no age=2.
  - Single transaction: all DB writes in one BEGIN/COMMIT, rollback on any failure.
  - Skip if existing run for data_date (idempotent).
  - Document that weekday check is not a real TWSE holiday calendar.
  - All 3 artifacts regenerated consistently; any artifact failure -> exit 1.
"""
import os
import sys
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

# RUNTIME_DIR provides market_screen, watchlist, market_report, market_report_html, deep_dive_prompts
RUNTIME_DIR = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts")
sys.path.insert(0, str(RUNTIME_DIR))

import pymysql
import market_screen as ms
import watchlist as wl
import market_report as mr
import market_report_html as mrh
import deep_dive_prompts as ddp

DB = dict(host="localhost", user="root", password="1234", database="tw_elec",
          connect_timeout=10, charset="utf8mb4")

REPORT_DIR = Path.home() / ".claude" / "skills" / "tw-invest-suite" / "reports"
MIN_TICKERS_FOR_RUN = 1900  # minimum data_date ticker count
TOTAL_UNIVERSE = 1927        # approximate full market screen universe

# D052h-fixup version stamp. If you change behavior, bump.
SCRIPT_VERSION = "D052h-fixup-1"


def is_trading_day(d):
    """Mon-Fri trading day. KNOWN LIMITATION: not a full TWSE holiday calendar.
    Holidays like 雙十, 春節, etc. are NOT excluded. Holiday detection would
    require a holiday list (TWSE publishes annually).
    For a personal project with weekly close on weekends, this is acceptable.
    Documented in D052h-fixup MD.
    """
    return d.weekday() < 5


def get_verified_data_date():
    """Returns (data_date, n_tickers) or (None, 0)."""
    conn = pymysql.connect(**DB)
    try:
        cur = conn.cursor()
        cur.execute("SELECT MAX(Date), COUNT(DISTINCT ticker) FROM daily_data2_full")
        row = cur.fetchone()
        return (row[0], row[1] or 0) if row else (None, 0)
    finally:
        conn.close()


def has_existing_successful_run(data_date):
    """True if market_screen_runs has a run with picks_count==24 for data_date."""
    conn = pymysql.connect(**DB)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, picks_count FROM market_screen_runs WHERE run_date = %s",
            (data_date,)
        )
        row = cur.fetchone()
        return row is not None and row[1] == 24
    finally:
        conn.close()


def validate_result(result):
    """Returns (ok: bool, reason: str). Expects 24 picks across 4 buckets x 2 horizons."""
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


def persist_atomic(data_date, picks_count, notes, result):
    """Single MySQL transaction: UPSERT run + DELETE/INSERT picks + CLOSE older.
    Returns (run_id, closed_count) on success. Raises on any failure (DB rolled back).
    """
    conn = pymysql.connect(**DB)
    try:
        cur = conn.cursor()
        try:
            conn.begin()  # explicit BEGIN
            # 1. UPSERT market_screen_runs
            cur.execute("""
                INSERT INTO market_screen_runs
                (run_date, run_at, total_tickers, picks_count, notes)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    run_at = VALUES(run_at),
                    total_tickers = VALUES(total_tickers),
                    picks_count = VALUES(picks_count),
                    notes = VALUES(notes)
            """, (data_date, datetime.now(), TOTAL_UNIVERSE, picks_count, notes))
            cur.execute("SELECT id FROM market_screen_runs WHERE run_date = %s", (data_date,))
            row = cur.fetchone()
            if not row:
                raise RuntimeError("failed to get run_id after upsert")
            run_id = row[0]

            # 2. REPLACE picks (delete + bulk insert) for this run_id
            cur.execute("DELETE FROM market_screen_picks WHERE run_id = %s", (run_id,))
            rows_to_insert = []
            for bucket_label, picks_by_horizon in result.items():
                for horizon in ("long", "short"):
                    for c in picks_by_horizon.get(horizon, []):
                        rows_to_insert.append((
                            run_id, c.ticker, c.name, c.industry or "",
                            horizon, bucket_label,
                            float(c.close), float(c.change_pct or 0),
                            int(c.volume),
                            float(c.market_cap) if c.market_cap else None,
                            float(c.excess_return_60d or 0),
                            float(c.excess_return_240d or 0),
                            None,  # score
                            c.zen_summary or "",
                        ))
            if not rows_to_insert:
                raise RuntimeError("no picks to insert (validation passed but list is empty)")
            cur.executemany("""
                INSERT INTO market_screen_picks
                (run_id, ticker, name, industry, horizon, bucket,
                 close_at_pick, change_pct, volume, market_cap,
                 excess_return_60d, excess_return_240d, score, rationale)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, rows_to_insert)
            if len(rows_to_insert) != picks_count:
                raise RuntimeError(
                    f"expected {picks_count} picks inserted, got {len(rows_to_insert)}"
                )

            # 3. CLOSE older active picks (from earlier run_date)
            cur.execute("""
                UPDATE market_screen_picks p
                JOIN market_screen_runs r ON p.run_id = r.id
                SET p.status = 'closed'
                WHERE p.status = 'active'
                  AND p.run_id != %s
                  AND r.run_date < %s
            """, (run_id, data_date))
            closed_count = cur.rowcount

            conn.commit()
            return run_id, closed_count
        except Exception:
            conn.rollback()
            raise
    finally:
        conn.close()


def generate_artifacts(data_date, result):
    """Generate MD + HTML + DD. Returns list of (path, ok) tuples. Any failure
    makes the overall task fail (caller decides).
    """
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    errors = []
    # MD
    try:
        md_path = mr.save_report(result)
        paths.append((md_path, True))
    except Exception as e:
        paths.append((None, False))
        errors.append(f"MD: {e}")
    # HTML
    try:
        html_path = mrh.save_html(result)
        paths.append((html_path, True))
    except Exception as e:
        paths.append((None, False))
        errors.append(f"HTML: {e}")
    # DD
    try:
        dd_path = REPORT_DIR / f"deep-dive-prompts-{data_date}.md"
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
        paths.append((str(dd_path), True))
    except Exception as e:
        paths.append((None, False))
        errors.append(f"DD: {e}")
    return paths, errors


def run():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="skip trading-day + freshness checks (testing only)")
    ap.add_argument("--data-date", help="override data_date (YYYY-MM-DD)")
    args = ap.parse_args()

    print(f"[runner] version={SCRIPT_VERSION}")

    today = date.today()

    # === Freshness gate ===
    if not args.force and not is_trading_day(today):
        print(f"[runner] {today} is weekend. skip. (NOT a full TWSE holiday calendar — known limitation)")
        return 0

    if args.data_date:
        data_date = datetime.strptime(args.data_date, "%Y-%m-%d").date()
        n_tickers = None  # not checked in override mode
    else:
        data_date, n_tickers = get_verified_data_date()
        if data_date is None:
            print("[runner] ERROR: no data in daily_data2_full. skip.")
            return 0
        if n_tickers < MIN_TICKERS_FOR_RUN:
            print(f"[runner] ERROR: data_date {data_date} has only {n_tickers} tickers (< {MIN_TICKERS_FOR_RUN}). skip.")
            return 0
        if not args.force and data_date != today:
            print(f"[runner] ERROR: data_date {data_date} != today {today}. stale (age={(today-data_date).days} days). skip.")
            return 0

    print(f"[runner] data_date={data_date} today={today} force={args.force}")

    # === Skip if already done ===
    if not args.force and has_existing_successful_run(data_date):
        print(f"[runner] market_screen_runs already has run for {data_date}. skip (idempotent).")
        return 0

    # === Run screener ===
    print("[runner] running screener...")
    try:
        result = ms.screen_market()
    except Exception as e:
        print(f"[runner] ERROR: screen_market() failed: {e}")
        traceback.print_exc()
        return 1

    ok, reason = validate_result(result)
    if not ok:
        print(f"[runner] ERROR: validation failed: {reason}")
        return 1
    print(f"[runner] validation OK: {reason}")

    picks_count = sum(
        len(result[b].get("long", [])) + len(result[b].get("short", []))
        for b in result
    )

    # === Persist atomic ===
    notes = f"auto-saved by market_screen_runner v={SCRIPT_VERSION} data_date={data_date}"
    print(f"[runner] persisting atomic ({picks_count} picks)...")
    try:
        run_id, closed_count = persist_atomic(data_date, picks_count, notes, result)
        print(f"[runner] market_screen_runs id={run_id}, closed {closed_count} older active picks")
    except Exception as e:
        print(f"[runner] ERROR: persist failed (DB rolled back): {e}")
        traceback.print_exc()
        return 1

    # === Generate artifacts (after DB committed) ===
    print("[runner] generating artifacts...")
    paths, errors = generate_artifacts(data_date, result)
    for p, ok in paths:
        print(f"[runner]   {'OK' if ok else 'FAIL'}: {p}")
    if errors:
        print(f"[runner] WARN: artifact generation had errors: {errors}")
        # Per D052h-fixup: artifact failure = task exit nonzero
        # But DB is already committed, so data is preserved
        return 1

    # === Verify post-state ===
    conn = pymysql.connect(**DB)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*), SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) "
            "FROM market_screen_picks WHERE run_id=%s",
            (run_id,)
        )
        n_total, n_active = cur.fetchone()
        print(f"[runner] POST: run_id={run_id} picks total={n_total} active={n_active}")
        if n_total != 24 or (n_active or 0) != 24:
            print(f"[runner] ERROR: post-state validation failed: total={n_total} active={n_active}")
            return 1
    finally:
        conn.close()

    print(f"[runner] OK data_date={data_date} run_id={run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
