from contextlib import contextmanager, redirect_stdout
from datetime import date
import importlib.util
from io import StringIO
from pathlib import Path
import unittest
import sys
from unittest.mock import MagicMock, patch

spec = importlib.util.spec_from_file_location('maintenance_fetch_test', Path(__file__).resolve().parents[1] / 'src/margin_rebound/finmind_maint.py')
maintenance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maintenance)
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import pipeline_state as ps


class MaintenanceFetchTests(unittest.TestCase):
    def test_one_session_source_lag_is_explicit_and_older_or_future_is_rejected(self):
        run = {'nightly_id':'n1','data_date':'2026-09-16'}
        fetch = {'nightly_id':'n1','requested_date':'2026-09-16','latest_source_date':'2026-09-15','status':'ok','provider_rows':2049,'api_errors':0}
        self.assertEqual(ps.validate_maintenance_fetch(fetch,run),'2026-09-15')
        for day in ('2026-09-14','2026-09-17'):
            with self.subTest(day=day), self.assertRaisesRegex(ValueError,'stale or future'):
                ps.validate_maintenance_fetch({**fetch,'latest_source_date':day},run)
        with self.assertRaisesRegex(ValueError,'does not certify'):
            ps.validate_maintenance_fetch({**fetch,'nightly_id':'old'},run)
        with self.assertRaisesRegex(ValueError,'does not certify'):
            ps.validate_maintenance_fetch({**fetch,'api_errors':1},run)

    def test_completion_holds_state_mutex_before_reading_run(self):
        locked = False
        @contextmanager
        def lock():
            nonlocal locked
            locked = True
            try:
                yield
            finally:
                locked = False
        def read(path):
            self.assertTrue(locked)
            raise RuntimeError('stop before artifact processing')
        with patch.object(ps,'state_lock',lock), patch.object(ps,'read_json',side_effect=read), self.assertRaisesRegex(RuntimeError,'stop before'):
            ps.complete('unused')
        self.assertFalse(locked)

    @contextmanager
    def connection(self):
        conn = MagicMock()
        conn.cursor.return_value.fetchone.return_value = (date(2026,9,15),)
        yield conn

    def run_fetch(self, response):
        with patch.object(maintenance,'get_conn',self.connection), patch.object(maintenance,'get_token',return_value='test-only'), patch.object(maintenance.time,'sleep'), patch.dict(maintenance.os.environ,{'TW_DATA_DATE':'2026-09-16'}), patch.object(maintenance.requests,'get',return_value=response) as request:
            result = maintenance.fetch_latest(days_back=0)
        return result, request.call_args.kwargs['params']

    def test_frozen_date_controls_provider_request(self):
        response = MagicMock()
        response.json.return_value = {'status':200,'data':[{'date':'2026-09-16'}]}
        rows, params = self.run_fetch(response)
        self.assertEqual(params['start_date'],'2026-09-16')
        self.assertEqual(rows[0]['date'],'2026-09-16')

    def test_empty_provider_data_cannot_certify_success(self):
        response = MagicMock()
        response.json.return_value = {'status':200,'data':[]}
        with self.assertRaisesRegex(RuntimeError,'No margin provider data'):
            self.run_fetch(response)

    def test_http_failure_cannot_leak_request_url_or_certify_success(self):
        response = MagicMock()
        response.raise_for_status.side_effect = RuntimeError('https://example.test/?token=DO_NOT_PRINT')
        output = StringIO()
        with redirect_stdout(output), self.assertRaisesRegex(RuntimeError,'requests failed'):
            self.run_fetch(response)
        self.assertNotIn('DO_NOT_PRINT', output.getvalue())
