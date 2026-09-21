"""Credential boundary regression tests for the public source release."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import db_client  # noqa: E402


class DbConfigTests(unittest.TestCase):
    def test_source_config_has_no_password(self):
        self.assertNotIn("password", db_client.DB_CONFIG)

    def test_missing_password_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "TW_DB_PASSWORD"):
                db_client.get_db_config()

    def test_password_is_read_from_environment(self):
        with patch.dict(os.environ, {"TW_DB_PASSWORD": "test-only-secret"}, clear=True):
            config = db_client.get_db_config(connect_timeout=3)
        self.assertEqual(config["password"], "test-only-secret")
        self.assertEqual(config["connect_timeout"], 3)


if __name__ == "__main__":
    unittest.main()
