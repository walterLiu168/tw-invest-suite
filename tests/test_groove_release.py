import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sync_groove_release as groove


class GrooveReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "release"
        self.dest = Path(self.temp.name) / "groove"
        self.dest.mkdir()
        self.manifest = {"nightly_id": "n1", "data_date": "2026-09-16", "run_id": 17, "tickers": [], "artifacts": []}
        for relative in ("watchlist.html", "patterns.html", "analyze/index.html", "data/patterns.json", "data/watchlist-full.json", "data/dashboard.md", "data/daily_summary_2026-09-16.md", "data/publish_manifest_2026-09-16.json"):
            p = self.root / relative
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(relative.encode())
            if "dashboard" not in relative and "daily_summary" not in relative and "publish_manifest" not in relative:
                self.manifest["artifacts"].append({"gh_path": relative, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()})
        self.addCleanup(patch.stopall)
        patch.object(groove, "GROOVE", self.dest).start()
        patch.object(groove, "RESULT", self.dest / "receipt.json").start()
        self.remote = patch.object(groove, "verify_paths", return_value=["watchlist.html"]).start()

    def test_exact_copy_retry_preserves_music_files(self):
        music = self.dest / "index.html"
        music.write_bytes(b"music application")
        config = self.dest / "config.yml"
        config.write_bytes(b"existing config")
        groove.deploy(self.root, self.manifest)
        groove.deploy(self.root, self.manifest)
        self.assertEqual(music.read_bytes(), b"music application")
        self.assertEqual(config.read_bytes(), b"existing config")
        for source in self.root.rglob("*"):
            if source.is_file():
                self.assertEqual((self.dest / source.relative_to(self.root)).read_bytes(), source.read_bytes())

    def test_source_mismatch_stops_before_any_copy(self):
        (self.root / "watchlist.html").write_bytes(b"changed")
        with self.assertRaises(ValueError):
            groove.deploy(self.root, self.manifest)
        self.assertFalse((self.dest / "patterns.html").exists())
        self.remote.assert_not_called()

    def test_path_escape_stops_before_any_copy(self):
        self.manifest["artifacts"].append({"gh_path": "../outside", "sha256": "invalid"})
        with self.assertRaises(ValueError):
            groove.deploy(self.root, self.manifest)
        self.assertFalse((self.dest / "patterns.html").exists())

    def test_music_root_cannot_be_a_release_artifact(self):
        (self.root / "index.html").write_bytes(b"stock index")
        self.manifest["artifacts"].append({"gh_path": "index.html", "sha256": hashlib.sha256(b"stock index").hexdigest()})
        with self.assertRaises(ValueError):
            groove.deploy(self.root, self.manifest)
        self.assertFalse((self.dest / "index.html").exists())
