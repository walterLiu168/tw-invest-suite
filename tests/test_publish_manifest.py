#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
test_publish_manifest.py - D054 fixup
Unit tests for publish_manifest.py (happy path + failure paths).

Run:
    cd C:\Users\icemo\Projects\tw-invest-suite
    python -m unittest tests.test_publish_manifest -v
"""
import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

REPO = Path(r"C:\Users\icemo\Projects\tw-invest-suite")
TESTS_DIR = REPO / "tests"
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(TESTS_DIR))

# Make tests pass from either repo root or tests/ dir
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

# Clear any cached import of publish_manifest from a different working dir
for mod in list(sys.modules.keys()):
    if "publish_manifest" in mod:
        del sys.modules[mod]

import publish_manifest as pm  # noqa: E402


class TestBuildManifestHappy(unittest.TestCase):
    """Test build_manifest with valid data — uses real 9/8 data."""

    def test_build_manifest_9_8(self):
        m = pm.build_manifest("2026-09-08")
        self.assertEqual(m["data_date"], "2026-09-08")
        self.assertEqual(m["picks_count"], 24)
        self.assertEqual(len(m["tickers"]), 24)
        self.assertEqual(sum(m["bucket_counts"].values()), 24)
        self.assertEqual(set(m["bucket_counts"].values()), {6})  # 4 buckets * 6
        # source commit full SHA (40 chars)
        self.assertEqual(len(m["source_commit"]), 40)
        # published_commit starts as None
        self.assertIsNone(m["published_commit"])
        # generated_at populated
        self.assertIsNotNone(m["generated_at"])
        # artifacts: 6 paths, all with full SHA-256 (64 chars)
        self.assertEqual(len(m["artifacts"]), 6)
        for art in m["artifacts"]:
            self.assertTrue(art["exists"], f"artifact missing: {art['gh_path']}")
            self.assertEqual(len(art["sha256"]), 64, f"non-full SHA-256: {art['gh_path']}")

    def test_picks_list_format(self):
        m = pm.build_manifest("2026-09-08")
        # Each pick has ticker, name, bucket, industry, status
        for p in m["tickers"]:
            self.assertIn("ticker", p)
            self.assertIn("name", p)
            self.assertIn("bucket", p)
            self.assertIn("industry", p)
            self.assertIn("status", p)
            self.assertEqual(len(p["ticker"]), 4)  # all 4-digit TWSE

    def test_4_buckets_present(self):
        m = pm.build_manifest("2026-09-08")
        expected = {"<100", "100-300", "300-1000", ">1000"}
        self.assertEqual(set(m["bucket_counts"].keys()), expected)


class TestBuildManifestFailures(unittest.TestCase):
    """Test build_manifest with bad data — must raise ValueError."""

    def test_no_market_screen_run(self):
        with self.assertRaises(ValueError) as ctx:
            pm.build_manifest("2020-01-01")
        self.assertIn("no market_screen_runs", str(ctx.exception))

    def test_wrong_picks_count(self):
        """Mock DB to return picks_count=12 — must raise."""
        fake_row = (99, 12)  # run_id=99, picks_count=12
        with patch("publish_manifest.fetch_picks") as mock_fetch:
            mock_fetch.return_value = (99, 12, {"<100": 3, "100-300": 3, "300-1000": 3, ">1000": 3}, [])
            with self.assertRaises(ValueError) as ctx:
                pm.build_manifest("2099-01-01")
            self.assertIn("picks_count=12", str(ctx.exception))
            self.assertIn("expected 24", str(ctx.exception))

    def test_wrong_bucket_sum(self):
        """Mock DB to return bucket sum != 24 — must raise."""
        with patch("publish_manifest.fetch_picks") as mock_fetch:
            mock_fetch.return_value = (
                99, 24,
                {"<100": 5, "100-300": 5, "300-1000": 5, ">1000": 5},
                [{"ticker": f"{1000+i}", "name": "X", "bucket": "<100", "industry": "Y", "status": "active"} for i in range(24)]
            )
            with patch("publish_manifest.artifacts_for") as mock_art:
                mock_art.return_value = [
                    {"gh_path": "x.html", "abs_path": "X", "exists": True, "sha256": "0"*64, "size": 0}
                ]
                with self.assertRaises(ValueError) as ctx:
                    pm.build_manifest("2099-01-01")
                self.assertIn("bucket sum=20", str(ctx.exception))

    def test_missing_artifact_files(self):
        """Mock artifacts list to have missing files — must raise."""
        with patch("publish_manifest.fetch_picks") as mock_fetch:
            mock_fetch.return_value = (
                99, 24,
                {"<100": 6, "100-300": 6, "300-1000": 6, ">1000": 6},
                [{"ticker": f"{1000+i}", "name": "X", "bucket": "<100", "industry": "Y", "status": "active"} for i in range(24)]
            )
            with patch("publish_manifest.artifacts_for") as mock_art:
                mock_art.return_value = [
                    {"gh_path": "missing.html", "abs_path": "X", "exists": False, "sha256": None, "size": 0}
                ]
                with self.assertRaises(ValueError) as ctx:
                    pm.build_manifest("2099-01-01")
                self.assertIn("missing artifacts", str(ctx.exception))


class TestWriteManifest(unittest.TestCase):
    """Test write_manifest creates valid JSON file."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="d054test_"))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_write_manifest_creates_file(self):
        out = self.tmpdir / "publish_manifest_2026-09-08.json"
        m = pm.write_manifest("2026-09-08", out)
        self.assertTrue(out.exists())
        # Round-trip parse
        parsed = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(parsed["data_date"], "2026-09-08")
        self.assertEqual(parsed["picks_count"], m["picks_count"])
        self.assertEqual(parsed["run_id"], m["run_id"])

    def test_write_manifest_creates_parent_dirs(self):
        nested = self.tmpdir / "a" / "b" / "c" / "manifest.json"
        m = pm.write_manifest("2026-09-08", nested)
        self.assertTrue(nested.exists())


class TestVerifyManifestAgainstLocal(unittest.TestCase):
    """Test strict local re-verification."""

    def test_valid_manifest_passes(self):
        m = pm.build_manifest("2026-09-08")
        ok, errs = pm.verify_manifest_against_local(m)
        self.assertTrue(ok, f"errors: {errs}")
        self.assertEqual(errs, [])

    def test_wrong_picks_count_detected(self):
        m = pm.build_manifest("2026-09-08")
        m["picks_count"] = 23  # tamper
        ok, errs = pm.verify_manifest_against_local(m)
        self.assertFalse(ok)
        self.assertTrue(any("picks_count" in e for e in errs))

    def test_wrong_bucket_counts_detected(self):
        m = pm.build_manifest("2026-09-08")
        m["bucket_counts"]["<100"] = 5  # tamper
        ok, errs = pm.verify_manifest_against_local(m)
        self.assertFalse(ok)
        self.assertTrue(any("bucket" in e for e in errs))

    def test_tampered_artifact_hash_detected(self):
        m = pm.build_manifest("2026-09-08")
        m["artifacts"][0]["sha256"] = "0" * 64  # fake hash
        ok, errs = pm.verify_manifest_against_local(m)
        self.assertFalse(ok)
        self.assertTrue(any("SHA mismatch" in e for e in errs))

    def test_short_source_commit_rejected(self):
        m = pm.build_manifest("2026-09-08")
        m["source_commit"] = "abc123"  # too short
        ok, errs = pm.verify_manifest_against_local(m)
        self.assertFalse(ok)
        self.assertTrue(any("source_commit" in e for e in errs))

    def test_wrong_tickers_count_detected(self):
        m = pm.build_manifest("2026-09-08")
        m["tickers"] = m["tickers"][:23]  # remove one
        ok, errs = pm.verify_manifest_against_local(m)
        self.assertFalse(ok)
        self.assertTrue(any("tickers" in e for e in errs))


class TestGitHeadCommitted(unittest.TestCase):
    """Test source_commit_committed flag (D054 contract: no uncommitted runtime copy)."""

    def test_clean_tree_via_mock(self):
        """Mock git status to return empty (clean tracked tree)."""
        with patch("publish_manifest.subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = ""  # empty = clean
            mock_run.return_value = mock_proc
            self.assertTrue(pm.git_head_committed())

    def test_dirty_tree_via_mock(self):
        """Mock git status to return 'M file' (uncommitted tracked change)."""
        with patch("publish_manifest.subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 0
            mock_proc.stdout = " M scripts/run_daily.ps1\n"
            mock_run.return_value = mock_proc
            self.assertFalse(pm.git_head_committed())

    def test_git_fails_returns_false(self):
        """Mock git command failing."""
        with patch("publish_manifest.subprocess.run") as mock_run:
            mock_proc = MagicMock()
            mock_proc.returncode = 1
            mock_proc.stdout = ""
            mock_run.return_value = mock_proc
            self.assertFalse(pm.git_head_committed())


class TestMainCLI(unittest.TestCase):
    """Test the main() CLI (uses sys.argv)."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="d054test_cli_"))
        self._old_argv = sys.argv

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)
        sys.argv = self._old_argv

    def test_cli_builds_manifest(self):
        out = self.tmpdir / "m.json"
        sys.argv = ["publish_manifest.py", "--date", "2026-09-08", "--write-to", str(out)]
        rc = pm.main()
        self.assertEqual(rc, 0)
        self.assertTrue(out.exists())

    def test_cli_verify_only_existing(self):
        out = self.tmpdir / "m.json"
        pm.write_manifest("2026-09-08", out)
        sys.argv = ["publish_manifest.py", "--date", "2026-09-08", "--write-to", str(out), "--verify-only"]
        rc = pm.main()
        self.assertEqual(rc, 0)

    def test_cli_verify_only_missing_returns_1(self):
        out = self.tmpdir / "missing.json"
        sys.argv = ["publish_manifest.py", "--date", "2026-09-08", "--write-to", str(out), "--verify-only"]
        rc = pm.main()
        self.assertEqual(rc, 1)


# Standalone entry point
if __name__ == "__main__":
    unittest.main()
