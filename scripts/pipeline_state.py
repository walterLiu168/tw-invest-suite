"""Daily run identity and verified artifacts. No DB writes or publication here."""
import argparse
from contextlib import contextmanager
from functools import wraps
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
REQUIRED = {"render", "patterns", "patterns_html", "watchlist", "all_reports"}
REPO_SOURCE_FILES = (
    'src/margin_rebound/finmind_maint.py', 'src/margin_rebound/scan.py',
    'src/all_reports.py', 'src/report_inputs.py', 'src/chip_rank.py',
    'src/chip_advanced.py', 'src/sector_aggregate.py', 'src/build_ticker_meta.py',
    'src/concept_stocks.py', 'src/render_concepts.py', 'src/render_chips_advanced.py',
    'src/industry_zh.py', 'src/generate_og.py', 'src/chip_push.py',
)
REPORT_FRONTEND_FILES = ('analyze.html','readme.html','chips-history.html','monitor.html',
                         'manifest.json','sw.js','assets/textsize.css','assets/textsize.js')
SOURCE_FILES = (
    "run_daily.ps1", "run_stage.py", "pipeline_state.py", "render_only.py",
    "render_full_watchlist.py", "pattern_classifier.py", "build_patterns_html.py",
    "publish_ghpages_daily.ps1", "publish_ghpages.py", "publish_manifest.py",
    "postflight_daily.py", "daily_summary.py", "build_dashboard.py",
    "marker_watchdog_daily.ps1", "cross_source_runner.py", "market_calendar.py",
    "market_screen_runner.py",
    "render_ticker_full.py", "daily_full_tickers.py",
    "market_report.py", "market_report_html.py",
    "bounded_deep_dive.py",
    "nightly_health.py", "nightly_health_daily.ps1",
    "check_openalice_health.py", "db_client.py", "deep_dive_prompts.py", "market_screen.py",
    "process_lifecycle.ps1", "publish_verified_sites.ps1", "sync_groove_release.py",
    "metadata_backfill_daily.ps1", "metadata_backfill.py", "market_screen_daily.ps1",
    "company_refresh_daily.ps1", "company_refresh.py", "postflight_daily.ps1",
    "sync_legacy_tables_runner.ps1", "sync_legacy_tables.py",
    "yfinance_daily.py", "yfinance_batch.py", "cache_manager.py",
    "groove_service_watch.ps1",
)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def owner_running(run):
    """Use a live process handle, not just a stale 'running' JSON field."""
    if run.get("status") != "running" or not run.get("owner_pid"):
        return False
    import ctypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x1000, False, int(run["owner_pid"]))
    if not handle:
        if ctypes.get_last_error() == 5:
            return owner_creation_matches(run, cim_process_creation_time(run['owner_pid']))
        return False
    try:
        code = ctypes.c_ulong()
        if not kernel.GetExitCodeProcess(ctypes.c_void_p(handle), ctypes.byref(code)) or code.value != 259:
            return False
        created = process_creation_time(run["owner_pid"])
        return owner_creation_matches(run, created)
    finally:
        kernel.CloseHandle(ctypes.c_void_p(handle))


def owner_creation_matches(run, created):
    if not created:
        return False
    actual = datetime.fromisoformat(created)
    if run.get('owner_created_at'):
        # FILETIME float conversion and CIM truncation differ by at most 1us.
        return abs(actual - datetime.fromisoformat(run['owner_created_at'])) <= timedelta(microseconds=2)
    if run.get('started_at'):
        return timedelta(seconds=-2) <= datetime.fromisoformat(run['started_at']) - actual <= timedelta(minutes=2)
    return True


def cim_process_creation_time(pid):
    """Read public process identity when another logon denies OpenProcess."""
    import subprocess
    command = (f"$p=Get-CimInstance Win32_Process -Filter 'ProcessId={int(pid)}' -ErrorAction Stop;"
               "if($p){$p.CreationDate.ToString('yyyy-MM-ddTHH:mm:ss.ffffff')}")
    result = subprocess.run([r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe',
                             '-NoProfile', '-Command', command], capture_output=True, text=True,
                            timeout=10, creationflags=0x08000000)
    if result.returncode:
        raise RuntimeError('Cannot verify process identity through CIM')
    created = result.stdout.strip()
    if created:
        datetime.fromisoformat(created)
    return created or None


def process_creation_time(pid):
    import ctypes
    from ctypes.wintypes import FILETIME
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x1000, False, int(pid))
    if not handle:
        if ctypes.get_last_error() == 5:
            return cim_process_creation_time(pid)
        return None
    try:
        times = [FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(ctypes.c_void_p(handle), *(ctypes.byref(t) for t in times)):
            return None
        ticks = (times[0].dwHighDateTime << 32) + times[0].dwLowDateTime
        return datetime.fromtimestamp((ticks - 116444736000000000) / 10000000).isoformat()
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
    for name in REPO_SOURCE_FILES:
        result[name] = sha256(REPO / name)
    for name in REPORT_FRONTEND_FILES:
        result['public/' + name] = sha256(PUBLIC / name)
    result['AI-Telegram/strategy_lab/finmind_batch_update.py'] = sha256(Path(r'D:\CODEX\AI-Telegram\strategy_lab\finmind_batch_update.py'))
    return result


class PickParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.picks = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        # Margin candidates also use class=pick, but are not committed screen picks.
        # Count identified screen cards even if an identity attribute is missing,
        # so malformed committed cards still fail the multiset validation.
        if tag == "div" and "pick" in attrs.get("class", "").split() and attrs.get("id", "").startswith("pick-"):
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
        c.execute("SELECT ticker FROM industry_type WHERE ticker REGEXP '^[0-9]{4}$|^[0-9]{4}[A-Z]$' ORDER BY ticker")
        render_tickers = [row['ticker'] for row in c.fetchall()]
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
            "ohlcv_rows": coverage["n"], "ohlcv_tickers": coverage["tickers"], "render_tickers": render_tickers}


@contextmanager
def state_lock():
    """Serialize begin/complete/fail with watchdog recovery across processes."""
    import ctypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.restype = ctypes.c_void_p
    handle = kernel.CreateMutexW(None, False, "Local\\TwInvestSuiteDailyState")
    if not handle:
        raise OSError("cannot open daily state mutex")
    acquired = False
    try:
        result = kernel.WaitForSingleObject(ctypes.c_void_p(handle), 10000)
        if result not in (0, 0x80):
            raise TimeoutError("daily state mutex unavailable")
        acquired = True
        yield
    finally:
        if acquired:
            kernel.ReleaseMutex(ctypes.c_void_p(handle))
        kernel.CloseHandle(ctypes.c_void_p(handle))


def state_guarded(function):
    @wraps(function)
    def guarded(*args, **kwargs):
        with state_lock():
            return function(*args, **kwargs)
    return guarded


@state_guarded
def begin(mode="full"):
    now = datetime.now()
    execution_day = now.date() if now.hour >= 18 else now.date() - timedelta(days=1)
    run = {"nightly_id": uuid.uuid4().hex, "started_at": now.isoformat(),
           "execution_date": execution_day.isoformat(), "status": "running", "mode": mode,
           "owner_pid": int(os.environ.get("TW_OWNER_PID", "0")), "trading_session": is_session(execution_day)}
    run["owner_created_at"] = process_creation_time(run["owner_pid"]) if run["owner_pid"] else None
    # Invalidate publish eligibility before preflight, including preflight failures.
    atomic_json(STATE, run)
    try:
        run.update(db_snapshot())
        if run["data_date"] != expected_session(execution_day):
            raise ValueError(f"upstream stale: expected {expected_session(execution_day)}, got {run['data_date']}")
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


def validate_all_reports(receipt, run):
    if (receipt.get('status') != 'ok' or receipt.get('nightly_id') != run['nightly_id']
            or receipt.get('data_date') != run['data_date']):
        raise ValueError('All-report receipt identity/status mismatch')
    dates = receipt.get('history_dates', [])
    if len(dates) != 30 or len(set(dates)) != 30 or dates != sorted(dates, reverse=True) or dates[0] != run['data_date']:
        raise ValueError('All-report history coverage mismatch')
    if receipt.get('current_rows', 0) < 1900 or receipt.get('metadata_tickers') != len(run['render_tickers']):
        raise ValueError('All-report market coverage mismatch')
    if receipt.get('rank_tickers',0) < 1900 or receipt.get('advanced_tickers',0) <= 0:
        raise ValueError('All-report ranking/advanced coverage mismatch')
    expected = {'sectors.html','chips.html','chips-advanced.html','concepts.html',
        'data/sectors.json','data/chips.json','data/chips-advanced.json','data/concept-stocks.json',
        'data/tw-industry.json','data/tickers.json','data/chips-history-index.json','data/og.png'}
    expected.update(f'data/chips-history/{day}.json' for day in dates)
    expected.update(REPORT_FRONTEND_FILES)
    artifacts = receipt.get('artifacts', [])
    if len(artifacts) != len(expected) or {a['gh_path'] for a in artifacts} != expected:
        raise ValueError('All-report artifact set mismatch')
    for item in artifacts:
        path = (PUBLIC / item['gh_path']).resolve()
        if path != Path(item['abs_path']).resolve() or not path.is_relative_to(PUBLIC.resolve()) or sha256(path) != item['sha256']:
            raise ValueError('All-report artifact changed/unsafe')
        if path.suffix == '.json' and path.name != 'manifest.json':
            value = read_json(path)
            if isinstance(value,dict):
                expected_date = path.stem if path.parent.name == 'chips-history' else run['data_date']
                if value.get('date') != expected_date or value.get('nightly_id') != run['nightly_id']:
                    raise ValueError('All-report JSON identity mismatch')
            elif path.name == 'tickers.json':
                if sorted(v['ticker'] for v in value) != run['render_tickers'] or any(v.get('date') != run['data_date'] for v in value):
                    raise ValueError('Ticker metadata universe/date mismatch')
    return artifacts


def validate_maintenance_fetch(fetch, run):
    dd = run['data_date']
    if fetch.get('nightly_id') != run['nightly_id'] or fetch.get('requested_date') != dd or fetch.get('status') != 'ok' or not fetch.get('provider_rows') or fetch.get('api_errors') != 0:
        raise ValueError('maintenance fetch does not certify this run')
    if fetch.get('price_refresh_date') != dd or not isinstance(fetch.get('price_refresh_rows'), int) or fetch['price_refresh_rows'] < 1900:
        raise ValueError('maintenance price refresh does not certify this run')
    source_date = date.fromisoformat(fetch['latest_source_date'])
    previous_session = date.fromisoformat(expected_session(date.fromisoformat(dd) - timedelta(days=1)))
    if not previous_session <= source_date <= date.fromisoformat(dd):
        raise ValueError('maintenance provider data is stale or future-dated')
    return source_date.isoformat()


@state_guarded
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
        if any(snapshot[k] != run[k] for k in ("data_date", "run_id", "picks", "render_tickers")):
            raise ValueError("DB changed during nightly")
        if source_hashes() != run["source_hashes"]:
            raise ValueError("source changed during nightly")
        receipt = read_json(ANALYZE / "render_receipt.json")
        if receipt["nightly_id"] != run["nightly_id"] or receipt["data_date"] != run["data_date"] or receipt["failures"]:
            raise ValueError("render receipt does not certify this run")
        if len(receipt["artifacts"]) != receipt["expected_count"] or receipt["expected_count"] < 1900:
            raise ValueError("incomplete render coverage")
        rendered = [Path(artifact['gh_path']).stem for artifact in receipt['artifacts']]
        if sorted(rendered) != run['render_tickers']:
            raise ValueError("render universe differs from the frozen metadata universe")
        if receipt.get("fresh_count", 0) < 1900:
            raise ValueError("fresh render coverage insufficient")
        artifacts = list(receipt["artifacts"])
        all_reports = read_json(RUNTIME / '_debug' / 'all_reports_receipt.json')
        artifacts += validate_all_reports(all_reports, run)
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
                 (ANALYZE / "patterns.html", "analyze/patterns.html"),
                 (ANALYZE / "patterns.json", "analyze/patterns.json"),
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
        maintenance = {}
        if any(stage['Name'] == 'finmind_maint' for stage in required):
            fetch = read_json(RUNTIME / '_debug' / 'maintenance_fetch.json')
            maintenance['maintenance_data_date'] = validate_maintenance_fetch(fetch, run)
        run.update(status="ok", marker_version="D056-3", completed_at=datetime.now().isoformat(),
                   all_reports=all_reports,
                   stages=stages, degraded_stages=sum(not s["Ok"] for s in stages if s.get("Optional")),
                   render_data_issues=receipt.get("data_issues", []), render_count=receipt["expected_count"],
                   fresh_render_count=receipt["fresh_count"], render_numeric_issues=receipt.get("numeric_data_issues", {}),
                   watchlist_fetch_errors=watch.get("fetch_errors", {}), artifacts=artifacts, **maintenance)
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
    if marker.get("marker_version") != "D056-3" or marker.get("regenerated_by"):
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
        if any(snapshot[k] != marker[k] for k in ("data_date", "run_id", "picks", "render_tickers")):
            raise ValueError("marker/DB mismatch")
        if source_hashes() != marker["source_hashes"]:
            raise ValueError("marker/source SHA mismatch")
        if not marker.get("artifacts"):
            raise ValueError("marker has no artifacts")
        for a in marker["artifacts"]:
            if sha256(a["abs_path"]) != a["sha256"]:
                raise ValueError(f"artifact changed: {a['gh_path']}")
        validate_all_reports(marker.get('all_reports', {}), marker)
    return marker


@state_guarded
def fail_run(nightly_id, reason="orchestrator failed; see daily log"):
    value = read_json(STATE)
    if value.get("nightly_id") != nightly_id:
        raise ValueError("cannot fail another run")
    # Certification is terminal. Never resurrect a failed attempt from an old
    # marker, nor invalidate a committed success because reporting later failed.
    if value.get("status") == "ok":
        marker = read_json(MARKER)
        if (marker.get("nightly_id") == nightly_id and marker.get("status") == "ok"
                and marker.get("marker_version") == "D056-3"):
            return value
        raise ValueError("inconsistent completed state; refusing overwrite")
    value.update(status="failed", error=reason)
    atomic_json(STATE, value)
    return value


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
            value = fail_run(os.environ.get("TW_NIGHTLY_ID"))
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
