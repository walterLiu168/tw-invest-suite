"""A current screen must not silently reuse historical enrichment tables."""
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import market_screen as ms


class ScreenInputDatesTests(unittest.TestCase):
    def test_enrichment_queries_use_price_session_instead_of_each_table_latest(self):
        with patch.object(ms.db, 'market_snapshot', return_value=[]), \
             patch.object(ms.db, 'all_industries', return_value={}), \
             patch.object(ms.db, 'all_shares_outstanding', return_value={}), \
             patch.object(ms.db, 'latest_date', return_value='2026-09-17'), \
             patch.object(ms.db, 'all_latest_chipscore', return_value={}) as chips, \
             patch.object(ms.db, 'all_latest_features', return_value={}) as features, \
             redirect_stdout(StringIO()):
            ms.screen_market()
        chips.assert_called_once_with('2026-09-17')
        features.assert_called_once_with('2026-09-17')

    def test_absent_current_enrichment_does_not_create_negative_or_old_values(self):
        c = ms.build_candidate({'Ticker':'2330', 'Close':100, 'Volume':12500}, {}, {})
        ms.enrich_from_chip_map(c, {})
        ms.enrich_from_features_map(c, {})
        self.assertIsNone(c.chip_score)
        self.assertIsNone(c.volume_burst)
        self.assertIsNone(c.kd_golden_cross)
        self.assertIsNone(c.excess_return_20d)

    def test_uncomputed_flags_remain_unknown_and_real_zero_is_preserved(self):
        c = ms.build_candidate({'Ticker':'2330','Close':100,'Volume':12500}, {}, {})
        ms.enrich_from_chip_map(c, {'2330':{'ChipScore':0.5,'VolumeBurst':None,'KD_GoldenCross':None}})
        self.assertEqual(c.chip_score,0.5)
        self.assertIsNone(c.volume_burst)
        self.assertIsNone(c.kd_golden_cross)
        ms.enrich_from_chip_map(c, {'2330':{'VolumeBurst':0,'KD_GoldenCross':1}})
        self.assertEqual(c.volume_burst,0)
        self.assertEqual(c.kd_golden_cross,1)


if __name__ == '__main__':
    unittest.main()
