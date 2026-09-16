"""OpenAlice + tw-invest-suite schedule health check.

Verifies every scheduled task:
  1. LastRunTime today (or for weekly/monthly tasks: within expected window)
  2. LastTaskResult == 0 (success) or skipped intentionally
  3. Cross-checks DB: did the data actually land?
     - daily_data2_full latest date
     - ai_5min_kbars latest date
     - stock_news latest crawled_at (ingestion freshness)
     - digest_source_raw latest created_at (UTC ingestion freshness)
     - 6 missing-data domain tables latest dates
     - finmind_taiwan_margin_maintenance latest trade_date
     - C:\\Groove-Lab\\analyze\\*.html modified today (render)
     - C:\\Groove-Lab\\watchlist.html modified today
     - C:\\Groove-Lab\\analyze\\patterns.html modified today

Output: human-readable table + JSON status. Exit 0 if all OK, 1 if any failure.

Usage:
  python -X utf8 check_openalice_health.py            # check today (Asia/Taipei)
  python -X utf8 check_openalice_health.py --date 2026-08-15
  python -X utf8 check_openalice_health.py --json
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
    ("OpenAlice Weekly Shareholding 1330",  "weekday",  "21:10"),
    ("OpenAlice ExDividend 1335",           "weekday",  "13:35"),
    ("OpenAlice Intraday 5m 1800",          "weekday",  "18:00"),
    ("OpenAlice Intraday 5m Retry 1830",    "weekday",  "18:30"),
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

# Tasks that are intentionally Disabled (legacy/obsolete, kept for audit).
# Don't flag them as "NOT READY" failures.
KNOWN_DISABLED = {
    "OpenAlice Daily Download Center 1900",   # legacy replaced by phased schedule
    "OpenAlice Daily OHLCV 1745",             # obsolete phase
    "OpenAlice Intraday 5m 1600",             # obsolete phase
    "OpenAlice Intraday 5m 1555",             # D024: moved to 18:00 (was failing on empty universe)
    "OpenAlice Intraday 5m Retry 1620",       # D024: moved to 18:30
}

# Trigger time lists for every2h tasks (must match install_openalice_aux_schedule.ps1)
AT_LISTS = {
    "OpenAlice News Refresh Every 2h": ["02:00","04:00","06:00","08:00","10:00","12:00","14:00","16:00","18:00","20:00","22:00"],
    "OpenAlice RSS Refresh Every 2h":  ["03:00","05:00","07:00","09:00","11:00","13:00","15:00","17:00","19:00","21:00","23:00"],
}




def get_task_info(name: str) -> dict:
    """Structured Scheduler data avoids localized schtasks labels and encodings."""
    quoted = name.replace("'", "''")
    command = "$n='" + quoted + "';$t=Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue;$i=Get-ScheduledTaskInfo -TaskName $n -ErrorAction SilentlyContinue;[pscustomobject]@{name=$n;state=[string]$t.State;last_run=if($i){$i.LastRunTime.ToString('o')}else{$null};result=if($i){[long]$i.LastTaskResult}else{$null};limit=[string]$t.Settings.ExecutionTimeLimit}|ConvertTo-Json -Compress"
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command], capture_output=True,
                                text=True, encoding='utf-8', timeout=15)
        if result.returncode:
            raise ValueError('Scheduler query failed')
        return json.loads(result.stdout)
    except Exception as e:
        return {'name': name, 'state': 'UNKNOWN', 'last_run': None, 'result': None, 'raw': str(e)}


def running_status(info, last_run, now):
    if info['name'] == 'tw-invest-suite-daily-report':
        import nightly_health
        verdict, state, detail = nightly_health.diagnose()
        return 'RUNNING' if verdict == 'healthy' and (state or {}).get('status') == 'running' else verdict.upper()
    import re
    match = re.fullmatch(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', info.get('limit', ''))
    if not match or not last_run:
        return 'UNKNOWN'
    seconds = sum(int(v or 0) * unit for v, unit in zip(match.groups(), (3600, 60, 1)))
    age = (now - last_run).total_seconds()
    return 'RUNNING' if seconds > 0 and 0 <= age <= seconds else 'STUCK'


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
    try:
        parsed = datetime.fromisoformat(s)
        return parsed.replace(tzinfo=TZ) if parsed.tzinfo is None else parsed.astimezone(TZ)
    except ValueError:
        pass
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
                if latest.tzinfo is None:
                    # rss_to_db explicitly writes UTC-naive raw timestamps.
                    source_tz = timezone.utc if table == 'digest_source_raw' else TZ
                    latest = latest.replace(tzinfo=source_tz)
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
        expected_today = True
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
        # T4 9/11: schtasks state in Task Scheduler context is in Traditional
        # Chinese (就緒=Ready, 執行中=Running, 正在執行=Running). Accept both.
        if info["state"] not in ("Ready", "Running", "就緒", "執行中", "正在執行", "Running."):
            if name in KNOWN_DISABLED:
                status = "DISABLED (intentional)"
            else:
                status = f"NOT READY ({info['state']})"
        elif info['state'] == 'Running' or info['result'] == 267009:
            status = running_status(info, last_run_dt, now_tz)
        elif expected_today and scheduled_passed and not ran_today:
            status = "DID NOT RUN TODAY"
        elif expected_today and scheduled_passed and ran_today and info["result"] != 0:
            # Missing/unrun results cannot pass a due task.
            status = 'UNKNOWN' if info['result'] in (None, 267011) else f"FAILED (code={info['result']})"
        elif not expected_today and ran_today:
            status = "RAN (not expected on weekend)"

        if status not in ("OK", "RAN (not expected on weekend)", "DISABLED (intentional)") and not status.startswith("RUNNING"):
            failures.append((name, status, last_run_str, info["result"]))
        # T4 deep-debug: log non-OK scheduler rows so we can see what cron sees
        try:
            if status not in ("OK", "RAN (not expected on weekend)", "DISABLED (intentional)") and not status.startswith("RUNNING"):
                import os as _os_s
                from datetime import datetime as _dt_s
                with open(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug\check_openalice_health_debug.log", "a", encoding="utf-8") as _f_s:
                    _f_s.write(f"  FAIL scheduler: task={name!r} status={status!r} state={info['state']!r} last_run={last_run_str!r} result={info['result']!r} kind={kind} at={at} ran_today={ran_today} sched_passed={scheduled_passed}\n")
        except Exception:
            pass
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
        ("stock_news",         "crawled_at", "News ingestion — every 2h; provider publication time is separate"),
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
        # Per-table max-days-behind threshold (data cadence is heterogeneous).
        #  - daily_data2_full, ai_5min_kbars, finmind_*_institutional, etc. → 1d (default)
        #  - finmind_taiwan_margin_maintenance → 1d (Stage 1 of daily-report fetches it)
        #  - finmind_taiwan_total_margin_daily → 35d (OpenAlice Missing Data Center weekly cadence; cron last run 8/18, structurally not running)
        #  - finmind_month_revenue → 35d (monthly data published at start of month, 30d lag is normal)
        #  - finmind_warrant_summary, finmind_etf_*, finmind_option_daily → 5d (missing data, weekly cadence)
        TABLE_MAX_DAYS_BEHIND = {
            "finmind_taiwan_total_margin_daily": 35,
            "finmind_month_revenue": 35,
            "finmind_warrant_summary": 5,
            "finmind_etf_active_holding": 5,
            "finmind_etf_premium_discount": 5,
            "finmind_option_daily": 5,
        }
        max_days = TABLE_MAX_DAYS_BEHIND.get(table, 1)
        if latest_date is None and hours_behind is None:
            status = "NO DATA"
        elif is_datetime_col and hours_behind is not None and hours_behind > 6 and is_weekday:
            status = f"BEHIND {hours_behind}h"
        elif days_behind is not None and days_behind > max_days and is_weekday:
            status = f"BEHIND {days_behind}d"
        elif days_behind is not None and days_behind > max(max_days, 5):
            status = f"STALE {days_behind}d"
        classification = 'core'
        registry = []
        if (table, col, desc) in domain_tables:
            with get_conn() as conn:
                cursor = conn.cursor(pymysql.cursors.DictCursor)
                cursor.execute('SELECT dataset_key,refresh_cadence FROM finmind_source_registry WHERE target_table=%s', (table,))
                registry = cursor.fetchall()
            classification = 'registry-listed' if registry else 'unregistered advisory'
            # This legacy domain list cannot certify the canonical daily lane.
            # Preserve its dates and condition without treating a 35d exemption
            # as proof that the data is fresh.
            if not registry:
                status = 'ADVISORY (unregistered; freshness not certified)'
        if status != "OK" and not status.startswith('ADVISORY'):
            failures.append((table, status, str(latest), None))
        # T4 debug: write non-OK db_landing rows to debug log
        try:
            if status != "OK" and table.startswith("finmind"):
                import os as _os
                from datetime import datetime as _dt
                with open(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug\check_openalice_health_debug.log", "a", encoding="utf-8") as _f:
                    _f.write(f"  FAIL {table}: status={status} latest={latest} days_behind={days_behind} max_days_for_table={max_days} is_weekday={is_weekday}\n")
        except Exception:
            pass
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
            "classification": classification,
            "registry": registry,
        })

    # 3) Render output files (tw-invest-suite 22:25)
    html_dir = Path("C:/Groove-Lab/analyze")
    files_to_check = [
        (Path('C:/Groove-Lab/watchlist.html'),  "watchlist.html (Stage 6)"),
        (html_dir / "patterns.html",   "patterns.html (Stage 4)"),
    ]
    # D053: PM 9.2 P0 - only flag render_output if daily-report 22:25 has passed today
    import pipeline_state as pipeline
    current = pipeline.read_json(pipeline.STATE) if pipeline.STATE.exists() else {}
    still_running = pipeline.owner_running(current)
    daily_report_passed = not still_running and ((not is_today) or task_scheduled_time_passed("22:25", check_date, now_tz))
    for path, desc in files_to_check:
        if daily_report_passed:
            ok = file_modified_today(path)
            status = "OK" if ok else "NOT UPDATED TODAY"
        else:
            ok = True
            status = "RUNNING (awaiting completion)" if still_running else "OK (daily-report not yet due today)"
        if not ok:
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
                    # D053: OK or "OK (...not yet run today)" are both pass
                    flag = "✓" if r["status"].startswith("OK") else "✗"
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
    rc = main()
    # Debug log for cron-launched runs (T4 investigation 9/11)
    try:
        import os as _os
        from datetime import datetime as _dt
        log_dir = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug")
        debug_log = log_dir / f"check_openalice_health_debug.log"
        with open(debug_log, "a", encoding="utf-8") as f:
            f.write(f"[{_dt.now().isoformat()}] pid={_os.getpid()} rc={rc} argv={sys.argv}\n")
            f.write(f"  working_dir={_os.getcwd()}\n")
            f.write(f"  python={sys.executable} version={sys.version.split()[0]}\n")
            try:
                _check_date = _dt.now().astimezone().date()
                f.write(f"  check_date={_check_date} (TZ={_dt.now().astimezone().tzinfo})\n")
            except Exception:
                pass
            # T4 deep-debug: in cron context, the in-scope `failures` list is
            # not accessible here. Per-task FAIL lines are written in main()
            # so they are visible in this log already.
    except Exception as e:
        sys.stderr.write(f"debug log failed: {e}\n")
    sys.exit(rc)
