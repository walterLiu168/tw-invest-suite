#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
postflight_daily.py — D052h-fixup2 + D056-A
Run at 00:05 daily. Verifies all 8 tw-invest-suite-* tasks ran on the
previous calendar day and data integrity holds.

D052h-fixup2 changes (per ChatGPT visible UI F3 + F4):
  - F3: PUBLISH log path uses repo scripts/_debug (not runtime _debug).
    Pattern is publish_ghpages_YYYYMMDD_HHMMSS.log (not publish_full_*.log).
    Also check for "done (exit 0)" success marker.
  - F4: Separate execution_date (previous calendar day for Scheduler
    task check) from data_date (latest trading data in DB for picks/
    company_null check).

D052h-fixup changes (kept):
  - Use Get-ScheduledTaskInfo (PowerShell) + JSON parsing instead of
    locale-dependent schtasks /Query string parsing.
  - 267011 (task killed) is NOT considered success.
  - Active picks must be EXACTLY 24 (not >= 24).

Pending (NOT addressed in fixup2):
  - H: existing-ticker reconciliation
  - J: 7768 per-day quarantine accumulation
  - T2/T3: live test infrastructure (mocked tests in tests/ post-fixup2)
  - T4: live stale-OHLCV test (deterministic unit test in tests/)

D056-A changes (Option A simplification):
  - At tail of main(), invoke build_dashboard.py via subprocess (best-effort,
    separate process). One-page morning dashboard for Walter's 1-minute read.
  - Don't fail postflight on dashboard failure (canonical invariant lives in
    the existing checks; dashboard is reporting only).

Exits 0 on all OK, 1 on any failure. Writes JSON status to log file.
"""
import json
import os
import re
import subprocess
import sys
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

import pymysql

DB = dict(host="localhost", user="root", password="1234", database="tw_elec",
          connect_timeout=10, charset="utf8mb4")

# D052h-fixup2 F3: actual publish log is written by publish_ghpages_daily.ps1
# to C:\Users\icemo\Projects\tw-invest-suite\scripts\_debug (it does
# Set-Location to repo scripts first). Pattern is publish_ghpages_YYYYMMDD_HHMMSS.log.
PUBLISH_LOG_DIR = Path(r"C:\Users\icemo\Projects\tw-invest-suite\scripts\_debug")
PUBLISH_LOG_PATTERN = "publish_ghpages_*.log"

LOG_DIR = Path(r"C:\Users\icemo\Projects\tw-invest-suite\scripts\_debug")
TASKS = [
    "tw-invest-suite-daily-report",
    "tw-invest-suite-yfinance",
    "tw-invest-suite-health-check",
    "tw-invest-suite-sync-legacy",
    "tw-invest-suite-publish",
    "tw-invest-suite-company-refresh",
    "tw-invest-suite-metadata-backfill",
    "tw-invest-suite-market-screen",
]

# Tasks that are exempt on weekends (e.g. market_screen, metadata-backfill)
WEEKEND_EXEMPT = {
    "tw-invest-suite-market-screen",
    "tw-invest-suite-metadata-backfill",
}


def get_tasks_info():
    """Returns list of dicts: task_name, last_run_time (str or None),
    last_task_result (int or None). Uses Get-ScheduledTaskInfo + JSON.
    """
    # PowerShell: list all our tasks and dump as JSON
    ps = r"""
$tasks = @(
  'tw-invest-suite-daily-report',
  'tw-invest-suite-yfinance',
  'tw-invest-suite-health-check',
  'tw-invest-suite-sync-legacy',
  'tw-invest-suite-publish',
  'tw-invest-suite-company-refresh',
  'tw-invest-suite-metadata-backfill',
  'tw-invest-suite-market-screen'
)
$out = @()
foreach ($t in $tasks) {
  $info = Get-ScheduledTaskInfo -TaskName $t -ErrorAction SilentlyContinue
  if ($info) {
    $out += [PSCustomObject]@{
      task = $t
      last_run_time = if ($info.LastRunTime) { $info.LastRunTime.ToString('o') } else { $null }
      last_task_result = [int]$info.LastTaskResult
    }
  } else {
    $out += [PSCustomObject]@{
      task = $t
      last_run_time = $null
      last_task_result = $null
    }
  }
}
$out | ConvertTo-Json -Compress
"""
    r = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", ps],
        capture_output=True, text=True, encoding='utf-8'
    )
    if r.returncode != 0 or not r.stdout.strip():
        return None
    try:
        data = json.loads(r.stdout)
    except json.JSONDecodeError as e:
        print(f"ERROR: failed to parse PowerShell JSON: {e}\nRaw: {r.stdout[:500]}")
        return None
    if isinstance(data, dict):
        return [data]
    return data or []


def previous_operational_date():
    """D052h-fixup2 F4: execution_date — the previous calendar day for
    which the Scheduler tasks should have completed.

    For a 00:05 postflight run, this is simply today - 1 day. (On TWSE
    holidays where no tasks ran, the failure will be detected by the
    task-run-time check itself; we don't try to skip holidays here.)

    Returns: date
    """
    return date.today() - timedelta(days=1)


def latest_trading_data_date():
    """D052h-fixup2 F4: data_date — the most recent date that has actual
    OHLCV data in daily_data2_full. This is the date the DB checks
    (market_screen, company_null) should target.

    Returns: date or None if DB is empty
    """
    conn = pymysql.connect(**DB)
    try:
        cur = conn.cursor()
        cur.execute("SELECT MAX(Date) FROM daily_data2_full")
        row = cur.fetchone()
        if row and row[0]:
            return row[0]
        return None
    finally:
        conn.close()


def check_tasks(operational_date):
    """Returns {all_pass: bool, details: [...]}."""
    tasks_info = get_tasks_info()
    if tasks_info is None:
        return {"all_pass": False, "error": "failed to get task info from PowerShell"}

    target_date = operational_date.isoformat()
    details = []
    all_pass = True
    for ti in tasks_info:
        task = ti.get("task")
        lrt = ti.get("last_run_time")  # ISO 8601 string or None
        ltr = ti.get("last_task_result")  # int or None

        ran_on_target = False
        if lrt:
            # Parse ISO 8601; just check if YYYY-MM-DD matches
            try:
                ran_on_target = lrt.startswith(target_date)
            except Exception:
                ran_on_target = False

        # D052h-fixup: 267011 is NOT success. Only 0 (success) is success.
        # Other values: 1 (error), 2 (warning), etc.
        success_result = (ltr == 0)
        is_weekend_exempt = task in WEEKEND_EXEMPT and operational_date.weekday() >= 5

        # On weekends, market-screen and metadata-backfill are expected to
        # be "Ready but not run today" — that's not a failure.
        # But on operational_date (which is the previous trading day),
        # they should have run. Only today (Sun/Sat) is exempt.
        is_ok = (ran_on_target and success_result) or (
            is_weekend_exempt and not ran_on_target  # never ran, that's ok on weekend
        )

        details.append({
            "task": task,
            "last_run_time": lrt,
            "last_task_result": ltr,
            "ran_on_target_date": ran_on_target,
            "success_result": success_result,
            "weekend_exempt": is_weekend_exempt,
            "pass": is_ok,
        })
        if not is_ok:
            all_pass = False

    return {"all_pass": all_pass, "target_date": target_date, "details": details}


def check_market_screen(operational_date):
    """Exact 24 active picks for operational_date's data."""
    conn = pymysql.connect(**DB)
    try:
        cur = conn.cursor()
        # Find the run for operational_date
        cur.execute(
            "SELECT id, picks_count FROM market_screen_runs WHERE run_date = %s",
            (operational_date,)
        )
        row = cur.fetchone()
        if not row:
            return {"pass": False, "reason": f"no market_screen_runs for {operational_date}"}
        run_id, picks_count = row
        cur.execute(
            "SELECT COUNT(*), SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) "
            "FROM market_screen_picks WHERE run_id = %s",
            (run_id,)
        )
        n_total, n_active = cur.fetchone()
        n_total = n_total or 0
        n_active = n_active or 0
        return {
            "pass": picks_count == 24 and n_total == 24 and n_active == 24,
            "run_id": run_id,
            "picks_count": picks_count,
            "picks_total": n_total,
            "picks_active": n_active,
        }
    finally:
        conn.close()


def check_company_null(operational_date):
    conn = pymysql.connect(**DB)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*), SUM(CASE WHEN company IS NULL OR TRIM(company)='' THEN 1 ELSE 0 END) "
            "FROM daily_data2_full WHERE Date = %s",
            (operational_date,)
        )
        total, null_cnt = cur.fetchone()
        total = total or 0
        null_cnt = null_cnt or 0
        return {
            "pass": total >= 1900 and null_cnt <= 5,
            "total": total,
            "null": null_cnt,
        }
    finally:
        conn.close()


def check_industry_count():
    conn = pymysql.connect(**DB)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM industry_type")
        n = cur.fetchone()[0]
        return {"pass": n >= 1962, "count": n}
    finally:
        conn.close()


def check_quarantine():
    conn = pymysql.connect(**DB)
    try:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM metadata_quarantine WHERE resolved_at IS NULL")
        n = cur.fetchone()[0]
        # <= 10 OK; > 10 is a leak
        return {"pass": n <= 10, "open_count": n}
    finally:
        conn.close()


def check_publish_artifact(execution_date):
    """D052h-fixup2 F3: verify publish cron produced a log for execution_date
    with explicit success marker.

    publish_ghpages_daily.ps1 writes to:
      C:\\Users\\icemo\\Projects\\tw-invest-suite\\scripts\\_debug
    Pattern: publish_ghpages_YYYYMMDD_HHMMSS.log
    Success marker in the log: "done (exit 0)" (last line)
    """
    if not PUBLISH_LOG_DIR.exists():
        return {"pass": False, "reason": f"publish log dir missing: {PUBLISH_LOG_DIR}"}
    # Match log files whose timestamp is on execution_date (YYYYMMDD prefix)
    # The filename embeds local time, so the prefix is the publish date
    prefix = f"publish_ghpages_{execution_date.strftime('%Y%m%d')}_"
    candidates = sorted(
        PUBLISH_LOG_DIR.glob(PUBLISH_LOG_PATTERN),
        key=lambda p: p.stat().st_mtime, reverse=True,
    )
    matches = [p for p in candidates if p.name.startswith(prefix)]
    if not matches:
        # Allow any publish log from execution_date's window as fallback,
        # but require it to be from execution_date (mtime check)
        recent = [p for p in candidates
                  if datetime.fromtimestamp(p.stat().st_mtime).date() == execution_date]
        if not recent:
            return {"pass": False, "reason": f"no publish_ghpages log for {execution_date}"}
        log_path = recent[0]
    else:
        log_path = matches[0]

    # Check log content for explicit success marker "done (exit 0)"
    try:
        content = log_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return {"pass": False, "reason": f"cannot read log: {e}"}

    has_done_marker = bool(re.search(r"done\s*\(exit\s*0\)", content, re.IGNORECASE))
    has_pushed = bool(re.search(r"pushed|Done|✓|✔", content, re.IGNORECASE))
    has_error = bool(re.search(r"error|exception|traceback|failed", content, re.IGNORECASE))
    return {
        "pass": has_done_marker and not has_error,
        "log": str(log_path),
        "has_done_marker": has_done_marker,
        "has_pushed": has_pushed,
        "has_error": has_error,
    }


def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # D052h-fixup2 F4: separate execution_date (Scheduler) from
    # data_date (DB / latest OHLCV).
    exec_date = previous_operational_date()
    data_date = latest_trading_data_date()
    print(f"[postflight] execution_date = {exec_date}  data_date = {data_date}")

    checks = {}
    overall_pass = True

    per_check = [
        ("market_screen", lambda: check_market_screen(data_date)),
        ("company_null", lambda: check_company_null(data_date)),
        ("industry_count", check_industry_count),
        ("quarantine", check_quarantine),
        ("publish_artifact", lambda: check_publish_artifact(exec_date)),
    ]
    for name, fn in per_check:
        try:
            result = fn()
        except Exception as e:
            result = {"pass": False, "error": str(e)}
        checks[name] = result
        if not result.get("pass", False):
            overall_pass = False

    try:
        checks["tasks"] = check_tasks(exec_date)
        if not checks["tasks"].get("all_pass", False):
            overall_pass = False
    except Exception as e:
        checks["tasks"] = {"all_pass": False, "error": str(e)}
        overall_pass = False

    summary = {
        "execution_date": exec_date.isoformat(),
        "data_date": data_date.isoformat() if data_date else None,
        "ts": datetime.now().isoformat(),
        "overall_pass": overall_pass,
        "checks": checks,
    }
    log_file = LOG_DIR / f"postflight_{date.today().isoformat()}.json"
    log_file.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))

    # D054: write daily_summary_YYYY-MM-DD.md (manifest + remote verify)
    try:
        from daily_summary import write_summary
        md_path = write_summary(summary)
        if md_path:
            print(f"[postflight] daily_summary written: {md_path}")
    except Exception as e:
        # Don't fail postflight on summary write errors
        print(f"[postflight] WARN: daily_summary write failed: {e}")

    # D056-A: build_dashboard.py — one-page morning dashboard (1-minute read)
    # Subprocess call (not import): lives in runtime scripts/_debug, separate
    # process boundary keeps dashboard failures from corrupting postflight state.
    DASHBOARD_RUNNER = (
        r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug\build_dashboard.py"
    )
    try:
        r = subprocess.run(
            ["python", DASHBOARD_RUNNER],
            capture_output=True, text=True, encoding="utf-8", timeout=60,
        )
        print(f"[postflight] build_dashboard.py exit={r.returncode}")
        if r.stdout:
            for line in r.stdout.splitlines()[-15:]:
                print(f"  [dashboard] {line}")
        if r.stderr:
            print(f"[postflight] dashboard stderr: {r.stderr[:500]}")
        # Don't fail postflight on dashboard failure (best-effort)
    except subprocess.TimeoutExpired:
        print("[postflight] WARN: build_dashboard.py timeout (>60s)")
    except Exception as e:
        print(f"[postflight] WARN: build_dashboard.py failed: {e}")

    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
