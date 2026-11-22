"""Retry the daily certified release after late upstream data lands.

This is an idempotent recovery entrypoint for the 06:00 nightly-health run.
It never fabricates a marker: run_daily.ps1 must complete its normal
pipeline_state.complete gate, and publish_verified_sites.ps1 must verify both
sites and final postflight before this process returns success.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import subprocess
import sys

import db_client as db
from market_calendar import expected_session, is_session
import pipeline_state as ps


RUNTIME = Path(__file__).resolve().parent
RUN_DAILY = RUNTIME / "run_daily.ps1"
PUBLISH = RUNTIME / "publish_verified_sites.ps1"
MARKER = RUNTIME / "_debug" / "last_completed.json"
PUBLICATION = RUNTIME / "_debug" / "publication_result.json"
MAINTENANCE = RUNTIME / "_debug" / "maintenance_fetch.json"
STATE = RUNTIME / "_debug" / "pipeline_run.json"


def latest_data_date() -> str | None:
    with db.get_cursor() as cursor:
        cursor.execute("SELECT MAX(Date) AS data_date FROM daily_data2_full")
        row = cursor.fetchone() or {}
    value = row.get("data_date") if isinstance(row, dict) else row[0]
    return str(value) if value else None


def read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def certified_for(data_date: str) -> bool:
    marker = read_json(MARKER)
    publication = read_json(PUBLICATION)
    maintenance = read_json(MAINTENANCE)
    nightly_id = marker.get("nightly_id")
    return bool(
        marker.get("marker_version") == "D056-3"
        and marker.get("status") == "ok"
        and marker.get("data_date") == data_date
        and nightly_id
        and publication.get("nightly_id") == nightly_id
        and publication.get("data_date") == data_date
        and publication.get("status") == "verified"
        and publication.get("report_status") == "verified"
        and publication.get("postflight_exit") == 0
        and ps.maintenance_claim_holds(marker, maintenance)
    )


def owner_running() -> bool:
    state = read_json(STATE)
    return state.get("status") == "running" and ps.owner_running(state)


def expected_catchup_date(today: date | None = None) -> str:
    today = today or date.today()
    return expected_session(today - timedelta(days=1))


def run_powershell(script: Path, *extra_args: str) -> int:
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *extra_args],
        cwd=str(RUNTIME),
        timeout=240 * 60,
    )
    return int(result.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description="Retry a late daily certified release.")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    data_date = latest_data_date()
    target = expected_catchup_date()
    result = {"target_date": target, "latest_data_date": data_date}
    if not data_date or data_date != target or not is_session(date.fromisoformat(target)):
        result["status"] = "WAITING_FOR_LANDED_SESSION"
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if certified_for(data_date):
        result["status"] = "ALREADY_CERTIFIED"
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if owner_running():
        result["status"] = "NIGHTLY_ALREADY_RUNNING"
        print(json.dumps(result, ensure_ascii=False))
        return 0
    if args.check_only:
        result["status"] = "READY_FOR_CATCHUP"
        print(json.dumps(result, ensure_ascii=False))
        return 0

    # A retry must refresh the valuation receipt for this new nightly_id.
    # Without -Force, a fresh cache can leave the previous nightly's receipt
    # in place and finalize_inputs correctly rejects the run.
    result["run_daily_exit"] = run_powershell(RUN_DAILY, "-Force")
    if result["run_daily_exit"] != 0:
        result["status"] = "NIGHTLY_FAILED"
        print(json.dumps(result, ensure_ascii=False))
        return result["run_daily_exit"] or 1
    result["publish_exit"] = run_powershell(PUBLISH)
    result["status"] = "CERTIFIED_AND_PUBLISHED" if result["publish_exit"] == 0 else "PUBLISH_FAILED"
    print(json.dumps(result, ensure_ascii=False))
    return result["publish_exit"]


if __name__ == "__main__":
    sys.exit(main())
