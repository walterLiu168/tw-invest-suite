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
        fetch = {'nightly_id':'n1','requested_date':'2026-09-16','latest_source_date':'2026-09-15','status':'ok','provider_rows':2049,'api_errors':0,'price_refresh_date':'2026-09-16','price_refresh_rows':1949,
                 'canonical_refresh_date':'2026-09-16','canonical_refresh_rows':1949,
                 'canonical_datasets':['price','inst','margin','daytrade','shareholding','shares'],'source_value_mismatches':0,
                 'price_history_sessions':30,'price_history_mismatches':0,
                 'chips_history_sessions':30,'chips_history_mismatches':0,
                 'chips_history_datasets':['inst','margin','daytrade','shareholding','shares'],
                 'valuation_refresh':{'date':'2026-09-16','provider_tickers':1900,'mismatches':0}}
        self.assertEqual(ps.validate_maintenance_fetch(fetch,run),'2026-09-15')
        for day in ('2026-09-14','2026-09-17'):
            with self.subTest(day=day), self.assertRaisesRegex(ValueError,'stale or future'):
                ps.validate_maintenance_fetch({**fetch,'latest_source_date':day},run)
        with self.assertRaisesRegex(ValueError,'does not certify'):
            ps.validate_maintenance_fetch({**fetch,'nightly_id':'old'},run)
        with self.assertRaisesRegex(ValueError,'does not certify'):
            ps.validate_maintenance_fetch({**fetch,'api_errors':1},run)
        for price in ({'price_refresh_date':'2026-09-15'}, {'price_refresh_rows':1899}, {'price_refresh_rows':None}):
            with self.subTest(price=price), self.assertRaisesRegex(ValueError,'price refresh'):
                ps.validate_maintenance_fetch({**fetch,**price},run)
        for canonical in ({'canonical_refresh_date':'2026-09-15'}, {'canonical_refresh_rows':1948},
                          {'canonical_datasets':['price']}, {'source_value_mismatches':1}):
            with self.subTest(canonical=canonical), self.assertRaisesRegex(ValueError,'canonical source'):
                ps.validate_maintenance_fetch({**fetch,**canonical},run)
        for chips in ({'chips_history_sessions':None}, {'chips_history_mismatches':1},
                      {'chips_history_datasets':['inst']}):
            with self.subTest(chips=chips), self.assertRaisesRegex(ValueError,'chips history'):
                ps.validate_maintenance_fetch({**fetch,**chips},run)

    def test_nightly_refresh_uses_normal_single_day_price_writer_without_schema_flag(self):
        output = ''.join(f'SOURCE_VERIFY dataset={name} date=2026-09-16 tickers=1949 mismatch=0\n'
                         for name in ('price','inst','margin','daytrade','shareholding','shares'))
        result = MagicMock(stdout=output+'HISTORY_VERIFY date=2026-09-16 sessions=30 rows=58743 revised=0 mismatch=0\nCHIPS_HISTORY_VERIFY date=2026-09-16 sessions=30 datasets=inst,margin,daytrade,shareholding,shares rows=293715 revised=0 mismatch=0\nDB_VERIFY phase=canonical range=2026-09-16..2026-09-16 expected=1949 complete=1949 missing=0 first_missing=-\n')
        with patch.object(maintenance.Path,'is_file',return_value=True), patch.object(maintenance.subprocess,'run',return_value=result) as run, redirect_stdout(StringIO()):
            self.assertEqual(maintenance.refresh_price_inputs('2026-09-16'),1949)
        command = run.call_args.args[0]
        self.assertIn('--refresh-existing',command)
        self.assertEqual(command[command.index('--phase')+1],'canonical')
        self.assertEqual(command[command.index('--date')+1],'2026-09-16')
        self.assertNotIn('--ensure-state-schema',command)
        self.assertTrue(run.call_args.kwargs['check'])
        self.assertEqual(command[command.index('--refresh-lookback-sessions')+1],'30')
        self.assertEqual(run.call_args.kwargs['timeout'],1050)

    def test_price_only_history_proof_cannot_certify_chips_history(self):
        output = ''.join(f'SOURCE_VERIFY dataset={name} date=2026-09-16 tickers=1949 mismatch=0\n'
                         for name in ('price','inst','margin','daytrade','shareholding','shares'))
        output += ('HISTORY_VERIFY date=2026-09-16 sessions=30 rows=58743 revised=0 mismatch=0\n'
                   'DB_VERIFY phase=canonical range=2026-09-16..2026-09-16 expected=1949 complete=1949 missing=0\n')
        with patch.object(maintenance.Path,'is_file',return_value=True), patch.object(maintenance.subprocess,'run',return_value=MagicMock(stdout=output)), redirect_stdout(StringIO()), self.assertRaisesRegex(RuntimeError,'chips history'):
            maintenance.refresh_price_inputs('2026-09-16')

    def test_nightly_refresh_rejects_stale_or_incomplete_completion_output(self):
        for output in ('DB_VERIFY phase=canonical range=2026-09-15..2026-09-15 expected=1949 complete=1949 missing=0',
                       'DB_VERIFY phase=canonical range=2026-09-16..2026-09-16 expected=1949 complete=1948 missing=1',
                       'DB_VERIFY phase=canonical range=2026-09-16..2026-09-16 expected=1899 complete=1899 missing=0'):
            with patch.object(maintenance.Path,'is_file',return_value=True), patch.object(maintenance.subprocess,'run',return_value=MagicMock(stdout=output)), redirect_stdout(StringIO()), self.assertRaisesRegex(RuntimeError,'complete current market'):
                maintenance.refresh_price_inputs('2026-09-16')

    def test_nightly_refresh_refuses_counts_without_exact_source_values(self):
        output = 'DB_VERIFY phase=canonical range=2026-09-16..2026-09-16 expected=1949 complete=1949 missing=0'
        with patch.object(maintenance.Path,'is_file',return_value=True), patch.object(maintenance.subprocess,'run',return_value=MagicMock(stdout=output)), redirect_stdout(StringIO()), self.assertRaisesRegex(RuntimeError,'exact source/DB'):
            maintenance.refresh_price_inputs('2026-09-16')

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
