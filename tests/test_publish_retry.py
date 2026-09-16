"""Identical retries and both final report byte hashes."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import publish_ghpages as publisher


class PublishRetryTests(unittest.TestCase):
    def test_identical_git_commit_is_success_and_change_is_committed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            publisher.initialize_release_git(root)
            publisher.run(["git", "config", "user.name", "fixture"], root)
            publisher.run(["git", "config", "user.email", "fixture@example.invalid"], root)
            (root / "watchlist.html").write_text("certified")
            publisher.run(["git", "add", "-A"], root)
            publisher.commit_if_changed(root, "initial")
            first = publisher.run(["git", "rev-parse", "HEAD"], root)
            publisher.run(["git", "add", "-A"], root)
            publisher.commit_if_changed(root, "identical retry")
            self.assertEqual(publisher.run(["git", "rev-parse", "HEAD"], root), first)
            (root / "watchlist.html").write_text("new certified")
            publisher.run(["git", "add", "-A"], root)
            publisher.commit_if_changed(root, "new release")
            self.assertNotEqual(publisher.run(["git", "rev-parse", "HEAD"], root), first)

    def test_stale_daily_summary_fails_even_when_dashboard_matches(self):
        class QuietHandler(SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "staged"
            served = Path(folder) / "served"
            (root / "data").mkdir(parents=True)
            paths = ["data/dashboard.md", "data/daily_summary_2026-09-16.md"]
            for path in paths:
                (root / path).write_text("current " + path)
            shutil.copytree(root, served)
            server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(served)))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with patch.object(publisher.pm, "GITHUB_PAGES_BASE", f"http://127.0.0.1:{server.server_port}"):
                    self.assertEqual(set(publisher.remote_verify_paths(root, {"nightly_id": "fixture"}, paths)), set(paths))
                    (served / paths[1]).write_text("yesterday")
                    with self.assertRaisesRegex(ValueError, "daily_summary"):
                        publisher.remote_verify_paths(root, {"nightly_id": "fixture"}, paths)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
