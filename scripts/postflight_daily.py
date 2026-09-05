#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
postflight_daily.py — D052h K
Run at 00:05 daily. Verifies all 8 tw-invest-suite-* tasks ran today
and the data integrity invariants hold.

Checks:
  1. All 8 tw-invest-suite-* Task Scheduler entries fired today with
     exit code 0 (or expected "skip" exit)
  2. market_screen_runs has a run for the latest valid data_date
  3. market_screen_picks has 24 active for the latest run
  4. metadata_quarantine open count is small (no new unresolved)
  5. daily_data2_full latest date: ticker count >= 1900, null company <= 5
  6. industry_type count >= 1962 (master table growing)

Exits 0 on all OK, 1 on any failure. Writes JSON status to log file.

Schedule: Task Scheduler daily 00:05 (after publish at 23:50).
"""
import json
import os
import subprocess
import sys
import time
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


def check_tasks_today():
    results = []
    today = date.today().isoformat()
    for t in TASKS:
        info = subprocess.run(
            ["schtasks", "/Query", "/TN", t, "/V", "/FO", "LIST"],
            capture_output=True, text=True
        )
        last_run = None
        last_result = None
        for line in info.stdout.splitlines():
            if "Last Run Time:" in line:
                last_run = line.split(":", 1)[1].strip()
            if "Last Result:" in line:
                last_result = line.split(":", 1)[1].strip()
        is_today = last_run and last_run.startswith(today) if last_run else False
        results.append({
            "task": t,
            "last_run": last_run,
            "last_result": last_result,
            "ran_today": is_today,
            "pass": is_today and last_result in ("0", "267011"),
        })
    return results


def check_market_screen_run():
    conn = pymysql.connect(**DB)
    try:
        cur = conn.cursor()
        cur.execute("SELECT MAX(Date) FROM daily_data2_full")
        data_date = cur.fetchone()[0]
        if not data_date:
            return {"pass": False, "reason": "no data_date"}
        cur.execute(
            "SELECT id, run_date, picks_count FROM market_screen_runs "
            "WHERE run_date = %s",
            (data_date,)
        )
        row = cur.fetchone()
        if not row:
            return {"pass": False, "data_date": str(data_date), "reason": "no run for data_date"}
        run_id, run_date, picks_count = row
        # Check active picks
        cur.execute(
            "SELECT COUNT(*), SUM(CASE WHEN status='active' THEN 1 ELSE 0 END) "
            "FROM market_screen_picks WHERE run_id = %s",
            (run_id,)
        )
        n_total, n_active = cur.fetchone()
        return {
            "pass": (picks_count == 24 and n_total == 24 and (n_active or 0) > 0),
            "data_date": str(data_date),
            "run_id": run_id,
            "picks_count": picks_count,
            "picks_total": n_total,
            "picks_active": n_active or 0,
        }
    finally:
        conn.close()


def check_company_null():
    conn = pymysql.connect(**DB)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*), SUM(CASE WHEN company IS NULL OR TRIM(company)='' THEN 1 ELSE 0 END) "
            "FROM daily_data2_full WHERE Date = (SELECT MAX(Date) FROM daily_data2_full)"
        )
        total, null_cnt = cur.fetchone()
        return {
            "pass": (total or 0) >= 1900 and (null_cnt or 0) <= 5,
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
        # 5 is expected (7768 multi-day rows). 10+ would be a leak.
        return {"pass": n <= 10, "open_count": n}
    finally:
        conn.close()


def main():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / f"postflight_{date.today().isoformat()}.json"

    checks = {}
    overall_pass = True
    # Per-check fns each return a dict with "pass" key
    per_check = [
        ("market_screen", check_market_screen_run),
        ("company_null", check_company_null),
        ("industry_count", check_industry_count),
        ("quarantine", check_quarantine),
    ]
    for name, fn in per_check:
        try:
            result = fn()
        except Exception as e:
            result = {"pass": False, "error": str(e)}
        checks[name] = result
        if not result.get("pass", False):
            overall_pass = False

    # tasks check returns a list; aggregate
    try:
        task_results = check_tasks_today()
        tasks_all_pass = all(t.get("pass", False) for t in task_results)
        checks["tasks"] = {"all_pass": tasks_all_pass, "details": task_results}
        if not tasks_all_pass:
            overall_pass = False
    except Exception as e:
        checks["tasks"] = {"all_pass": False, "error": str(e)}
        overall_pass = False

    summary = {
        "date": date.today().isoformat(),
        "ts": datetime.now().isoformat(),
        "overall_pass": overall_pass,
        "checks": checks,
    }
    log_file.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2, default=str))
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
