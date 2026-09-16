import ctypes
import os
import json
import subprocess
import tempfile
import time
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import pipeline_state as ps


class S4uOwnerIdentityTests(unittest.TestCase):
    def test_stage_cleans_actual_descendants_after_owner_termination(self):
        with tempfile.TemporaryDirectory(prefix='tw-orphan-stage-') as folder:
            root = Path(folder)
            child_script = root/'child.py'
            child_script.write_text("import os,time,subprocess,sys\nfrom pathlib import Path\nPath('child.pid').write_text(str(os.getpid()))\nsubprocess.Popen([sys.executable,'-c',\"import os,time;open('grandchild.pid','w').write(str(os.getpid()));time.sleep(120)\"])\ntime.sleep(120)\n")
            stage = Path(ps.__file__).with_name('run_stage.py')
            cmd = [sys.executable,str(stage),'--label','orphan','--out',str(root/'out'),'--err',str(root/'err'),'--exit-code-file',str(root/'exit'),'--timeout','90','--workdir',str(root),str(child_script)]
            owner_script = root/'owner.py'
            owner_script.write_text(f"import subprocess,time\np=subprocess.Popen({cmd!r},stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)\nopen({str(root/'wrapper.pid')!r},'w').write(str(p.pid))\ntime.sleep(120)\n")
            owner = subprocess.Popen([sys.executable,str(owner_script)])
            try:
                deadline=time.monotonic()+8
                while not (root/'grandchild.pid').exists() and time.monotonic()<deadline:
                    time.sleep(.05)
                self.assertTrue((root/'grandchild.pid').exists())
                owner.terminate()
                owner.wait(timeout=5)
                deadline=time.monotonic()+25
                while not (root/'exit').exists() and time.monotonic()<deadline:
                    time.sleep(.1)
                self.assertEqual((root/'exit').read_text(),'-2')
                heartbeat=json.loads((root/'exit.heartbeat.json').read_text())
                self.assertEqual(heartbeat['stop_reason'],'owner exited')
                for name in ('child.pid','grandchild.pid'):
                    self.assertFalse(ps.owner_running({'status':'running','owner_pid':int((root/name).read_text())}))
            finally:
                if owner.poll() is None:
                    owner.terminate()
                    owner.wait(timeout=5)
                if (root/'wrapper.pid').exists():
                    subprocess.run(['taskkill','/F','/T','/PID',(root/'wrapper.pid').read_text()],capture_output=True,timeout=10)

    def test_access_denied_uses_creation_identity_and_rejects_pid_reuse(self):
        kernel = MagicMock()
        kernel.OpenProcess.return_value = 0
        run = {'status':'running','owner_pid':123,'owner_created_at':'2026-09-16T20:59:15.859219'}
        with patch.object(ctypes,'WinDLL',return_value=kernel), patch.object(ctypes,'get_last_error',return_value=5), patch.object(ps,'cim_process_creation_time',return_value='2026-09-16T20:59:15.859218'):
            self.assertTrue(ps.owner_running(run))
        for created in (None, '2026-09-16T20:59:16.859218'):
            with self.subTest(created=created), patch.object(ctypes,'WinDLL',return_value=kernel), patch.object(ctypes,'get_last_error',return_value=5), patch.object(ps,'cim_process_creation_time',return_value=created):
                self.assertFalse(ps.owner_running(run))

    def test_missing_process_does_not_query_cim(self):
        kernel = MagicMock()
        kernel.OpenProcess.return_value = 0
        with patch.object(ctypes,'WinDLL',return_value=kernel), patch.object(ctypes,'get_last_error',return_value=87), patch.object(ps,'cim_process_creation_time') as cim:
            self.assertFalse(ps.owner_running({'status':'running','owner_pid':123}))
            cim.assert_not_called()

    def test_real_cim_identity_matches_native_handle(self):
        actual = ps.cim_process_creation_time(os.getpid())
        native = ps.process_creation_time(os.getpid())
        self.assertTrue(ps.owner_creation_matches({'owner_created_at':native}, actual))

    def test_cim_failure_is_unknown_not_dead(self):
        kernel = MagicMock()
        kernel.OpenProcess.return_value = 0
        with patch.object(ctypes,'WinDLL',return_value=kernel), patch.object(ctypes,'get_last_error',return_value=5), patch.object(ps,'cim_process_creation_time',side_effect=RuntimeError('CIM unavailable')):
            with self.assertRaisesRegex(RuntimeError,'CIM unavailable'):
                ps.owner_running({'status':'running','owner_pid':123})
