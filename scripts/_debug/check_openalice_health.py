"""OpenAlice + tw-invest-suite schedule health check.

Verifies every scheduled task:
  1. LastRunTime today (or for weekly/monthly tasks: within expected window)
  2. LastTaskResult == 0 (success) or skipped intentionally
  3. Cross-checks DB: did the data actually land?
     - daily_data2_full latest date
     - ai_5min_kbars latest date
     - stock_news latest published_at
     - digest_source_raw latest trade_date
     - 6 missing-data domain tables latest dates
     - finmind_taiwan_margin_maintenance latest trade_date
     - C:\\Groove-Lab\\analyze\\*.html modified today (render)
     - C:\\Groove-Lab\\watchlist.html modified today
     - C:\\Groove-Lab\\analyze\\patterns.html modified today

Output: human-readable table + JSON status. Exit 0 if all OK, 1 if any failure.

Usage:
  python _debug/check_openalice_health.py            # check today (Asia/Taipei)
  python _debug/check_openalice_health.py --date 2026-08-15  # check specific date
  python _debug/check_openalice_health.py --json     # JSON output only
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pymysql

TZ = ZoneInfo("Asia/Taipei")
DB = dict(host="localhost", user="root", password="1234", database="tw_elec", connect_timeout=5)

TASKS = [
    # OpenAlice aux (12)
    ("OpenAlice Weekly Shareholding 1330",  "weekday",  "13:30"),
    ("OpenAlice ExDividend 1335",           "weekday",  "13:35"),
    ("OpenAlice Intraday 5m 1555",          "weekday",  "15:55"),
    ("OpenAlice Intraday 5m Retry 1620",    "weekday",  "16:20"),
    ("OpenAlice Daily OHLCV 1735",          "weekday",  "17:35"),
    ("OpenAlice Daily OHLCV Retry 1755",    "weekday",  "17:55"),
    ("OpenAlice Missing Data Center 1830",  "weekday",  "18:30"),
    ("OpenAlice Daily Institutional 2015",  "weekday",  "20:15"),
    ("OpenAlice Daily Margin Short 2115",   "weekday",  "21:15"),
    ("OpenAlice Daily DayTrade 2145",       "weekday",  "21:45"),
    ("OpenAlice News Refresh Every 2h",     "every2h",  None),
    ("OpenAlice RSS Refresh Every 2h",      "every2h",  None),
    # tw-invest-suite 22:25
    ("tw-invest-suite-daily-report",        "weekday",  "22:25"),
]

# Trigger time lists for every2h tasks (must match install_openalice_aux_schedule.ps1)
AT_LISTS = {
    "OpenAlice News Refresh Every 2h": ["02:00","04:00","06:00","08:00","10:00","12:00","14:00","16:00","18:00","20:00","22:00"],
    "OpenAlice RSS Refresh Every 2h":  ["03:00","05:00","07:00","09:00","11:00","13:00","15:00","17:00","19:00","21:00","23:00"],
}


def get_task_info(name: str) -> dict:
    """Query Windows Task Scheduler for last run + result."""
    try:
        out = subprocess.check_output(
            ["schtasks", "/Query", "/TN", name, "/FO", "LIST", "/V"],
            text=True, encoding="utf-8", errors="replace", timeout=10,
        )
    except subprocess.CalledProcessError as e:
        return {"name": name, "state": "MISSING", "last_run": None, "result": None, "raw": str(e)}
    info = {"name": name, "state": "?", "last_run": None, "result": None}
    for line in out.splitlines():
        line = line.strip()
        if line.startswith("Status:"):
            info["state"] = line.split(":", 1)[1].strip()
        elif line.startswith("Last Run Time:"):
            info["last_run"] = line.split(":", 1)[1].strip()
        elif line.startswith("Last Task Result:"):
            try:
                info["result"] = int(line.split(":", 1)[1].strip())
            except ValueError:
                info["result"] = line.split(":", 1)[1].strip()
    return info


def parse_task_last_run(s: str | None) -> datetime | None:
    """Parse Windows schtasks Last Run Time, supporting Chinese locale (上午/下午).

    Handles:
      "2026/8/18 下午 01:30:00"  → 2026-08-18 13:30:00
      "2026/8/18 上午 09:00:00"  → 2026-08-18 09:00:00
      "2026-08-18 13:30:00"     → 2026-08-18 13:30:00
      "1999/11/30 上午 12:00:00" → never-run sentinel
    """
    if not s or s.strip() in ("", "Never"):
        return None
    s = s.strip()
    # detect never-run sentinel: 1999/11/30
    if s.startswith("1999/"):
        return None
    # detect AM/PM
    is_pm = "下午" in s or " PM " in s.upper()
    is_am = "上午" in s or " AM " in s.upper()
    s = s.replace("上午", "").replace("下午", "").replace("AM", "").replace("PM", "").strip()
    s = " ".join(s.split())  # collapse extra spaces
    # s is now like "2026/8/18 01:30:00" or "2026/8/18 13:30:00"
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            # if original said 下午 (PM) and hour < 12, add 12
            if is_pm and dt.hour < 12:
                dt = dt.replace(hour=dt.hour + 12)
            return dt.replace(tzinfo=TZ)
        except ValueError:
            continue
    return None


def task_scheduled_time_passed(at_str: str | None, check_date: date, now: datetime) -> bool:
    """For a weekday task at HH:MM, did its scheduled time pass on check_date?"""
    if not at_str:
        return True
    try:
        hh, mm = at_str.split(":")
        scheduled = datetime.combine(check_date, datetime.min.time(), tzinfo=TZ).replace(
            hour=int(hh), minute=int(mm)
        )
        return now >= scheduled
    except Exception:
        return True


def every2h_past_triggers(at_list: list[str], check_date: date, now: datetime) -> list[str]:
    """Return list of HH:MM trigger times that have passed today (for every2h tasks)."""
    out = []
    for at in at_list or []:
        try:
            hh, mm = at.split(":")
            scheduled = datetime.combine(check_date, datetime.min.time(), tzinfo=TZ).replace(
                hour=int(hh), minute=int(mm)
            )
            if now >= scheduled:
                out.append(at)
        except Exception:
            continue
    return out


def get_conn():
    return pymysql.connect(**DB)


def db_max_date(table: str, col: str = "Date") -> str | None:
    try:
        with get_conn() as c:
            cur = c.cursor()
            cur.execute(f"SELECT MAX({col}) FROM {table}")
            row = cur.fetchone()
            return str(row[0]) if row and row[0] else None
    except Exception as e:
        return f"ERR: {e}"


def db_max_date_hours_behind(table: str, col: str) -> int | None:
    """For datetime columns, return hours behind now (None if null/error)."""
    try:
        with get_conn() as c:
            cur = c.cursor()
            cur.execute(f"SELECT MAX({col}) FROM {table}")
            row = cur.fetchone()
            if not row or not row[0]:
                return None
            latest = row[0]
            now = datetime.now(TZ)
            if isinstance(latest, datetime):
                delta = now - latest
                # If the latest is naive, treat as UTC? we keep tz-naive comparison
                if latest.tzinfo is None:
                    return int(delta.total_seconds() // 3600)
                return int((now - latest).total_seconds() // 3600)
            # date column
            delta_days = (now.date() - latest).days if hasattr(latest, 'isoformat') else None
            return delta_days * 24 if delta_days is not None else None
    except Exception:
        return None


def db_count_since(table: str, since: date) -> int | None:
    try:
        with get_conn() as c:
            cur = c.cursor()
            cur.execute(f"SELECT COUNT(*) FROM {table} WHERE Date >= %s", (since,))
            row = cur.fetchone()
            return int(row[0]) if row else 0
    except Exception as e:
        return None


def file_modified_today(path: Path) -> bool:
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=TZ)
    return mtime.date() == date.today()


def file_mtime_str(path: Path) -> str:
    if not path.exists():
        return "MISSING"
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=TZ)
    return mtime.strftime("%Y-%m-%d %H:%M:%S")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=None, help="Check date (YYYY-MM-DD); default today Asia/Taipei")
    p.add_argument("--json", action="store_true", help="JSON output only")
    args = p.parse_args()

    check_date = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else datetime.now(TZ).date()
    today = date.today()
    is_today = (check_date == today)
    is_weekday = check_date.weekday() < 5
    is_weekend = not is_weekday
    now_tz = datetime.now(TZ)

    rows = []
    failures = []

    # 1) Task Scheduler state per task
    for name, kind, at in TASKS:
        info = get_task_info(name)
        last_run_str = info.get("last_run")
        last_run_dt = parse_task_last_run(last_run_str)
        last_run_date = last_run_dt.date() if last_run_dt else None
        ran_today = (last_run_date == check_date) if last_run_date else False

        # expected to run today
        expected_today = is_today
        if kind == "weekday" and is_weekend:
            expected_today = False
        if kind == "every2h" and is_weekend:
            expected_today = True

        # For weekday task at HH:MM: if current time hasn't reached it, don't flag
        scheduled_passed = True
        if is_today and expected_today:
            if kind == "weekday" and at:
                scheduled_passed = task_scheduled_time_passed(at, check_date, now_tz)
            elif kind == "every2h":
                # for every2h, the task "should have run today" if any past trigger passed
                past = every2h_past_triggers(AT_LISTS.get(name), check_date, now_tz)
                scheduled_passed = len(past) > 0
            else:
                scheduled_passed = True

        status = "OK"
        if info["state"] not in ("Ready", "Running"):
            status = f"NOT READY ({info['state']})"
        elif expected_today and scheduled_passed and not ran_today:
            status = "DID NOT RUN TODAY"
        elif expected_today and ran_today and info["result"] not in (0, "0", 267011, None):
            status = f"FAILED (code={info['result']})"
        elif not expected_today and ran_today:
            status = "RAN (not expected on weekend)"

        if status not in ("OK", "RAN (not expected on weekend)"):
            failures.append((name, status, last_run_str, info["result"]))
        rows.append({
            "check": "scheduler",
            "task": name,
            "kind": kind,
            "at": at,
            "state": info["state"],
            "last_run": last_run_str,
            "ran_today": ran_today,
            "scheduled_passed": scheduled_passed if is_today else None,
            "result": info["result"],
            "status": status,
        })

    # 2) DB landing date cross-check (snapshot, regardless of which task)
    db_checks = [
        ("daily_data2_full",   "Date",  "OHLCV/price/chips/weekly/exdiv/inst/margin/daytrade — should land by ~21:45"),
        ("ai_5min_kbars",      "Date",  "5m — should land by 15:55 + retry 16:20"),
        ("stock_news",         "published_at", "News — every 2h"),
        ("digest_source_raw",  "created_at",  "RSS — every 2h (using created_at, not trade_date which is nullable)"),
        ("finmind_taiwan_margin_maintenance", "trade_date", "Margin maintenance — D020, daily 22:25"),
    ]
    domain_tables = [
        ("finmind_option_daily",                "trade_date", "Missing data: options"),
        ("finmind_warrant_summary",             "published_date", "Missing data: warrants"),
        ("finmind_etf_active_holding",          "trade_date", "Missing data: ETF holdings"),
        ("finmind_etf_premium_discount",        "trade_date", "Missing data: ETF premium"),
        ("finmind_taiwan_total_institutional_daily", "trade_date", "Missing data: macro inst"),
        ("finmind_taiwan_total_margin_daily",   "trade_date",       "Missing data: macro margin"),
        ("finmind_month_revenue",               "published_date",   "Missing data: month revenue"),
    ]
    for table, col, desc in db_checks + domain_tables:
        latest = db_max_date(table, col)
        latest_date = None
        if latest and not latest.startswith("ERR"):
            try:
                latest_date = datetime.strptime(str(latest).split()[0], "%Y-%m-%d").date()
            except ValueError:
                pass
        landed_today = (latest_date == check_date) if latest_date else False
        days_behind = (check_date - latest_date).days if latest_date else None

        # Special: for digest_source_raw + stock_news, use hours-behind on the datetime column
        is_datetime_col = (table in ("digest_source_raw", "stock_news"))
        hours_behind = None
        if is_datetime_col:
            hours_behind = db_max_date_hours_behind(table, col)

        status = "OK"
        if latest_date is None and hours_behind is None:
            status = "NO DATA"
        elif is_datetime_col and hours_behind is not None and hours_behind > 6 and is_weekday:
            status = f"BEHIND {hours_behind}h"
        elif days_behind is not None and days_behind > 1 and is_weekday:
            status = f"BEHIND {days_behind}d"
        elif days_behind is not None and days_behind > 5:
            status = f"STALE {days_behind}d"
        if status not in ("OK",):
            failures.append((table, status, str(latest), None))
        rows.append({
            "check": "db_landing",
            "task": table,
            "col": col,
            "desc": desc,
            "latest": str(latest) if latest else None,
            "days_behind": days_behind,
            "hours_behind": hours_behind,
            "landed_today": landed_today,
            "status": status,
        })

    # 3) Render output files (tw-invest-suite 22:25)
    html_dir = Path("C:/Groove-Lab/analyze")
    files_to_check = [
        (html_dir / "watchlist.html",  "watchlist.html (Stage 6)"),
        (html_dir / "patterns.html",   "patterns.html (Stage 4)"),
    ]
    for path, desc in files_to_check:
        ok = file_modified_today(path)
        status = "OK" if ok else "NOT UPDATED TODAY"
        if status != "OK":
            failures.append((str(path), status, file_mtime_str(path), None))
        rows.append({
            "check": "render_output",
            "task": desc,
            "path": str(path),
            "mtime": file_mtime_str(path),
            "status": status,
        })
    # analyze/*.html count
    try:
        n_html = sum(1 for _ in html_dir.glob("*.html"))
    except Exception:
        n_html = -1
    rows.append({
        "check": "render_count",
        "task": f"analyze/*.html count in {html_dir}",
        "count": n_html,
        "status": "OK" if n_html >= 1900 else "LOW",
    })
    if n_html < 1900:
        failures.append(("analyze_count", f"only {n_html} files", None, None))

    # === Output ===
    if args.json:
        out = {
            "check_date": check_date.isoformat(),
            "is_today": is_today,
            "is_weekday": is_weekday,
            "rows": rows,
            "failures": [{"name": n, "status": s, "last_run": lr, "result": r} for (n, s, lr, r) in failures],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"=== OpenAlice + tw-invest-suite health check  date={check_date}  weekday={is_weekday} ===")
        print()
        # Group by check type
        from itertools import groupby
        for check_type, group in groupby(rows, key=lambda r: r["check"]):
            print(f"[{check_type}]")
            for r in group:
                if r["check"] == "scheduler":
                    flag = "✓" if r["status"] == "OK" else "✗"
                    sched = f" sched_passed={r['scheduled_passed']}" if r.get("scheduled_passed") is not None else ""
                    print(f"  {flag} {r['task']:45s} state={r['state']:10s} last_run={str(r['last_run'])[:19]:19s} result={r['result']}{sched}  {r['status']}")
                elif r["check"] == "db_landing":
                    flag = "✓" if r["status"] == "OK" else "✗"
                    behind = f"{r['hours_behind']}h" if r.get("hours_behind") is not None else f"{r['days_behind']}d"
                    print(f"  {flag} {r['task']:45s} latest={str(r['latest']):19s} behind={behind:>4s}  {r['status']}  ({r['desc']})")
                elif r["check"] == "render_output":
                    flag = "✓" if r["status"] == "OK" else "✗"
                    print(f"  {flag} {r['task']:45s} mtime={r['mtime']}  {r['status']}")
                elif r["check"] == "render_count":
                    flag = "✓" if r["status"] == "OK" else "✗"
                    print(f"  {flag} {r['task']:45s} count={r['count']}  {r['status']}")
            print()
        print("=" * 70)
        if failures:
            print(f"FAILURES: {len(failures)}")
            for (n, s, lr, r) in failures:
                print(f"  - {n}: {s}  (last_run={lr}, result={r})")
        else:
            print("ALL CHECKS PASS")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
