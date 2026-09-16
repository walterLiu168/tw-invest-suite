"""Checks for the scheduled health lane's identity and timezone handling."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import check_openalice_health as h
import nightly_health as nh


class ScheduleHealthTests(unittest.TestCase):
    def test_iso_scheduler_datetime_preserves_instant(self):
        parsed = h.parse_task_last_run('2026-09-16T11:00:00+00:00')
        self.assertEqual(parsed.hour, 19)

    def test_daily_stage_can_run_longer_than_five_minutes(self):
        now = datetime.now(h.TZ)
        with patch.object(nh, 'diagnose', return_value=('healthy', {'status': 'running'}, 'within budget')):
            self.assertEqual(h.running_status({'name': 'tw-invest-suite-daily-report'}, now - timedelta(minutes=60), now), 'RUNNING')

    def test_stale_running_code_cannot_hide_dead_owner(self):
        with patch.object(nh, 'diagnose', return_value=('stuck', {'status': 'running'}, 'dead owner')):
            self.assertEqual(h.running_status({'name': 'tw-invest-suite-daily-report'}, None, datetime.now(h.TZ)), 'STUCK')

    def test_auxiliary_tasks_respect_their_actual_deadline(self):
        now = datetime.now(h.TZ)
        info = {'name': 'OpenAlice RSS Refresh Every 2h', 'limit': 'PT2H'}
        self.assertEqual(h.running_status(info, now - timedelta(minutes=60), now), 'RUNNING')
        self.assertEqual(h.running_status(info, now - timedelta(hours=3), now), 'STUCK')
        info['limit'] = ''
        self.assertEqual(h.running_status(info, now, now), 'UNKNOWN')

    def test_utc_naive_raw_ingestion_has_real_hour_age(self):
        cursor = MagicMock()
        latest = datetime.now(h.TZ).astimezone(h.timezone.utc).replace(tzinfo=None) - timedelta(hours=2, seconds=1)
        cursor.fetchone.return_value = (latest,)
        conn = MagicMock()
        conn.__enter__.return_value.cursor.return_value = cursor
        with patch.object(h, 'get_conn', return_value=conn):
            self.assertEqual(h.db_max_date_hours_behind('digest_source_raw', 'created_at'), 2)

    def test_structured_query_reports_missing_as_unknown(self):
        with patch.object(h.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'denied')):
            result = h.get_task_info('missing')
        self.assertEqual(result['state'], 'UNKNOWN')
        self.assertIsNone(result['result'])

    def test_actual_scheduler_json_is_parseable_and_complete(self):
        result = h.get_task_info('tw-invest-suite-daily-report')
        self.assertIn(result['state'], ('Ready', 'Running'))
        self.assertIsInstance(result['result'], int)
        self.assertIsNotNone(h.parse_task_last_run(result['last_run']))


if __name__ == '__main__':
    unittest.main()
