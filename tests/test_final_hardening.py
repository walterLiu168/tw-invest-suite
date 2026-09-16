"""Failure-injection checks for certification, hung fetches and watchdog recovery."""
from datetime import datetime, timedelta
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import pipeline_state as ps
import bounded_deep_dive as bounded
import build_dashboard as dashboard
spec = importlib.util.spec_from_file_location("final_nightly_health", ROOT / "scripts/nightly_health.py")
nh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nh)


class CertificationTests(unittest.TestCase):
    def test_actual_powershell_51_hashtable_budget_accepts_default_and_rejects_overflow(self):
        source = (ROOT / "scripts/run_daily.ps1").read_text(encoding="utf-8-sig")
        budget = source[source.index("$stageBudgetSec ="):source.index("# Run stages")]
        for minutes, expected in (([10, 90, 30, 10, 30, 30], 0), ([120, 120], 7)):
            with self.subTest(minutes=minutes), tempfile.TemporaryDirectory() as folder:
                script = Path(folder) / "budget.ps1"
                stages = ",".join("@{To=" + str(value * 60) + "}" for value in minutes)
                script.write_text("$ErrorActionPreference='Stop'\ntrap {exit 7}\n"
                                  + "$stages=@(" + stages + ")\n" + budget + "\nexit 0", encoding="utf-8-sig")
                result = subprocess.run(["powershell.exe", "-NoProfile", "-File", str(script)], capture_output=True, timeout=15)
                self.assertEqual(result.returncode, expected, result.stderr)

    def test_actual_cert_process_captures_stderr_and_reads_sidecar_for_zero_and_failure(self):
        source = (ROOT / "scripts/run_daily.ps1").read_text(encoding="utf-8-sig")
        block = source[source.index("$certExitPath ="):source.index("if ($completionExit -ne 0)")]
        block = block.replace(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\run_stage.py", str(ROOT / "scripts/run_stage.py"))
        for rc in (0, 7):
            with self.subTest(rc=rc), tempfile.TemporaryDirectory(prefix="tw-cert-") as folder:
                root = Path(folder)
                (root / "pipeline_state.py").write_text(f"import sys\nprint('fixture cert reason',file=sys.stderr)\nsys.exit({rc})\n")
                script = root / "cert.ps1"
                prolog = "$ErrorActionPreference='Stop';$env:TW_NIGHTLY_ID='fixture';$stagesPath='fixture';$completeLogPath='cert.log';$completeErrPath='cert.err'\ntrap {exit 99}\n"
                prolog += f". '{ROOT / 'scripts/process_lifecycle.ps1'}'\n"
                script.write_text(prolog + block + f"\nif ($completionExit -ne {rc}) {{exit 9}}\nexit 0", encoding="utf-8-sig")
                result = subprocess.run(["powershell.exe", "-NoProfile", "-File", str(script)], cwd=root, capture_output=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("fixture cert reason", (root / "cert.err").read_text())

    def test_late_failure_cannot_overwrite_terminal_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            marker = {"nightly_id": "current", "status": "ok", "marker_version": "D056-2"}
            with patch.object(ps, "STATE", root / "state"), patch.object(ps, "MARKER", root / "marker"):
                ps.atomic_json(ps.STATE, marker)
                ps.atomic_json(ps.MARKER, marker)
                before = ps.STATE.read_bytes()
                ps.fail_run("current")
                self.assertEqual(ps.STATE.read_bytes(), before)
                with self.assertRaisesRegex(ValueError, "another run"):
                    ps.fail_run("older")

    def test_old_ok_marker_does_not_protect_new_running_or_failed_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.object(ps, "STATE", root / "state"), patch.object(ps, "MARKER", root / "marker"):
                ps.atomic_json(ps.MARKER, {"nightly_id": "old", "status": "ok", "marker_version": "D056-2"})
                ps.atomic_json(ps.STATE, {"nightly_id": "new", "status": "running"})
                self.assertEqual(ps.fail_run("new")["status"], "failed")

    def test_actual_powershell_reporting_failure_after_certification_exits_zero(self):
        source = (ROOT / "scripts/run_daily.ps1").read_text(encoding="utf-8-sig")
        tail = source[source.index("# Certification is the final required operation."):]
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "post-cert.ps1"
            script.write_text("$ErrorActionPreference='Stop'\ntrap {exit 9}\nfunction Log-Msg {throw 'injected reporting error'}\n" + tail, encoding="utf-8-sig")
            result = subprocess.run(["powershell.exe", "-NoProfile", "-File", str(script)], capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)


class FetchTests(unittest.TestCase):
    def test_hung_fetch_is_killed_and_other_committed_picks_remain(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            pid_file = root / "pid"
            def command(ticker, output):
                if ticker == "1452":
                    code = f"import os,time;open({str(pid_file)!r},'w').write(str(os.getpid()));time.sleep(60)"
                else:
                    payload = {"stock_id": ticker, "fetch_errors": [], "info": []}
                    code = f"import json;open({str(output)!r},'w').write(json.dumps({payload!r}))"
                return [sys.executable, "-c", code]
            tickers = ["1452"] + [str(2000 + i) for i in range(23)]
            started = time.monotonic()
            result = bounded.fetch_tickers(tickers, timeout_sec=1, budget_sec=15, worker_command=command)
            self.assertLess(time.monotonic() - started, 15)
            self.assertEqual(set(result), set(tickers))
            self.assertIn("timeout", result["1452"]["fetch_errors"][0])
            self.assertFalse(ps.owner_running({"status": "running", "owner_pid": int(pid_file.read_text())}))
            self.assertEqual(result[tickers[-1]]["fetch_errors"], [])

    def test_global_fetch_budget_preserves_all_queued_picks(self):
        calls = []
        def command(ticker, output):
            calls.append(ticker)
            return [sys.executable, "-c", "import time;time.sleep(60)"]
        result = bounded.fetch_tickers(["1452", "2330", "2317"], timeout_sec=1, budget_sec=0.2, worker_command=command)
        self.assertEqual(set(result), {"1452", "2330", "2317"})
        self.assertEqual(calls, ["1452"])
        self.assertIn("budget", result["2330"]["fetch_errors"][0])


class WatchdogTests(unittest.TestCase):
    def test_recovery_terminates_actual_owner_and_child_tree_then_marks_failed(self):
        with tempfile.TemporaryDirectory(prefix="tw-watchdog-tree-") as folder:
            root = Path(folder)
            child_pid = root / "child.pid"
            code = f"import os,time;open({str(child_pid)!r},'w').write(str(os.getpid()));time.sleep(60)"
            owner = subprocess.Popen([sys.executable, "-c", f"import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',{code!r}]);time.sleep(60)"])
            try:
                deadline = time.monotonic() + 5
                while not child_pid.exists() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue(child_pid.exists())
                logs = root / "logs"
                logs.mkdir()
                state = {"nightly_id": "tree", "status": "running", "owner_pid": owner.pid,
                         "owner_created_at": ps.process_creation_time(owner.pid), "started_at": datetime.now().isoformat()}
                ps.atomic_json(root / "state", state)
                ps.atomic_json(logs / "20260916_tree_stage2_render.heartbeat.json", {"state": "finished", "updated_epoch": time.time()-360})
                with patch.object(nh, "STATE", root / "state"), patch.object(nh, "LOG_DIR", logs), patch.object(ps, "MARKER", root / "marker"):
                    self.assertTrue(nh.recover(state))
                owner.wait(timeout=5)
                self.assertFalse(ps.owner_running({"status": "running", "owner_pid": int(child_pid.read_text())}))
                self.assertEqual(ps.read_json(root / "state")["status"], "failed")
            finally:
                if owner.poll() is None:
                    bounded._kill_tree(owner)
                    owner.wait(timeout=5)

    def fixture(self, root, heartbeat, age=110):
        state = {"nightly_id": "fixture", "status": "running", "owner_pid": os.getpid(),
                 "owner_created_at": ps.process_creation_time(os.getpid()),
                 "started_at": (datetime.now() - timedelta(minutes=age)).isoformat()}
        ps.atomic_json(root / "state", state)
        logs = root / "logs"
        logs.mkdir()
        ps.atomic_json(logs / "20260916_fixture_stage2_render.heartbeat.json", heartbeat)
        return state, logs

    def test_live_stage_within_budget_is_not_killed_after_ninety_minutes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            now = time.time()
            state, logs = self.fixture(root, {"state": "running", "label": "render", "started_epoch": now-3600,
                                            "timeout_sec": 5400, "updated_epoch": now})
            with patch.object(nh, "STATE", root / "state"), patch.object(nh, "LOG_DIR", logs):
                self.assertEqual(nh.diagnose()[0], "healthy")

    def test_stage_deadline_and_between_stage_gap_are_detected(self):
        for heartbeat in ({"state": "running", "label": "render", "started_epoch": time.time()-5500,
                           "timeout_sec": 5400, "updated_epoch": time.time()},
                          {"state": "finished", "updated_epoch": time.time()-360}):
            with self.subTest(heartbeat=heartbeat), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                _, logs = self.fixture(root, heartbeat)
                with patch.object(nh, "STATE", root / "state"), patch.object(nh, "LOG_DIR", logs):
                    self.assertEqual(nh.diagnose()[0], "stuck")

    def test_old_watchdog_cannot_fail_a_new_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            newer = {"nightly_id": "new", "status": "running"}
            with patch.object(nh, "diagnose", return_value=("stuck", newer, "orphan")), patch.object(ps, "fail_run") as fail:
                self.assertFalse(nh.recover({"nightly_id": "old"}))
                fail.assert_not_called()

    def test_pid_reuse_is_not_a_live_owner(self):
        self.assertTrue(ps.owner_running({"status": "running", "owner_pid": os.getpid(),
                                         "owner_created_at": ps.process_creation_time(os.getpid())}))
        self.assertFalse(ps.owner_running({"status": "running", "owner_pid": os.getpid(),
                                          "owner_created_at": "2000-01-01T00:00:00"}))


class SchedulerTests(unittest.TestCase):
    def test_actual_powershell_scheduler_query_parses_and_returns_all_tasks(self):
        rows = dashboard.fetch_cron_lastruns()
        self.assertEqual({r["task"] for r in rows}, {"tw-invest-suite-" + n for n in dashboard.TASKS})
        self.assertTrue(all(r["rc"] is not None for r in rows))


class NativeWrapperTests(unittest.TestCase):
    def test_powershell_advances_between_noisy_stages_without_console_inheritance(self):
        source = (ROOT / "scripts/run_daily.ps1").read_text(encoding="utf-8-sig")
        function = source[source.index("function Run-Stage {"):source.index("# === Main ===")]
        with tempfile.TemporaryDirectory(prefix="tw-wrapper-chain-") as folder:
            root = Path(folder)
            child = root / "noisy.py"
            child.write_text("import sys\nsys.stdout.write('x'*1048576)\nsys.stderr.write('y'*1048576)\n")
            function = function.replace(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\run_stage.py", str(ROOT / "scripts/run_stage.py"))
            function = function.replace(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts", str(root))
            script = root / "chain.ps1"
            prolog = "$ErrorActionPreference='Stop';$today='test';$TimeoutMin=1;$env:TW_NIGHTLY_ID='chain';function Log-Msg {param($msg)};function Write-Status {param($Stage,$State,$Pct)}\n"
            prolog += f". '{ROOT / 'scripts/process_lifecycle.ps1'}'\n"
            script.write_text(prolog + function + f"\n$a=Run-Stage -Number 2 -Name render -Cmd '{child}' -TimeoutSec 10\n$b=Run-Stage -Number 3 -Name patterns -Cmd '{child}' -TimeoutSec 10\nif (-not ($a -and $b)) {{exit 9}}\nexit 0", encoding="utf-8-sig")
            result = subprocess.run(["powershell.exe", "-NoProfile", "-File", str(script)], cwd=root, capture_output=True, timeout=35)
            self.assertEqual(result.returncode, 0, result.stderr)
            logs = root / "_debug/stage_logs"
            self.assertEqual(len(list(logs.glob("*.exit"))), 2)
            self.assertEqual(len(list(logs.glob("*.wrapper.err"))), 2)
            self.assertTrue(all(json.loads(p.read_text())["state"] == "finished" for p in logs.glob("*.heartbeat.json")))

    def test_wrapper_timeout_terminates_child_and_grandchild(self):
        with tempfile.TemporaryDirectory(prefix="tw-wrapper-tree-") as folder:
            root = Path(folder)
            pid_file = root / "grandchild.pid"
            child = root / "child.py"
            code = f"import os,time;open({str(pid_file)!r},'w').write(str(os.getpid()));time.sleep(60)"
            child.write_text(f"import subprocess,sys,time\nsubprocess.Popen([sys.executable,'-c',{code!r}])\ntime.sleep(60)\n")
            args = [sys.executable, str(ROOT / "scripts/run_stage.py"), "--label", "tree", "--out", str(root / "out"),
                    "--err", str(root / "err"), "--exit-code-file", str(root / "stage.exit"), "--timeout", "2", str(child)]
            result = subprocess.run(args, capture_output=True, timeout=20)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((root / "stage.exit").read_text(), "-1")
            self.assertFalse(ps.owner_running({"status": "running", "owner_pid": int(pid_file.read_text())}))


if __name__ == "__main__":
    unittest.main()
