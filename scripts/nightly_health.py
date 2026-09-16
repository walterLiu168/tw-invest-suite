"""Watch run identity and stage deadlines; never mint completion or auto-publish."""
import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pipeline_state as ps

STATE = ps.STATE
LOG_DIR = ps.RUNTIME / "_debug" / "stage_logs"
STUCK_AFTER_MIN = 240
STAGE_LOG_QUIET_MIN = 30  # legacy diagnostics only, not an execution deadline
BETWEEN_STAGE_MIN = 5


def read_state():
    return ps.read_json(STATE) if STATE.exists() else None


def pid_alive(pid):
    return ps.owner_running({"status": "running", "owner_pid": pid})


def last_stage_mtime(state):
    nightly = (state or {}).get("nightly_id")
    candidates = list(LOG_DIR.glob(f"*{nightly}_stage*.log")) if nightly else []
    return max((p.stat().st_mtime for p in candidates), default=None)


def diagnose():
    state = read_state()
    if not state:
        return "missing", state, "no pipeline_run.json"
    if state.get("status") == "ok":
        return "healthy", state, "completed; publication freshness is checked separately"
    if state.get("status") != "running":
        return "failed", state, f"status={state.get('status')}"
    if not state.get("started_at") or not state.get("owner_pid"):
        return "unknown", state, "running state lacks start/owner identity"
    now = datetime.now()
    age = now - datetime.fromisoformat(state["started_at"])
    if not ps.owner_running(state):
        return "stuck", state, "owner process is dead or PID creation identity differs"
    if age > timedelta(minutes=STUCK_AFTER_MIN):
        return "stuck", state, "runtime exceeds 240m Scheduler hard cap"
    paths = list(LOG_DIR.glob(f"*{state['nightly_id']}_stage*.heartbeat.json"))
    if paths:
        heartbeat = ps.read_json(max(paths, key=lambda p: p.stat().st_mtime))
        if heartbeat["state"] == "finished":
            gap = now.timestamp() - heartbeat["updated_epoch"]
            if gap > BETWEEN_STAGE_MIN * 60:
                return "stuck", state, f"between-stage gap {gap/60:.1f}m exceeds 5m"
        elif now.timestamp() > heartbeat["started_epoch"] + heartbeat["timeout_sec"] + 45:
            return "stuck", state, f"{heartbeat['label']} exceeded its stage deadline"
        elif now.timestamp() - heartbeat["updated_epoch"] > 120:
            return "unknown", state, "wrapper heartbeat quiet; within stage deadline, do not kill"
        return "healthy", state, f"running age={age.total_seconds()/60:.1f}m within stage budget"
    # A quiet legacy renderer may still be working; silence alone cannot kill it.
    last_log = last_stage_mtime(state)
    if not last_log and age > timedelta(minutes=BETWEEN_STAGE_MIN):
        return "stuck", state, "preflight/initial stage gap exceeds 5m"
    if last_log and now.timestamp() - last_log > STAGE_LOG_QUIET_MIN * 60:
        return "unknown", state, "legacy stage logs quiet; no heartbeat deadline evidence"
    return "healthy", state, "running within hard cap; awaiting first stage heartbeat"


@ps.state_guarded
def recover(state):
    verdict, current, detail = diagnose()
    if verdict != "stuck" or current.get("nightly_id") != state.get("nightly_id"):
        return False
    if ps.owner_running(current):
        result = subprocess.run(["taskkill", "/F", "/T", "/PID", str(current["owner_pid"])],
                                capture_output=True, timeout=15)
        if result.returncode and ps.owner_running(current):
            raise RuntimeError("could not terminate owner tree; state was not force-failed")
    previous_state_path = ps.STATE
    try:
        ps.STATE = STATE
        ps.fail_run(current["nightly_id"], "nightly_health: " + detail)
    finally:
        ps.STATE = previous_state_path
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kill", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        verdict, state, detail = diagnose()
        out = {"verdict": verdict, "detail": detail,
               "nightly_id": (state or {}).get("nightly_id"),
               "owner_pid": (state or {}).get("owner_pid")}
        if verdict == "stuck" and args.kill:
            out["recovered"] = recover(state)
        print(json.dumps(out, ensure_ascii=False))
        return 2 if out.get("recovered") else 0 if verdict == "healthy" else 1
    except Exception as e:
        print(f"[health] FATAL: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
