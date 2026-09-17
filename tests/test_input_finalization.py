from contextlib import contextmanager
from datetime import date, timedelta
import copy
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import pipeline_state as ps
import yfinance_batch as yfb
import market_screen_runner as msr


class InputFinalizationTests(unittest.TestCase):
    def test_canonical_digest_changes_when_volume_changes_with_same_dates_and_counts(self):
        @contextmanager
        def cursor():
            result = MagicMock()
            result.fetchall.side_effect = [
                [{'Date':date(2026,9,16)-timedelta(days=index)} for index in range(30)],
                [{'Ticker':'1101','Date':date(2026,9,16),'Volume':volume}],
                [{'ticker':'1101','company':'台泥','industry':'水泥工業'}]]
            yield result
        import db_client as db
        volume = 17554875
        with patch.object(db,'get_cursor',cursor):
            previous = ps.canonical_inputs_hash('2026-09-16')
            self.assertEqual(previous,ps.canonical_inputs_hash('2026-09-16'))
            volume = 18247875
            self.assertNotEqual(previous,ps.canonical_inputs_hash('2026-09-16'))

    def test_finalization_requires_identity_and_cannot_repeat(self):
        for run in ({'nightly_id':'n1','status':'failed'},
                    {'nightly_id':'old','status':'running'},
                    {'nightly_id':'n1','status':'running','inputs_finalized_at':'already'}):
            with patch.object(ps,'read_json',return_value=run), patch.dict(ps.os.environ,{'TW_NIGHTLY_ID':'n1'}), self.assertRaises(ValueError):
                ps.finalize_inputs()

    def test_finalization_keeps_uuid_and_date_but_freezes_refreshed_picks(self):
        run = {'nightly_id':'n1','status':'running','data_date':'2026-09-16','source_hashes':{'a':'sha'},
               'render_tickers':['1101'],'run_id':17,'picks':['earlier']}
        snapshot = {'data_date':'2026-09-16','render_tickers':['1101'],'run_id':17,'picks':['refreshed']}
        with patch.object(ps,'read_json',side_effect=[copy.deepcopy(run), {}, {}]), patch.object(ps.Path,'is_file',return_value=False), patch.dict(ps.os.environ,{'TW_NIGHTLY_ID':'n1'}), patch.object(ps,'source_hashes',return_value={'a':'sha'}), patch.object(ps,'validate_maintenance_fetch'), patch.object(ps,'validate_finance_fetch'), patch.object(ps,'db_snapshot',return_value=snapshot), patch.object(ps,'canonical_inputs_hash',return_value='canonical-sha'), patch.object(ps,'atomic_json') as write:
            finalized = ps.finalize_inputs()
        self.assertEqual(finalized['nightly_id'],'n1')
        self.assertEqual(finalized['data_date'],'2026-09-16')
        self.assertEqual(finalized['picks'],['refreshed'])
        self.assertEqual(finalized['canonical_inputs_sha256'],'canonical-sha')
        write.assert_called_once()

    def test_daily_force_fetch_ignores_previous_evening_fresh_cache(self):
        fake_yf = MagicMock()
        fake_yf.Ticker.return_value.info = {'symbol':'2330.TW','marketCap':1000,'returnOnEquity':.1}
        with patch.dict(yfb._market_map,{'2330':'.TW'},clear=True), patch.object(yfb.cm,'get_fresh',return_value={'data':{'marketCap':1}}), patch.object(yfb,'is_dead',return_value=False), patch.object(yfb,'_jitter'), patch.object(yfb,'_mark_success'), patch.object(yfb.cm,'put') as put, patch.dict(sys.modules,{'yfinance':fake_yf}):
            self.assertEqual(yfb._fetch_one_with_fallback('2330')['marketCap'],1)
            self.assertEqual(yfb._fetch_one_with_fallback('2330',force=True)['marketCap'],1000)
        fake_yf.Ticker.assert_called_once()
        self.assertEqual(put.call_count,2)

    def test_screener_refresh_keeps_metadata_gate(self):
        with patch.object(sys,'argv',['runner','--data-date','2026-09-16','--refresh-existing']), patch.object(msr,'is_trading_day',return_value=True), patch.object(msr,'get_verified_data_date',return_value=(date(2026,9,16),1949)), patch.object(msr,'has_metadata_marker',return_value=False), patch.object(msr.ms,'screen_market') as screen:
            self.assertEqual(msr.run(),1)
        screen.assert_not_called()

    def test_screener_refresh_recomputes_an_existing_complete_run(self):
        conn = MagicMock()
        conn.cursor.return_value.fetchone.return_value = (24,24)
        with patch.object(sys,'argv',['runner','--data-date','2026-09-16','--refresh-existing']), patch.object(msr,'is_trading_day',return_value=True), patch.object(msr,'get_verified_data_date',return_value=(date(2026,9,16),1949)), patch.object(msr,'has_metadata_marker',return_value=True), patch.object(msr,'has_complete_run_for_data_date',return_value=(17,True,[])), patch.object(msr.ms,'screen_market',return_value={}) as screen, patch.object(msr,'validate_result',return_value=(True,'24 picks')), patch.object(msr,'persist_atomic',return_value=(17,0)), patch.object(msr,'generate_artifacts',return_value=([],[])), patch.object(msr.pymysql,'connect',return_value=conn):
            self.assertEqual(msr.run(),0)
        screen.assert_called_once()


if __name__ == '__main__':
    unittest.main()
