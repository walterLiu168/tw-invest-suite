from contextlib import nullcontext
from datetime import date
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import finmind_batch as fm
import yfinance_batch as yf
import yfinance_daily as daily
import pipeline_state as ps
import cross_source_runner as csr


class ValuationSourceTests(unittest.TestCase):
    def test_market_suffixes_and_preferred_security_code_are_preserved(self):
        today=date.today().isoformat()
        rows=[dict(stock_id=ticker,date=today,type=venue) for ticker,venue in
              [('2330','twse'),('1584','tpex'),('3293','tpex'),('2881A','twse')]]
        with patch.dict(yf._market_map,{},clear=True):
            yf.refresh_market_map(rows)
            self.assertEqual([yf._format_ticker_yf(t) for t in ('2330','1584','3293','2881A')],
                             ['2330.TW','1584.TWO','3293.TWO','2881A.TW'])
            self.assertEqual(yf._format_ticker_back('1584.TWO'),'1584')
            with self.assertRaises(ValueError):
                yf._format_ticker_yf('9999')

    def test_metadata_conflict_and_staleness_fail_closed(self):
        today=date.today().isoformat()
        for rows in ([dict(stock_id='2330',date='2000-01-01',type='twse')],
                     [dict(stock_id='2330',date=today,type=v) for v in ('twse','tpex')]):
            with self.assertRaises((ValueError,RuntimeError)):
                yf.refresh_market_map(rows)

    def test_market_per_exact_source_snapshot_is_read_back_from_real_cache(self):
        rows=[dict(stock_id='2330',date='2026-09-16',PER=27.59,PBR=9.59,dividend_yield=.92)]
        with tempfile.TemporaryDirectory() as folder, patch.object(fm.cm,'CACHE_DIR',Path(folder)), patch.object(fm,'_call',return_value=rows):
            result=fm.refresh_market_pe('2026-09-16',['2330'])
            self.assertEqual(result['mismatches'],0)
            self.assertEqual(fm.cm.get_fresh('2330','finmind_pe')['data'],rows[0])

    def test_market_per_rejects_empty_wrong_date_duplicate_and_nonfinite_before_write(self):
        valid=dict(stock_id='2330',date='2026-09-16',PER=27.59,PBR=9.59,dividend_yield=.92)
        for rows in ([],[dict(valid,date='2026-09-15')],[valid,valid],[dict(valid,PER=float('nan'))]):
            with patch.object(fm,'_call',return_value=rows), patch.object(fm.cm,'put') as put, self.assertRaises((ValueError,RuntimeError)):
                fm.refresh_market_pe('2026-09-16',['2330'])
            put.assert_not_called()

    def test_old_or_wrong_symbol_cache_does_not_prove_valuation_ready(self):
        with patch.dict(yf._market_map,{'1584':'.TWO'},clear=True):
            for fetched,symbol in (('2026-09-15T22:34:00','1584.TWO'),('2026-09-17T16:00:00','1584.TW'),
                                   ('2099-01-01T00:00:00','1584.TWO')):
                entry={'fetched_at':fetched,'data':{'_source':'yfinance','_symbol':symbol,'marketCap':1000}}
                with patch.object(daily.cache,'get_fresh',return_value=entry):
                    self.assertEqual(daily.cache_coverage(['1584'],'2026-09-16')['fresh_tickers'],0)

    def test_scheduled_duplicate_reuses_verified_cache_and_keeps_nightly_receipt_identity(self):
        tickers=[str(value) for value in range(1100,3000)]
        mapped={ticker:'.TW' for ticker in tickers}
        def fresh(ticker,key):
            return {'fetched_at':'2026-09-17T16:00:00','data':{'_source':'yfinance','_symbol':ticker+'.TW','marketCap':1000}}
        with patch.object(daily,'valuation_lock',return_value=nullcontext()), patch.object(yf,'refresh_market_map'), patch.dict(yf._market_map,mapped,clear=True), patch.object(daily.cache,'get_fresh',side_effect=fresh), patch.object(yf,'batch_fetch') as fetch, patch.object(ps,'atomic_json') as write, patch.dict(daily.os.environ,{'TW_NIGHTLY_ID':'n1'}):
            self.assertEqual(daily.refresh(tickers,'2026-09-16'),0)
        fetch.assert_not_called()
        self.assertEqual(write.call_args.args[1]['nightly_id'],'n1')
        self.assertEqual(write.call_args.args[0].name,'finance_fetch.json')

    def test_expired_weekend_quote_still_uses_valid_periodic_roe_without_api(self):
        def fresh(ticker,key):
            return {'data':{'returnOnEquity':.1,'_symbol':'2330.TW'}} if key=='yfinance_roe' else None
        with patch.object(csr,'_db_basic',return_value={'ticker':'2330'}), patch.object(csr.cm,'get_fresh',side_effect=fresh), patch.object(csr.fmb,'fetch_pe') as api:
            data=csr.assemble('2330',use_yfinance=False,fetch_news=False,cache_only=True)
        self.assertEqual(data['yfinance']['returnOnEquity'],.1)
        self.assertIsNone(data.get('valuation',{}).get('pe'))
        api.assert_not_called()


if __name__=='__main__':
    unittest.main()
