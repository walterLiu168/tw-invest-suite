"""Execute the endpoint SQL against dated fixtures; do not infer correctness from counts."""
from contextlib import contextmanager, redirect_stdout
from io import StringIO
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import db_client as db
import market_screen as ms


class ReturnEndpointTests(unittest.TestCase):
    def test_actual_sql_excludes_future_zero_prices_and_preserves_missing_history(self):
        connection = sqlite3.connect(':memory:')
        connection.row_factory = sqlite3.Row
        connection.execute('CREATE TABLE daily_data2_full (Ticker TEXT, Date TEXT, Close REAL)')
        connection.executemany('INSERT INTO daily_data2_full VALUES (?,?,?)', [
            ('2330','2026-09-17',100), ('2330','2026-09-18',1000),
            ('2330','2026-08-27',80), ('2330','2026-08-28',0), ('2330','2026-08-29',5000),
            ('2330','2026-07-18',50), ('2330','2026-05-19',40), ('2330','2026-01-19',25),
            ('1452','2026-09-17',200), ('1452','2026-08-29',100),
        ])
        class Cursor:
            def execute(self, sql, params):
                self.cursor = connection.execute(sql.replace('%s','?'), params)
            def fetchall(self):
                return [dict(row) for row in self.cursor.fetchall()]
        @contextmanager
        def cursor():
            yield Cursor()
        try:
            with patch.object(db,'get_cursor',cursor):
                result = db.long_term_returns_batch(['2330','1452','missing'],'2026-09-17')
            self.assertEqual(result['2330'],{'ret_20d':0.25,'ret_60d':1.0,'ret_120d':1.5,'ret_240d':3.0})
            self.assertEqual(result['1452'],{})
            self.assertEqual(result['missing'],{})
        finally:
            connection.close()

    def test_long_ranking_receives_returns_for_every_candidate_before_selection(self):
        snapshot = [{'Ticker':str(1100+n),'Close':150,'Volume':200000,'SharesOutstanding_shares':1000000} for n in range(4)]
        returns = {str(1100+n):{'ret_240d':value} for n,value in enumerate((-1,0.5,0.3,0.2))}
        with patch.object(ms.db,'market_snapshot',return_value=snapshot), \
             patch.object(ms.db,'all_industries',return_value={}), \
             patch.object(ms.db,'all_shares_outstanding',return_value={}), \
             patch.object(ms.db,'latest_date',return_value='2026-09-17'), \
             patch.object(ms.db,'all_latest_chipscore',return_value={}), \
             patch.object(ms.db,'all_latest_features',return_value={}), \
             patch.object(ms.db,'long_term_returns_batch',return_value=returns) as loaded, \
             patch.object(ms,'enrich_news_for_picks'), patch.object(ms.zen,'analyze',side_effect=ValueError('fixture')), \
             redirect_stdout(StringIO()):
            result = ms.screen_market()
        loaded.assert_called_once_with(['1100','1101','1102','1103'],'2026-09-17')
        self.assertEqual([c.ticker for c in result['100-300']['long']],['1101','1102','1103'])
        self.assertTrue(all(c.horizon=='long' for c in result['100-300']['long']))
        self.assertTrue(all(c.horizon=='short' for c in result['100-300']['short']))
        long_b = next(c for c in result['100-300']['long'] if c.ticker=='1101')
        short_b = next(c for c in result['100-300']['short'] if c.ticker=='1101')
        self.assertIsNot(long_b,short_b)


if __name__ == '__main__':
    unittest.main()
