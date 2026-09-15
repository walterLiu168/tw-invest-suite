"""Daily run identity and verified artifacts. No DB writes or publication here."""
import argparse
from collections import Counter
from datetime import date, datetime, timedelta
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import shutil
import sys
import uuid
from market_calendar import expected_session, is_session

REPO = Path(r"C:\Users\icemo\Projects\tw-invest-suite")
RUNTIME = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts")
PUBLIC = REPO / "public"
REPORTS = RUNTIME.parent / "reports"
ANALYZE = Path(r"C:\Groove-Lab\analyze")
STATE = RUNTIME / "_debug" / "pipeline_run.json"
MARKER = RUNTIME / "_debug" / "last_completed.json"
BUCKETS = {"<100", "100-300", "300-1000", ">1000"}
REQUIRED = {"render", "patterns", "patterns_html", "watchlist"}
SOURCE_FILES = (
    "run_daily.ps1", "run_stage.py", "pipeline_state.py", "render_only.py",
    "render_full_watchlist.py", "pattern_classifier.py", "build_patterns_html.py",
    "publish_ghpages_daily.ps1", "publish_ghpages.py", "publish_manifest.py",
    "postflight_daily.py", "daily_summary.py", "build_dashboard.py",
    "marker_watchdog_daily.ps1", "cross_source_runner.py", "market_calendar.py",
    "market_screen_runner.py",
)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def owner_running(run):
    """Use a live process handle, not just a stale 'running' JSON field."""
    if run.get("status") != "running" or not run.get("owner_pid"):
        return False
    import ctypes
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x1000, False, int(run["owner_pid"]))
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        return bool(kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code))) and code.value == 259
    finally:
        kernel.CloseHandle(ctypes.c_void_p(handle))


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    os.replace(tmp, path)


def sha256(path):
    with Path(path).open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else hashlib.sha256(f.read()).hexdigest()


def source_hashes():
    result = {}
    for name in SOURCE_FILES:
        source, runtime = REPO / "scripts" / name, RUNTIME / name
        digest = sha256(source)
        if not runtime.is_file() or sha256(runtime) != digest:
            raise ValueError(f"runtime/repo SHA mismatch: {name}")
        result[name] = digest
    for name in ("src/margin_rebound/finmind_maint.py", "src/margin_rebound/scan.py"):
        result[name] = sha256(REPO / name)
    return result


class PickParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.picks = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "div" and "pick" in attrs.get("class", "").split():
            self.picks.append(tuple(attrs.get(k) for k in ("data-ticker", "data-horizon", "data-bucket")))


def validate_watchlist(body, picks):
    parser = PickParser()
    parser.feed(body)
    expected = Counter((p["ticker"], p["horizon"], p["bucket"]) for p in picks)
    if len(parser.picks) != 24 or Counter(parser.picks) != expected:
        raise ValueError("watchlist HTML does not contain the 24 committed picks")


def db_snapshot():
    import db_client as db
    with db.get_cursor() as c:
        c.execute("SELECT MAX(Date) AS d FROM daily_data2_full")
        data_date = str(c.fetchone()["d"])
        c.execute("SELECT COUNT(*) AS n, COUNT(DISTINCT Ticker) AS tickers FROM daily_data2_full WHERE Date=%s", (data_date,))
        coverage = c.fetchone()
        c.execute("SELECT id,run_date,picks_count FROM market_screen_runs WHERE run_date=%s ORDER BY id DESC LIMIT 1", (data_date,))
        run = c.fetchone()
        if not run:
            raise ValueError(f"no screen run for {data_date}")
        c.execute("SELECT ticker,horizon,bucket,status FROM market_screen_picks WHERE run_id=%s ORDER BY bucket,horizon,ticker", (run["id"],))
        picks = c.fetchall()
    groups = Counter((p["bucket"], p["horizon"]) for p in picks)
    expected = {(b, h): 3 for b in BUCKETS for h in ("long", "short")}
    if run["picks_count"] != 24 or len(picks) != 24 or groups != expected:
        raise ValueError(f"invalid picks for run {run['id']}: {dict(groups)}")
    if any(p["status"] != "active" for p in picks):
        raise ValueError("inactive picks in current run")
    if coverage["tickers"] < 1900:
        raise ValueError(f"OHLCV coverage insufficient: {coverage}")
    return {"data_date": data_date, "run_id": run["id"], "picks_count": 24,
            "bucket_counts": {b: 6 for b in sorted(BUCKETS)}, "picks": picks,
            "ohlcv_rows": coverage["n"], "ohlcv_tickers": coverage["tickers"]}


def begin(mode="full"):
    now = datetime.now()
    run = {"nightly_id": uuid.uuid4().hex, "started_at": now.isoformat(),
           "execution_date": now.date().isoformat(), "status": "running", "mode": mode,
           "owner_pid": int(os.environ.get("TW_OWNER_PID", "0")), "trading_session": is_session(now.date())}
    # Invalidate publish eligibility before preflight, including preflight failures.
    atomic_json(STATE, run)
    try:
        run.update(db_snapshot())
        if run["data_date"] != expected_session(now.date()):
            raise ValueError(f"upstream stale: expected {expected_session(now.date())}, got {run['data_date']}")
        run["source_hashes"] = source_hashes()
        atomic_json(STATE, run)
        return run
    except Exception as e:
        run.update(status="failed", error=str(e))
        atomic_json(STATE, run)
        raise


def artifact(path, gh_path):
    path = Path(path)
    if not path.is_file() or not path.stat().st_size:
        raise ValueError(f"missing/empty artifact: {path}")
    return {"gh_path": gh_path, "abs_path": str(path), "exists": True,
            "sha256": sha256(path), "size": path.stat().st_size}


def complete(stages_path):
    run = read_json(STATE)
    try:
        stages = read_json(stages_path)
        if run["status"] != "running" or os.environ.get("TW_NIGHTLY_ID") != run["nightly_id"]:
            raise ValueError("run identity mismatch")
        required = [s for s in stages if not s.get("Optional")]
        if not REQUIRED.issubset({s["Name"] for s in required}) or any(not s["Ok"] for s in required):
            raise ValueError("required stage failed/missing")
        snapshot = db_snapshot()
        if any(snapshot[k] != run[k] for k in ("data_date", "run_id", "picks")):
            raise ValueError("DB changed during nightly")
        if source_hashes() != run["source_hashes"]:
            raise ValueError("source changed during nightly")
        receipt = read_json(ANALYZE / "render_receipt.json")
        if receipt["nightly_id"] != run["nightly_id"] or receipt["data_date"] != run["data_date"] or receipt["failures"]:
            raise ValueError("render receipt does not certify this run")
        if len(receipt["artifacts"]) != receipt["expected_count"] or receipt["expected_count"] < 1900:
            raise ValueError("incomplete render coverage")
        if receipt.get("fresh_count", 0) < 1900:
            raise ValueError("fresh render coverage insufficient")
        artifacts = list(receipt["artifacts"])
        for a in artifacts:
            if sha256(a["abs_path"]) != a["sha256"]:
                raise ValueError(f"render artifact changed: {a['gh_path']}")
        dd = run["data_date"]
        patterns = read_json(ANALYZE / "patterns.json")
        if patterns["as_of_date"] != dd or patterns.get("total_tickers", 0) < 1900:
            raise ValueError("patterns date/coverage mismatch")
        if patterns.get("nightly_id") != run["nightly_id"]:
            raise ValueError("patterns belongs to another nightly")
        watch = read_json(PUBLIC / "data" / "watchlist-full.json")
        if watch["nightly_id"] != run["nightly_id"] or watch["run_id"] != run["run_id"] or watch["picks"] != run["picks"]:
            raise ValueError("watchlist identity/picks mismatch")
        if watch["html_sha256"] != sha256(PUBLIC / "watchlist.html"):
            raise ValueError("watchlist HTML/receipt mismatch")
        validate_watchlist((PUBLIC / "watchlist.html").read_text(encoding="utf-8"), run["picks"])
        # Publish exactly the files the generators produced, not an older public mirror.
        pairs = [(ANALYZE / "patterns.json", "data/patterns.json"),
                 (ANALYZE / "patterns.html", "patterns.html"),
                 (ANALYZE / "index.html", "analyze/index.html"),
                 (PUBLIC / "watchlist.html", "watchlist.html"),
                 (PUBLIC / "data" / "watchlist-full.json", "data/watchlist-full.json")]
        for name in (f"market-screen-{dd}.html", f"market-screen-{dd}.md",
                     f"deep-dive-prompts-{dd}.md", f"watchlist-full-{dd}.html"):
            pairs.append((REPORTS / name, name))
        for src, dest in pairs:
            target = PUBLIC / dest
            target.parent.mkdir(parents=True, exist_ok=True)
            if src.resolve() != target.resolve():
                shutil.copy2(src, target)
            artifacts.append(artifact(target, dest))
        run.update(status="ok", marker_version="D056-2", completed_at=datetime.now().isoformat(),
                   stages=stages, degraded_stages=sum(not s["Ok"] for s in stages if s.get("Optional")),
                   render_data_issues=receipt.get("data_issues", []), render_count=receipt["expected_count"],
                   fresh_render_count=receipt["fresh_count"], artifacts=artifacts)
        atomic_json(MARKER, run)
        atomic_json(STATE, run)
        return run
    except Exception as e:
        run.update(status="failed", error=str(e))
        atomic_json(STATE, run)
        raise


def verify_marker(marker=None, now=None, check_files=True):
    marker = marker if marker is not None else read_json(MARKER)
    run = read_json(STATE)
    now = now or datetime.now()
    execution_day = now.date() if now.hour >= 18 else now.date() - timedelta(days=1)
    if marker.get("marker_version") != "D056-2" or marker.get("regenerated_by"):
        raise ValueError("uncertified/legacy marker")
    if marker.get("status") != "ok" or run.get("status") != "ok" or marker.get("nightly_id") != run.get("nightly_id"):
        raise ValueError("nightly is incomplete/failed or marker belongs to another run")
    if marker.get("execution_date") != execution_day.isoformat():
        raise ValueError("marker is from a previous nightly")
    started, completed = (datetime.fromisoformat(marker[k]) for k in ("started_at", "completed_at"))
    if not started <= completed <= now or completed - started > timedelta(hours=4):
        raise ValueError("invalid execution timestamps")
    if check_files:
        snapshot = db_snapshot()
        if any(snapshot[k] != marker[k] for k in ("data_date", "run_id", "picks")):
            raise ValueError("marker/DB mismatch")
        if source_hashes() != marker["source_hashes"]:
            raise ValueError("marker/source SHA mismatch")
        if not marker.get("artifacts"):
            raise ValueError("marker has no artifacts")
        for a in marker["artifacts"]:
            if sha256(a["abs_path"]) != a["sha256"]:
                raise ValueError(f"artifact changed: {a['gh_path']}")
    return marker


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["begin", "complete", "verify", "watchdog", "fail"])
    ap.add_argument("--stages")
    ap.add_argument("--mode", default="full")
    args = ap.parse_args()
    try:
        if args.action == "begin":
            value = begin(args.mode)
        elif args.action == "complete":
            value = complete(args.stages)
        elif args.action == "fail":
            value = read_json(STATE)
            if value.get("nightly_id") != os.environ.get("TW_NIGHTLY_ID"):
                raise ValueError("cannot fail another run")
            value.update(status="failed", error="orchestrator failed; see daily log")
            atomic_json(STATE, value)
        elif args.action == "watchdog" and STATE.exists() and owner_running(read_json(STATE)):
            print("PENDING: nightly process is still running; no completion marker fabricated")
            return 0
        else:
            value = verify_marker()
        print(json.dumps({k: value[k] for k in ("nightly_id", "data_date", "run_id", "status")}, ensure_ascii=False))
        return 0
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
