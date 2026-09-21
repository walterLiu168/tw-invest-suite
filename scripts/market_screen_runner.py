#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
market_screen_runner.py — D052h-fixup4
Master runner for daily market screen.

D052h-fixup4 changes (per ChatGPT manager read-only review):
  - has_metadata_marker now reads the marker with `utf-8-sig` so it
    accepts both BOM and BOM-less markers. The producer
    (metadata_backfill_daily.ps1) historically wrote UTF-8 with BOM on
    Windows PowerShell 5.1; the consumer must tolerate that until the
    producer is upgraded to UTF-8 without BOM.
  - SCRIPT_VERSION bumped to "D052h-fixup4".

D052h-fixup3 changes (kept):
  - Repair-only fully reconstructs MD + HTML + DD using the existing
    mr.save_report / mrh.save_html / ddp.render_prompt (no second
    renderer). After generation, re-runs has_complete_run_for_data_date;
    only returns success when missing=[].
  - Unified artifact date contract: mr.save_report / mrh.save_html now
    accept an optional data_date; market_screen_runner always passes
    data_date (never datetime.now()) so daily run, --force --data-date,
    and repair all produce artifacts named with the actual data date.
  - metadata marker check parses the marker file's target_date + status
    lines (no longer just .exists()).

D052h-fixup2 changes (kept):
  - F1: get_verified_data_date counts only MAX(Date), not all history
  - F2: trading day with bad data exits 1, not 0 (only weekend or
        idempotent re-run can exit 0)
  - F4: verify metadata-backfill success marker for target data_date
  - F5: --force --data-date validates the override date has data
  - F7: has_complete_run_for_data_date verifies 24 picks + 3 artifacts
        + falls back to repair-only when only artifacts are missing

D052h-fixup changes (kept):
  - Single DB transaction (rollback on any failure)
  - data_date must == today on trading day (no yesterday, no age=2)
  - Weekend skip via is_trading_day (weekday-only, NOT full TWSE holiday)
  - Artifact failure -> exit 1 (DB already committed)

Pending (NOT addressed in fixup4):
  - H: existing-ticker reconciliation
  - J: 7768 per-day quarantine accumulation
  - T2/T3 live: mocked tests in tests/ pass; live needs disposable DB
  - T4 live: deterministic unit test passes; live stale-OHLCV needs
    a real trading day with no fresh data
  - 9/7 trading-day live cron (today is Mon 9/7; first real run)
  - health-check LastResult=1 root cause
  - production residue cleanup (run_id=3, 4, 6) — pending Walter
  - push approval (origin/main still at 8d48318)
"""
import argparse
import os
import sys
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

# D052h-fixup3: import the renderer modules from the git repo path FIRST
# so we get the data_date-aware save_report / save_html. The runtime copy
# (C:\Users\icemo\.claude\skills\tw-invest-suite\scripts) is added next
# as a fallback for transitive imports (market_screen, watchlist, etc.).
#
# Both paths must be on sys.path. We ensure REPO comes first; the test
# file or runtime may have already added RUNTIME, so we re-insert REPO
# AFTER (which keeps REPO ahead of RUNTIME because insert(0) is LIFO
# relative to existing entries).
REPO_SCRIPTS = Path(r"C:\Users\icemo\Projects\tw-invest-suite\scripts")
RUNTIME_DIR = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts")
# Remove RUNTIME from sys.path if present, then add REPO, then RUNTIME.
# Result: REPO is at front, RUNTIME next. This works regardless of what
# the test/caller did to sys.path beforehand.
for p in (str(REPO_SCRIPTS), str(RUNTIME_DIR)):
    while p in sys.path:
        sys.path.remove(p)
sys.path.insert(0, str(RUNTIME_DIR))
sys.path.insert(0, str(REPO_SCRIPTS))

import pymysql
import db_client as db
import market_screen as ms
import watchlist as wl
import market_report as mr
import market_report_html as mrh
import deep_dive_prompts as ddp
from market_calendar import expected_session

DB = {"connect_timeout": 10, "charset": "utf8mb4"}

REPORT_DIR = Path.home() / ".claude" / "skills" / "tw-invest-suite" / "reports"
# D052h-fixup2 F4: metadata-backfill writes target-date success marker here.
METADATA_MARKER_DIR = Path(r"C:\Users\icemo\Projects\tw-invest-suite\scripts\_debug")
MIN_TICKERS_FOR_RUN = 1900
TOTAL_UNIVERSE = 1927

SCRIPT_VERSION = "D052h-fixup4"


def expected_data_date(day, hour=None):
    """Use the nightly's 18:00 operational-day boundary for manual reruns."""
    hour = datetime.now().hour if hour is None else hour
    operational_day = day if hour >= 18 else day - timedelta(days=1)
    return date.fromisoformat(expected_session(operational_day))


def has_metadata_marker(data_date):
    """D052h-fixup4: parse marker file content, verify both target_date
    AND status. The marker is metadata_target_YYYY-MM-DD_OK.marker and
    contains a small key=value block written by metadata_backfill_daily.ps1:

        target_date=YYYY-MM-DD
        finished_at=ISO8601
        missing_count=N
        status=ok

    The producer (Windows PowerShell 5.1 `Set-Content -Encoding UTF8`)
    writes UTF-8 with BOM. We use `utf-8-sig` to strip any leading BOM
    on read so both BOM and BOM-less markers are accepted. (Future
    producer fix is in metadata_backfill_daily.ps1 to write UTF8NoBOM.)

    Returns True only if:
      - file exists
      - target_date line == data_date
      - status line == 'ok'
    """
    marker = METADATA_MARKER_DIR / f"metadata_target_{data_date.isoformat()}_OK.marker"
    if not marker.exists():
        return False
    try:
        # D052h-fixup4: utf-8-sig strips a leading BOM if present.
        # Without this, the first key would be "\ufefftarget_date" and
        # info.get("target_date") would silently return None.
        content = marker.read_text(encoding="utf-8-sig", errors="ignore")
    except OSError:
        return False
    info = {}
    for line in content.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            info[k.strip()] = v.strip()
    if info.get("status") != "ok":
        return False
    if info.get("target_date") != data_date.isoformat():
        return False
    return True


def is_trading_day(d):
    from market_calendar import is_session
    return is_session(d)


def get_verified_data_date():
    """F1 (D052h-fixup2): Returns (data_date, n_tickers) where n_tickers is
    the count for MAX(Date) ONLY, not all history.
    """
    conn = db.connect(**DB)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT Date, COUNT(DISTINCT ticker)
            FROM daily_data2_full
            WHERE Date = (SELECT MAX(Date) FROM daily_data2_full)
            GROUP BY Date
        """)
        row = cur.fetchone()
        return (row[0], row[1] or 0) if row else (None, 0)
    finally:
        conn.close()


def has_existing_run_for_data_date(data_date):
    """Returns the run_id (int) if market_screen_runs has a row for data_date, else None."""
    conn = db.connect(**DB)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM market_screen_runs WHERE run_date = %s", (data_date,))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def has_complete_run_for_data_date(data_date):
    """F7 (D052h-fixup2): True if market_screen_runs has a complete run for
    data_date: run metadata + 24 total picks + 24 active picks + 3 artifacts.
    Returns (run_id, complete, missing_artifacts).
    """
    conn = db.connect(**DB)
    try:
        cur = conn.cursor()
        cur.execute("SELECT id, picks_count FROM market_screen_runs WHERE run_date = %s", (data_date,))
        row = cur.fetchone()
        if not row:
            return (None, False, ["run_metadata"])
        run_id, picks_count = row
        cur.execute(
            "SELECT COUNT(*), SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) "
            "FROM market_screen_picks WHERE run_id = %s",
            (run_id,)
        )
        n_total, n_active = cur.fetchone()
        n_total = n_total or 0
        n_active = n_active or 0
        missing = []
        if picks_count != 24:
            missing.append("picks_count_mismatch")
        if n_total != 24:
            missing.append("picks_total_mismatch")
        if n_active != 24:
            missing.append("picks_active_mismatch")
        # Check artifacts
        md = REPORT_DIR / f"market-screen-{data_date}.md"
        html = REPORT_DIR / f"market-screen-{data_date}.html"
        dd = REPORT_DIR / f"deep-dive-prompts-{data_date}.md"
        if not md.exists():
            missing.append("md")
        if not html.exists():
            missing.append("html")
        if not dd.exists():
            missing.append("dd")
        return (run_id, not missing, missing)
    finally:
        conn.close()


def validate_result(result):
    """Returns (ok, reason)."""
    if not isinstance(result, dict) or not result:
        return False, f"result is not a non-empty dict: {type(result).__name__}"
    expected_buckets = [b[0] for b in ms.PRICE_BUCKETS]
    total = 0
    for bucket in expected_buckets:
        if bucket not in result:
            return False, f"missing bucket '{bucket}'"
        for horizon in ("long", "short"):
            n = len(result[bucket].get(horizon, []))
            if n == 0:
                return False, f"bucket '{bucket}' horizon '{horizon}' empty"
            total += n
    if total != 24:
        return False, f"total picks = {total}, expected 24"
    return True, f"24 picks, 4 buckets, both long/short OK"


def persist_atomic(data_date, picks_count, notes, result):
    """Single MySQL transaction: UPSERT run + DELETE/INSERT picks + CLOSE older.
    Returns (run_id, closed_count). Raises on any failure (rolled back).
    """
    conn = db.connect(**DB)
    try:
        cur = conn.cursor()
        try:
            conn.begin()
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
                            None,
                            c.zen_summary or "",
                        ))
            if not rows_to_insert:
                raise RuntimeError("no picks to insert")
            cur.executemany("""
                INSERT INTO market_screen_picks
                (run_id, ticker, name, industry, horizon, bucket,
                 close_at_pick, change_pct, volume, market_cap,
                 excess_return_60d, excess_return_240d, score, rationale)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, rows_to_insert)
            if len(rows_to_insert) != picks_count:
                raise RuntimeError(f"expected {picks_count}, got {len(rows_to_insert)}")

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
    """Generate MD + HTML + DD. Returns (paths, errors).
    D052h-fixup3: file names use data_date consistently (not datetime.now()).
    Compatible with daily run (data_date=today) and --force --data-date.
    """
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    errors = []
    try:
        md_path = mr.save_report(result, data_date=data_date)
        paths.append((md_path, True))
    except Exception as e:
        paths.append((None, False))
        errors.append(f"MD: {e}")
    try:
        html_path = mrh.save_html(result, data_date=data_date)
        paths.append((html_path, True))
    except Exception as e:
        paths.append((None, False))
        errors.append(f"HTML: {e}")
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


def _row_to_candidate(row):
    """Reconstruct an ms.Candidate from a market_screen_picks row.
    D052h-fixup3: fields not stored in the DB get safe defaults (0 / '')
    so the existing renderer patterns (mr.save_report, mrh.save_html,
    ddp.render_prompt) don't crash. The renderer guards (e.g. `if c.market_cap`)
    and `or 0` patterns handle the degraded fields.
    """
    (ticker, name, industry, horizon, bucket, close, chg_pct, vol,
     mc, er60, er240, rationale) = row
    return ms.Candidate(
        ticker=ticker,
        name=name or "",
        industry=industry or "",
        close=float(close) if close is not None else 0.0,
        change_pct=float(chg_pct) if chg_pct is not None else 0.0,
        volume=int(vol) if vol is not None else 0,
        # DB doesn't store these; renderer's `or 0` / `if c.X` guards skip
        # them when 0/None, so degraded repair output is acceptable.
        three_net=0,
        foreign_net=0,
        margin_balance=0,
        short_balance=0,
        foreign_ratio=0.0,
        sma13=0.0,
        sma27=0.0,
        sma54=0.0,
        rsi14=0.0,
        atr14=0.0,
        is_gap=0,
        excess_return_60d=float(er60) if er60 is not None else 0.0,
        excess_return_240d=float(er240) if er240 is not None else 0.0,
        market_cap=float(mc) if mc is not None else 0.0,
        horizon=horizon or "",
        zen_summary=rationale or "",
    )


def _build_result_from_picks(rows):
    """Group 24 Candidate rows into the {bucket: {long, short}} result dict
    that mr.save_report / mrh.save_html expect. Mirrors ms.PRICE_BUCKETS so
    the renderer iterates the same buckets.
    """
    result = {}
    for label, _, _ in ms.PRICE_BUCKETS:
        result[label] = {"long": [], "short": []}
    for row in rows:
        c = _row_to_candidate(row)
        bucket = c.zen_summary and ""  # rationale is the last column; use bucket
        # row order: (ticker, name, industry, horizon, bucket, close, ...)
        bucket_label = row[4] if len(row) > 4 else None
        if not bucket_label or bucket_label not in result:
            continue
        result[bucket_label][c.horizon].append(c)
    return result


def repair_only_artifacts(data_date, run_id):
    """D052h-fixup3: full reconstruction of MD + HTML + DD from the 24
    active picks in market_screen_picks. Reuses existing mr.save_report /
    mrh.save_html / ddp.render_prompt (no second renderer).

    After generation, re-runs has_complete_run_for_data_date(data_date);
    only returns success when missing=[].

    Returns (success, error_list).
    """
    print(f"[runner] repair-only for data_date={data_date} run_id={run_id}")
    conn = db.connect(**DB)
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT ticker, name, industry, horizon, bucket, close_at_pick,
                   change_pct, volume, market_cap, excess_return_60d,
                   excess_return_240d, rationale
            FROM market_screen_picks
            WHERE run_id = %s AND status = 'active'
        """, (run_id,))
        rows = cur.fetchall()
    finally:
        conn.close()

    if len(rows) != 24:
        return False, [f"expected 24 active picks, got {len(rows)}"]

    result = _build_result_from_picks(rows)
    # Sanity: 4 buckets x (long + short) = 24
    total = sum(len(result[b]["long"]) + len(result[b]["short"]) for b in result)
    if total != 24:
        return False, [f"reconstructed total = {total}, expected 24"]

    paths, errors = generate_artifacts(data_date, result)
    for p, ok in paths:
        print(f"[runner]   {'OK' if ok else 'FAIL'}: {p}")
    if errors:
        return False, [f"artifact errors: {errors}"]

    # D052h-fixup3: re-verify completeness; only return success if missing=[]
    _, complete, missing = has_complete_run_for_data_date(data_date)
    if not complete:
        return False, [f"after repair, still missing: {missing}"]
    return True, []


def run():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true",
                    help="skip trading-day + freshness checks (testing only)")
    ap.add_argument("--data-date", help="override data_date (YYYY-MM-DD)")
    ap.add_argument("--refresh-existing", action="store_true",
                    help="Recompute existing picks after final source refresh; keep normal validation gates")
    args = ap.parse_args()

    print(f"[runner] version={SCRIPT_VERSION}")
    today = date.today()

    # === F2: only weekend/holiday or successful re-run can exit 0 ===
    # F2 means: even on a trading day, if data is missing/partial/stale,
    # we MUST exit 1. Only:
    #   - is_trading_day(today) is False (weekend/holiday) → exit 0
    #   - has_complete_run_for_data_date(today) is True → exit 0
    # Otherwise exit 1.

    if not args.force and not is_trading_day(today):
        print(f"[runner] {today} is weekend. skip (NOT full TWSE holiday calendar — known limitation)")
        return 0

    # Resolve data_date
    if args.data_date:
        override_date = datetime.strptime(args.data_date, "%Y-%m-%d").date()
        # F5: --data-date MUST equal the screener's actual data source.
        # The screener (ms.screen_market) always uses MAX(Date) from
        # daily_data2_full. So we require override_date == latest data_date.
        latest_date, _ = get_verified_data_date()
        if latest_date is None:
            print("[runner] ERROR: no data in daily_data2_full. exit 1.")
            return 1
        if override_date != latest_date:
            print(f"[runner] ERROR: --data-date={override_date} != latest data_date={latest_date}.")
            print(f"[runner] ms.screen_market() always uses MAX(Date) from daily_data2_full, so override must match.")
            print(f"[runner] This prevents creating a run labeled {override_date} from a {latest_date} snapshot.")
            return 1
        data_date = override_date
        n_tickers = None
    else:
        data_date, n_tickers = get_verified_data_date()
        if data_date is None:
            print("[runner] ERROR: no data in daily_data2_full. exit 1.")
            return 1
        # F1: n_tickers now means latest-day count, not all-history
        if n_tickers < MIN_TICKERS_FOR_RUN:
            print(f"[runner] ERROR: data_date {data_date} has only {n_tickers} tickers on latest day. exit 1.")
            return 1
        if not args.force:
            expected_date = expected_data_date(today)
            if data_date != expected_date:
                print(f"[runner] ERROR: data_date {data_date} != expected session {expected_date} (today={today}). exit 1.")
                return 1

    print(f"[runner] data_date={data_date} today={today} force={args.force}")

    # D052h-fixup2 F4: verify metadata-backfill ran successfully for the
    # same target data_date. Without this, market-screen may run on a
    # date where new tickers are missing from industry_type (causing
    # them to be filtered out of the universe). The marker is written
    # by metadata_backfill_daily.ps1 ONLY after a successful run.
    if not args.force and not has_metadata_marker(data_date):
        marker = METADATA_MARKER_DIR / f"metadata_target_{data_date.isoformat()}_OK.marker"
        print(f"[runner] ERROR: metadata-backfill success marker missing for {data_date}.")
        print(f"[runner] expected: {marker}")
        print(f"[runner] this means new tickers may not have industry_type rows yet.")
        print(f"[runner] refusing to run with stale metadata state. exit 1.")
        return 1

    # F7: if existing complete run, exit 0 (idempotent)
    run_id, complete, missing = has_complete_run_for_data_date(data_date)
    if run_id is not None and complete and not args.force and not args.refresh_existing:
        print(f"[runner] market_screen_runs already has complete run for {data_date} (run_id={run_id}). skip (idempotent).")
        return 0
    if run_id is not None and not complete and not args.force and not args.refresh_existing:
        # F7: existing run but missing artifacts -> repair-only
        if all(m in ["md", "html", "dd"] for m in missing):
            print(f"[runner] existing run for {data_date} (run_id={run_id}) has missing artifacts: {missing}")
            print("[runner] running repair-only mode")
            ok, errs = repair_only_artifacts(data_date, run_id)
            if ok:
                print("[runner] repair OK")
                return 0
            else:
                print(f"[runner] repair FAILED: {errs}")
                return 1
        else:
            # Critical metadata missing
            print(f"[runner] existing run for {data_date} has critical missing: {missing}")
            print("[runner] will re-run full screen")
            # fall through to full re-run

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

    # === Generate artifacts ===
    print("[runner] generating artifacts...")
    paths, errors = generate_artifacts(data_date, result)
    for p, ok in paths:
        print(f"[runner]   {'OK' if ok else 'FAIL'}: {p}")
    if errors:
        print(f"[runner] WARN: artifact errors: {errors}")
        return 1

    # === Post-state verify ===
    conn = db.connect(**DB)
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
            print(f"[runner] ERROR: post-state fail: total={n_total} active={n_active}")
            return 1
    finally:
        conn.close()

    print(f"[runner] OK data_date={data_date} run_id={run_id}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
