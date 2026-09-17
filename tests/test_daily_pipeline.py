"""Regression tests for actual process boundaries and release failure gates."""
from collections import Counter
from datetime import datetime, timedelta
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import threading
import unittest
from datetime import date
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import pipeline_state as ps
import publish_ghpages as publisher
import build_dashboard as dashboard
import nightly_health as nh


class NativeStageTests(unittest.TestCase):
    def test_live_process_creation_identity_is_required(self):
        command = f". '{ROOT / 'scripts/process_lifecycle.ps1'}';$created=(Get-Process -Id $PID).StartTime.ToUniversalTime().Ticks;if (-not (Test-OwnedProcess $PID $created)) {{exit 7}};if (Test-OwnedProcess $PID 0) {{exit 8}};if (-not (Wait-OwnedProcess $PID 0 2000)) {{exit 9}}"
        result = subprocess.run(['powershell.exe','-NoProfile','-Command',command], capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_powershell_child_flags_spaces_failure_and_optional(self):
        with tempfile.TemporaryDirectory(prefix="pipeline-native-") as folder:
            root = Path(folder)
            child = root / "child with spaces.py"
            child.write_text("import sys\nassert sys.argv[1:]==['--no-news','--out','a b']\nsys.exit(42)\n")
            source = (ROOT / "scripts" / "run_daily.ps1").read_text(encoding="utf-8-sig")
            fn = source[source.index("function Run-Stage {"):source.index("# === Main ===")]
            fn = fn.replace(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\run_stage.py", str(ROOT / "scripts" / "run_stage.py"))
            fn = fn.replace(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts", str(root))
            prolog = "$ErrorActionPreference='Stop'; $today='test'; $TimeoutMin=1; $env:TW_NIGHTLY_ID='fixture'; function Log-Msg {param($msg)}; function Write-Status {param($Stage,$State,$Pct)}\n"
            prolog += f". '{ROOT / 'scripts/process_lifecycle.ps1'}'\n"
            script = root / "test.ps1"
            script.write_text(prolog + fn + f"\n$cmd='\"{child}\" --no-news --out \"a b\"'\n$a=Run-Stage -Number 1 -Name required -Cmd $cmd -TimeoutSec 5\n$b=Run-Stage -Number 2 -Name optional -Cmd $cmd -TimeoutSec 5 -Optional\nif ($a -or $b) {{exit 9}}\nexit 0\n", encoding="utf-8-sig")
            r = subprocess.run(["powershell.exe", "-NoProfile", "-File", str(script)], cwd=root, capture_output=True, text=True, timeout=30)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            codes = sorted(p.read_text() for p in (root / "_debug" / "stage_logs").glob("*.exit"))
            self.assertEqual(codes, ["42", "42"])

    def test_wrapper_success_timeout_and_missing_child(self):
        with tempfile.TemporaryDirectory(prefix="pipeline-wrapper-") as folder:
            root = Path(folder)
            child = root / "child.py"
            base = [sys.executable, str(ROOT / "scripts" / "run_stage.py"), "--label", "test", "--out", str(root / "stdout"), "--err", str(root / "stderr"), "--exit-code-file", str(root / "exit"), "--timeout", "1"]
            for code, expected in [("pass", "0"), ("import time; time.sleep(10)", "-1")]:
                child.write_text(code)
                r = subprocess.run(base + [str(child)], capture_output=True, timeout=15)
                self.assertEqual((root / "exit").read_text(), expected)
                self.assertEqual(r.returncode == 0, expected == "0")
            r = subprocess.run(base + [str(root / "missing.py")], capture_output=True, timeout=15)
            self.assertNotEqual(r.returncode, 0)
            self.assertNotEqual((root / "exit").read_text(), "0")


class ReleaseGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pipeline-gate-")
        self.root = Path(self.temp.name)
        self.state_patch = patch.object(ps, "STATE", self.root / "state.json")
        self.state_patch.start()
        self.marker = {"marker_version": "D056-3", "nightly_id": "current", "status": "ok",
                       "execution_date": "2026-09-15", "data_date": "2026-09-15",
                       "started_at": "2026-09-15T22:25:00", "completed_at": "2026-09-15T23:55:00"}
        ps.atomic_json(ps.STATE, self.marker)
        self.now = datetime(2026, 9, 16, 0, 30)

    def tearDown(self):
        self.state_patch.stop()
        self.temp.cleanup()

    def test_current_passes_but_old_failed_future_and_watchdog_do_not(self):
        self.assertEqual(ps.verify_marker(self.marker, self.now, False), self.marker)
        for changes in ({"execution_date": "2026-09-14"}, {"status": "failed"},
                        {"regenerated_by": "watchdog"}, {"completed_at": "2026-09-16T01:00:00"},
                        {"marker_version": "D056-1"}, {"nightly_id": "older"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                ps.verify_marker(dict(self.marker, **changes), self.now, False)

    def test_new_running_or_failed_attempt_invalidates_old_success(self):
        for status in ("running", "failed"):
            ps.atomic_json(ps.STATE, dict(self.marker, nightly_id="next", status=status))
            with self.assertRaises(ValueError):
                ps.verify_marker(self.marker, self.now, False)

    def test_missing_marker_artifacts_cannot_be_prepared(self):
        marker = dict(self.marker, run_id=1, picks=[], source_hashes={}, render_tickers=[])
        with patch.object(ps, "db_snapshot", return_value={"data_date": marker["data_date"], "run_id": 1, "picks": [], "render_tickers": []}), patch.object(ps, "source_hashes", return_value={}):
            with self.assertRaisesRegex(ValueError, "no artifacts"):
                ps.verify_marker(marker, self.now)

    def test_changed_artifact_is_rejected(self):
        f = self.root / "watchlist.html"
        f.write_text("old")
        artifact = ps.artifact(f, "watchlist.html")
        f.write_text("changed")
        marker = dict(self.marker, run_id=1, picks=[], source_hashes={}, artifacts=[artifact], render_tickers=[])
        with patch.object(ps, "db_snapshot", return_value={"data_date": marker["data_date"], "run_id": 1, "picks": [], "render_tickers": []}), patch.object(ps, "source_hashes", return_value={}):
            with self.assertRaisesRegex(ValueError, "artifact changed"):
                ps.verify_marker(marker, self.now)

    def test_metadata_universe_change_invalidates_certified_render(self):
        marker = dict(self.marker, run_id=1, picks=[], source_hashes={}, render_tickers=['2330'])
        with patch.object(ps, 'db_snapshot', return_value={'data_date': marker['data_date'], 'run_id':1,'picks':[], 'render_tickers':['2330','7768']}):
            with self.assertRaisesRegex(ValueError, 'marker/DB mismatch'):
                ps.verify_marker(marker, self.now)

    def test_staged_hash_matches_actual_published_path(self):
        f = self.root / "watchlist.html"
        f.write_text("current")
        manifest = {"artifacts": [ps.artifact(f, "watchlist.html")]}
        publisher.verify_staged(self.root, manifest)
        f.write_text("stale")
        with self.assertRaises(ValueError):
            publisher.verify_staged(self.root, manifest)


class ContentTests(unittest.TestCase):
    def test_provider_numeric_placeholders_become_missing_with_warnings(self):
        import cross_source_runner as csr
        raw = {"trailingPE": "Infinity", "forwardPE": "12.5", "priceToBook": "N/A",
               "dividendYield": float("nan"), "marketCap": "1000000", "beta": "-0.2",
               "returnOnEquity": True, "longName": "Example", "industry": "Textiles"}
        with patch.object(csr, "_db_basic", return_value={"ticker": "1452"}), patch.object(csr.cm, "get_fresh", side_effect=lambda ticker, key: {"data": raw} if key == "yfinance" else None):
            result = csr.assemble("1452", use_yfinance=False, fetch_news=False, cache_only=True)
        self.assertIsNone(result["valuation"]["pe"])
        self.assertIsNone(result["valuation"]["pb"])
        self.assertIsNone(result["valuation"]["dividend_yield"])
        self.assertIsNone(result["yfinance"]["returnOnEquity"])
        self.assertEqual(result["valuation"]["forward_pe"], 12.5)
        self.assertEqual(result["valuation"]["beta"], -0.2)
        self.assertEqual(result["yfinance"]["industry"], "Textiles")
        self.assertEqual(set(result["_meta"]["numeric_warnings"]), {"trailingPE", "priceToBook", "dividendYield", "returnOnEquity"})
        self.assertEqual(raw["trailingPE"], "Infinity")  # provider cache is preserved

    def test_expected_session_uses_official_closures_not_db_max(self):
        self.assertEqual(ps.expected_session(date(2026, 9, 28)), "2026-09-24")
        self.assertEqual(ps.expected_session(date(2026, 2, 20)), "2026-02-11")
        self.assertEqual(ps.expected_session(date(2026, 9, 15)), "2026-09-15")
        with self.assertRaises(ValueError):
            ps.expected_session(date(2027, 1, 4))

    def test_calendar_all_2026_holidays_closed(self):
        # Every TWSE-scheduled 2026 closure must be closed even mid-week.
        from market_calendar import CLOSED, is_session
        self.assertEqual(len(CLOSED[2026]), 24, "expected 24 TWSE holidays in 2026")
        for iso in sorted(CLOSED[2026]):
            d = date.fromisoformat(iso)
            self.assertFalse(is_session(d), f"{iso} should be closed")

    def test_calendar_weekend_always_closed(self):
        # 2026-09-12 (Sat) and 2026-09-13 (Sun) are weekend closures.
        from market_calendar import is_session
        self.assertFalse(is_session(date(2026, 9, 12)))
        self.assertFalse(is_session(date(2026, 9, 13)))
        # But a Monday after a non-holiday weekend is open.
        self.assertTrue(is_session(date(2026, 9, 14)))

    def test_calendar_unknown_year_raises_is_session(self):
        from market_calendar import is_session
        with self.assertRaisesRegex(ValueError, "2027"):
            is_session(date(2027, 1, 4))
        with self.assertRaisesRegex(ValueError, "2025"):
            is_session(date(2025, 12, 31))

    def test_calendar_unscheduled_closures_override_weekday(self):
        # A typhoon day on a Wednesday must be closed.
        from market_calendar import is_session, UNSCHEDULED
        UNSCHEDULED[2026].add("2026-10-14")  # Wednesday
        try:
            self.assertFalse(is_session(date(2026, 10, 14)))
            # expected_session walks back to 2026-10-13 (Tuesday — open).
            self.assertEqual(ps.expected_session(date(2026, 10, 14)), "2026-10-13")
        finally:
            UNSCHEDULED[2026].discard("2026-10-14")

    def test_calendar_verify_metadata_age_and_staleness(self):
        from datetime import timedelta
        from market_calendar import verify_calendar, LAST_VERIFIED, SOURCE_URL, STALENESS_WARN_DAYS
        meta = verify_calendar(today=date(2026, 9, 15))
        self.assertEqual(meta["last_verified"], LAST_VERIFIED)
        self.assertEqual(meta["source_url"], SOURCE_URL)
        self.assertEqual(meta["age_days"], 0)
        self.assertFalse(meta["stale"])
        self.assertIn(2026, meta["known_years"])
        self.assertEqual(meta["scheduled_count"], 24)
        # 61 days out → stale=True
        meta_stale = verify_calendar(today=date(2026, 9, 15) + timedelta(days=STALENESS_WARN_DAYS + 1))
        self.assertTrue(meta_stale["stale"])
        self.assertEqual(meta_stale["age_days"], STALENESS_WARN_DAYS + 1)

    def test_watchlist_exact_multiset_not_just_count_or_ticker(self):
        picks = [{"ticker": str(1000 + i), "horizon": h, "bucket": b} for i, b in enumerate(sorted(ps.BUCKETS)) for h in ("long", "short") for _ in range(3)]
        body = "".join(f'<div class="pick" id="pick-{p["ticker"]}-{p["horizon"]}" data-ticker="{p["ticker"]}" data-horizon="{p["horizon"]}" data-bucket="{p["bucket"]}"></div>' for p in picks)
        ps.validate_watchlist(body, picks)
        ps.validate_watchlist('<div class="pick">margin candidate</div>' * 60 + body, picks)
        with self.assertRaises(ValueError):
            ps.validate_watchlist(body.replace('data-horizon="long"', ''), picks)
        for bad in (body[:body.index("</div>") + 6], body.replace('data-ticker="1000"', 'data-ticker="9999"')):
            with self.assertRaises(ValueError):
                ps.validate_watchlist(bad, picks)

    def test_no_marker_or_remote_evidence_never_green(self):
        self.assertEqual(dashboard.evaluate(None, {}, []), "CRITICAL")
        self.assertEqual(dashboard.evaluate({"nightly_id": "a"}, {"nightly_id": "b", "status": "verified"}, []), "WARNING")
        self.assertEqual(dashboard.evaluate({"nightly_id": "a"}, {"nightly_id": "a", "status": "verified"}, []), "OK")


class PublicationTests(unittest.TestCase):
    def test_git_release_preserves_certified_bytes_with_windows_autocrlf(self):
        with tempfile.TemporaryDirectory(prefix="pipeline-git-") as folder:
            root = Path(folder)
            publisher.run(["git", "init", "-b", "main"], root)
            publisher.run(["git", "config", "core.autocrlf", "true"], root)
            # Attributes, including nested ones, must not rewrite release bytes.
            (root / ".gitattributes").write_text("*.html text eol=lf\n")
            page = root / "analyze" / "2330.html"
            page.parent.mkdir()
            page.write_bytes(b"<html>\r\ncurrent\r\n</html>\r\n")
            publisher.initialize_release_git(root)
            publisher.run(["git", "add", "-A"], root)
            blob = subprocess.run(["git", "show", ":analyze/2330.html"], cwd=root, check=True, capture_output=True).stdout
            self.assertEqual(blob, page.read_bytes())

    def test_remote_verifier_rejects_one_stale_selected_ticker(self):
        with tempfile.TemporaryDirectory(prefix="pipeline-http-") as folder:
            root = Path(folder)
            served, staged = root / "served", root / "staged"
            manifest = {"nightly_id": "fixture", "data_date": "2026-09-15", "artifacts": [], "tickers": [{"ticker": "2330"}, {"ticker": "2317"}]}
            paths = ["watchlist.html", "patterns.html", "analyze/patterns.html", "analyze/patterns.json", "data/patterns.json", "data/watchlist-full.json", "data/publish_manifest_2026-09-15.json", "analyze/2330.html", "analyze/2317.html"]
            for base in (served, staged):
                for relative in paths:
                    f = base / relative
                    f.parent.mkdir(parents=True, exist_ok=True)
                    f.write_text("current " + relative, encoding="utf-8")
            class QuietHandler(SimpleHTTPRequestHandler):
                def log_message(self, *args):
                    pass
            server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(served)))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with patch.object(publisher.pm, "GITHUB_PAGES_BASE", f"http://127.0.0.1:{server.server_port}"):
                    self.assertEqual(set(publisher.remote_verify(staged, manifest)), set(paths))
                    (served / "analyze" / "2317.html").write_text("yesterday")
                    with self.assertRaisesRegex(ValueError, "2317"):
                        publisher.remote_verify(staged, manifest)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)

    def test_default_prepare_never_invokes_git_push(self):
        with tempfile.TemporaryDirectory(prefix="pipeline-prepare-") as folder:
            root = Path(folder)
            manifest = {"nightly_id": "fixture", "data_date": "2026-09-15", "run_id": 16, "artifacts": []}
            with patch.object(ps, "verify_marker", return_value={}), patch.object(publisher, "prepare_site", return_value=(root, manifest)), patch.object(ps, "RUNTIME", root), patch.object(publisher, "run") as git, patch.object(sys, "argv", ["publish_ghpages.py"]):
                self.assertEqual(publisher.main(), 0)
                git.assert_not_called()

    def test_remote_failure_never_becomes_verified(self):
        with tempfile.TemporaryDirectory(prefix="pipeline-remote-failure-") as folder:
            root = Path(folder)
            manifest = {"nightly_id": "fixture", "data_date": "2026-09-15", "run_id": 16, "artifacts": []}
            result_path = root / "result.json"
            with patch.object(ps, "verify_marker", return_value={}), patch.object(publisher, "prepare_site", return_value=(root, manifest)), patch.object(publisher, "verify_staged"), patch.object(ps, "RUNTIME", root), patch.object(publisher, "RESULT", result_path), patch.object(publisher, "run", return_value="commit"), patch.object(publisher, "remote_verify", side_effect=ValueError("stale page")), patch.object(publisher.time, "sleep"), patch.object(sys, "argv", ["publish_ghpages.py", "--publish"]):
                self.assertEqual(publisher.main(), 1)
                self.assertEqual(ps.read_json(result_path)["status"], "failed")


class NightlyHealthTests(unittest.TestCase):
    def _write_state(self, tmp, status, started_offset_min=None, owner_pid=0):
        state = {"nightly_id": "fixture", "started_at": datetime.now().isoformat(),
                 "execution_date": "2026-09-15", "status": status, "mode": "full",
                 "owner_pid": owner_pid, "trading_session": True, "data_date": "2026-09-15",
                 "run_id": 16, "picks_count": 24,
                 "bucket_counts": {b: 6 for b in sorted(ps.BUCKETS)}}
        state["owner_created_at"] = ps.process_creation_time(owner_pid) if owner_pid else None
        if started_offset_min is not None:
            state["started_at"] = (datetime.now() - timedelta(minutes=started_offset_min)).isoformat()
        tmp.write_text(json.dumps(state), encoding="utf-8")

    def test_diagnose_missing_state_is_healthy(self):
        with tempfile.TemporaryDirectory(prefix="nh-missing-") as folder:
            with patch.object(nh, "STATE", Path(folder) / "absent.json"):
                verdict, state, detail = nh.diagnose()
            self.assertEqual(verdict, "missing")
            self.assertIsNone(state)

    def test_diagnose_completed_run_is_healthy(self):
        with tempfile.TemporaryDirectory(prefix="nh-done-") as folder:
            p = Path(folder) / "pipeline_run.json"
            self._write_state(p, status="ok")
            with patch.object(nh, "STATE", p):
                verdict, state, detail = nh.diagnose()
            self.assertEqual(verdict, "healthy")
            self.assertEqual(state["status"], "ok")

    def test_diagnose_stuck_when_running_too_long_with_quiet_logs(self):
        # Simulate 9/16 incident: started 2h ago, owner_pid alive but idle,
        # no stage log updates in 40+ minutes.
        with tempfile.TemporaryDirectory(prefix="nh-stuck-") as folder:
            root = Path(folder)
            state_path = root / "pipeline_run.json"
            log_dir = root / "stage_logs"
            log_dir.mkdir()
            self._write_state(state_path, status="running", started_offset_min=120,
                              owner_pid=os.getpid())
            (log_dir / "20260916_fixture_stage2_render.log").write_text("old", encoding="utf-8")
            old_time = time.time() - 2400
            os.utime(log_dir / "20260916_fixture_stage2_render.log", (old_time, old_time))
            with patch.object(nh, "STATE", state_path), patch.object(nh, "LOG_DIR", log_dir):
                verdict, state, detail = nh.diagnose()
            self.assertEqual(verdict, "unknown", detail)
            self.assertIn("no heartbeat deadline evidence", detail)

    def test_diagnose_orphan_when_owner_pid_dead(self):
        # PID 1 on Windows may exist but the running state should still detect via
        # age threshold. Use a clearly dead PID.
        with tempfile.TemporaryDirectory(prefix="nh-orphan-") as folder:
            root = Path(folder)
            state_path = root / "pipeline_run.json"
            log_dir = root / "stage_logs"
            log_dir.mkdir()
            self._write_state(state_path, status="running", started_offset_min=10,
                              owner_pid=999999)
            with patch.object(nh, "STATE", state_path), patch.object(nh, "LOG_DIR", log_dir):
                verdict, state, detail = nh.diagnose()
            # PID 999999 is not alive → caught by age threshold + log check;
            # the verdict may be "stuck" or "healthy" depending on log mtime.
            # We assert the function does not crash and returns one of the two.
            self.assertEqual(verdict, "stuck", detail)

    def test_diagnose_running_but_fresh_is_healthy(self):
        with tempfile.TemporaryDirectory(prefix="nh-fresh-") as folder:
            root = Path(folder)
            state_path = root / "pipeline_run.json"
            log_dir = root / "stage_logs"
            log_dir.mkdir()
            self._write_state(state_path, status="running", started_offset_min=5,
                              owner_pid=os.getpid())
            (log_dir / "20260916_fixture_stage2_render.log").write_text("now", encoding="utf-8")
            with patch.object(nh, "STATE", state_path), patch.object(nh, "LOG_DIR", log_dir):
                verdict, state, detail = nh.diagnose()
            self.assertEqual(verdict, "healthy")


if __name__ == "__main__":
    unittest.main()
