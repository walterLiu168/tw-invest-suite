"""TWSE scheduled closures, verified 2026-09-15. Unknown years fail closed.

Source: https://www.twse.com.tw/holidaySchedule/holidaySchedule?response=html
Unscheduled closures require an explicit update; never infer them from stale DB data.
"""
from datetime import timedelta

CLOSED = {
    2026: set("""2026-01-01 2026-02-12 2026-02-13 2026-02-15 2026-02-16
    2026-02-17 2026-02-18 2026-02-19 2026-02-20 2026-02-27 2026-02-28
    2026-04-03 2026-04-04 2026-04-05 2026-04-06 2026-05-01 2026-06-19
    2026-09-25 2026-09-28 2026-10-09 2026-10-10 2026-10-25 2026-10-26
    2026-12-25""".split())
}


def is_session(day):
    return day.weekday() < 5 and day.isoformat() not in CLOSED.get(day.year, set())


def expected_session(day):
    if day.year not in CLOSED:
        raise ValueError(f"TWSE calendar for {day.year} must be verified before running")
    while not is_session(day):
        day -= timedelta(days=1)
    return day.isoformat()
