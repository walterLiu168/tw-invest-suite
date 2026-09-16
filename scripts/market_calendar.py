"""TWSE scheduled closures, verified 2026-09-15. Unknown years fail closed.

Source: https://www.twse.com.tw/holidaySchedule/holidaySchedule?response=html
Unscheduled closures require an explicit update; never infer them from stale DB data.

Hardening contract (D056-2):
- Year not in CLOSED → raises (fail closed; downstream cannot assume "open")
- Date in UNSCHEDULED → closed regardless of weekday (typhoon / ad-hoc)
- LAST_VERIFIED > STALENESS_WARN_DAYS days → metadata.stale=True (advisory only;
  does NOT block; the actual fail-closed gate is the year-in-CLOSED check)
- Calendar metadata (last_verified, source_url, counts) is read-only and never
  mutated by the pipeline; updates are committed via git when TWSE publishes
  changes.
"""
from datetime import date, timedelta

# Scheduled closures (annual holidays). Verified against the TWSE link above
# on the LAST_VERIFIED date below. Unknown years fail closed.
CLOSED = {
    2026: set("""2026-01-01 2026-02-12 2026-02-13 2026-02-15 2026-02-16
    2026-02-17 2026-02-18 2026-02-19 2026-02-20 2026-02-27 2026-02-28
    2026-04-03 2026-04-04 2026-04-05 2026-04-06 2026-05-01 2026-06-19
    2026-09-25 2026-09-28 2026-10-09 2026-10-10 2026-10-25 2026-10-26
    2026-12-25""".split()),
}

# Unscheduled / emergency closures (typhoon, special holidays). Add ISO dates
# here when TWSE announces ad-hoc closures mid-year. Per spec, never infer
# these from DB gaps; the human or a manual fetch decides.
UNSCHEDULED = {
    2026: set(),  # e.g. {"2026-10-12"} after a typhoon announcement
}

LAST_VERIFIED = "2026-09-15"
SOURCE_URL = "https://www.twse.com.tw/holidaySchedule/holidaySchedule?response=html"
STALENESS_WARN_DAYS = 60


def _closed_for(day):
    """Union of scheduled + unscheduled closures for a given year."""
    return CLOSED.get(day.year, set()) | UNSCHEDULED.get(day.year, set())


def _ensure_year_known(day):
    if day.year not in CLOSED:
        raise ValueError(
            f"TWSE calendar for {day.year} must be verified before running "
            f"(known years: {sorted(CLOSED.keys())})"
        )


def is_session(day):
    _ensure_year_known(day)
    return day.weekday() < 5 and day.isoformat() not in _closed_for(day)


def expected_session(day):
    _ensure_year_known(day)
    while not is_session(day):
        day -= timedelta(days=1)
    return day.isoformat()


def verify_calendar(today=None):
    """Read-only metadata about the calendar's verification state.

    Does NOT touch the network and does NOT fail-closed on its own. The actual
    fail-closed gate is in `is_session` / `expected_session` (year not in CLOSED
    raises). This accessor exists so callers (run_daily.ps1, dashboard) can
    surface staleness as a warning without silently pretending freshness.

    Returns dict with keys:
        last_verified, source_url, unscheduled_count, scheduled_count,
        known_years, age_days, stale
    """
    today = today or date.today()
    verified = date.fromisoformat(LAST_VERIFIED)
    age = (today - verified).days
    return {
        "last_verified": LAST_VERIFIED,
        "source_url": SOURCE_URL,
        "unscheduled_count": sum(len(s) for s in UNSCHEDULED.values()),
        "scheduled_count": sum(len(s) for s in CLOSED.values()),
        "known_years": sorted(CLOSED.keys()),
        "age_days": age,
        "stale": age > STALENESS_WARN_DAYS,
    }