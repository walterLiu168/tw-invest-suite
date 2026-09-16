"""Regression tests for actual process boundaries and release failure gates."""
from collections import Counter
from datetime import datetime
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import pipeline_state as ps
import publish_ghpages as publisher
import build_dashboard as dashboard


class NativeStageTests(unittest.TestCase):
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
        self.marker = {"marker_version": "D056-2", "nightly_id": "current", "status": "ok",
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
        marker = dict(self.marker, run_id=1, picks=[], source_hashes={})
        with patch.object(ps, "db_snapshot", return_value={"data_date": marker["data_date"], "run_id": 1, "picks": []}), patch.object(ps, "source_hashes", return_value={}):
            with self.assertRaisesRegex(ValueError, "no artifacts"):
                ps.verify_marker(marker, self.now)

    def test_changed_artifact_is_rejected(self):
        f = self.root / "watchlist.html"
        f.write_text("old")
        artifact = ps.artifact(f, "watchlist.html")
        f.write_text("changed")
        marker = dict(self.marker, run_id=1, picks=[], source_hashes={}, artifacts=[artifact])
        with patch.object(ps, "db_snapshot", return_value={"data_date": marker["data_date"], "run_id": 1, "picks": []}), patch.object(ps, "source_hashes", return_value={}):
            with self.assertRaisesRegex(ValueError, "artifact changed"):
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
    def test_expected_session_uses_official_closures_not_db_max(self):
        self.assertEqual(ps.expected_session(date(2026, 9, 28)), "2026-09-24")
        self.assertEqual(ps.expected_session(date(2026, 2, 20)), "2026-02-11")
        self.assertEqual(ps.expected_session(date(2026, 9, 15)), "2026-09-15")
        with self.assertRaises(ValueError):
            ps.expected_session(date(2027, 1, 4))

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


if __name__ == "__main__":
    unittest.main()
