#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
postflight_daily.py — D052h-fixup
Run at 00:05 daily. Verifies all 8 tw-invest-suite-* tasks ran on the
previous operational date and data integrity holds.

D052h-fixup changes:
  - Use Get-ScheduledTaskInfo (PowerShell) + JSON parsing instead of
    locale-dependent schtasks /Query string parsing.
  - Check previous operational date (not today) since 00:05 may run on
    Sun/Mon and "today" is not yet operational.
  - 267011 (task killed) is NOT considered success.
  - Active picks must be EXACTLY 24 (not >= 24).
  - Add publish artifact/date verification.

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

LOG_DIR = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug")
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
    """Returns the most recent date that should have data. If today is
    Sun/Mon, returns last Friday. Else returns yesterday.
    """
    today = date.today()
    wd = today.weekday()  # 0=Mon, 6=Sun
    if wd == 6:  # Sun
        return today - timedelta(days=2)  # Fri
    if wd == 0:  # Mon
        return today - timedelta(days=3)  # Fri (data from Fri, weekend gap)
    if wd == 5:  # Sat
        return today - timedelta(days=1)  # Fri
    # Tue-Fri: yesterday
    return today - timedelta(days=1)


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


def check_publish_artifact(operational_date):
    """Verify publish cron ran on operational_date and produced artifact.
    We check the publish_ghpages_daily.ps1 log file in _debug/ dir.
    """
    # Find publish log for operational_date
    expected = LOG_DIR / f"publish_full_{operational_date.strftime('%Y%m%d')}.log"
    if not expected.exists():
        # Try the recent one
        candidates = sorted(LOG_DIR.glob("publish_*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            return {"pass": False, "reason": "no publish log found"}
        latest = candidates[0]
        # Check if latest log is from today or operational_date
        mtime = datetime.fromtimestamp(latest.stat().st_mtime).date()
        if mtime != operational_date:
            return {"pass": False, "reason": f"latest publish log is {mtime}, expected {operational_date}"}
        log_path = latest
    else:
        log_path = expected

    # Check log content for "Done" / "pushed" / success marker
    try:
        content = log_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as e:
        return {"pass": False, "reason": f"cannot read log: {e}"}

    # Look for success markers
    has_pushed = bool(re.search(r"pushed|done|Done|✓|✔|OK", content, re.IGNORECASE))
    has_error = bool(re.search(r"error|exception|traceback|failed", content, re.IGNORECASE))
    return {
        "pass": has_pushed and not has_error,
        "log": str(log_path),
        "has_pushed": has_pushed,
        "has_error": has_error,
    }


def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    op_date = previous_operational_date()
    print(f"[postflight] checking operational_date = {op_date}")

    checks = {}
    overall_pass = True

    per_check = [
        ("market_screen", lambda: check_market_screen(op_date)),
        ("company_null", lambda: check_company_null(op_date)),
        ("industry_count", check_industry_count),
        ("quarantine", check_quarantine),
        ("publish_artifact", lambda: check_publish_artifact(op_date)),
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
        checks["tasks"] = check_tasks(op_date)
        if not checks["tasks"].get("all_pass", False):
            overall_pass = False
    except Exception as e:
        checks["tasks"] = {"all_pass": False, "error": str(e)}
        overall_pass = False

    summary = {
        "operational_date": op_date.isoformat(),
        "ts": datetime.now().isoformat(),
        "overall_pass": overall_pass,
        "checks": checks,
    }
    log_file = LOG_DIR / f"postflight_{date.today().isoformat()}.json"
    log_file.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
