"""Contract tests for the long/short overlap handling in the watchlist page."""
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import render_full_watchlist as r  # noqa: E402


class FakePick:
    def __init__(self, ticker, horizon):
        self.ticker = ticker
        self.horizon = horizon


class OverlapSummaryTests(unittest.TestCase):
    def test_repeated_name_is_counted_once_in_the_statistics(self):
        picks = [FakePick('3443', 'long'), FakePick('3443', 'short'),
                 FakePick('2330', 'long'), FakePick('2454', 'short')]
        perf = {'3443': {'ret_since_pick': 0.10},
                '2330': {'ret_since_pick': -0.20},
                '2454': {'ret_since_pick': 0.05}}
        slots, distinct, avg, winrate, repeated = r.summarize_picks(picks, perf)
        self.assertEqual(slots, 4)
        self.assertEqual(distinct, 3)
        self.assertEqual(repeated, ['3443'])
        # counting 3443 twice would give (0.10 - 0.20 + 0.05 + 0.10) / 4 = 0.0125
        self.assertAlmostEqual(avg, (0.10 - 0.20 + 0.05) / 3, places=9)
        self.assertAlmostEqual(winrate, 2 / 3 * 100, places=6)

    def test_no_overlap_keeps_the_plain_counts(self):
        picks = [FakePick('2330', 'long'), FakePick('2454', 'short')]
        perf = {'2330': {'ret_since_pick': 0.10}, '2454': {'ret_since_pick': 0.05}}
        slots, distinct, avg, winrate, repeated = r.summarize_picks(picks, perf)
        self.assertEqual((slots, distinct), (2, 2))
        self.assertEqual(repeated, [])
        self.assertAlmostEqual(avg, 0.075, places=9)
        self.assertAlmostEqual(winrate, 100.0, places=6)

    def test_missing_returns_do_not_break_the_average(self):
        picks = [FakePick('2330', 'long'), FakePick('2454', 'short')]
        perf = {'2330': {'ret_since_pick': 0.10}}
        slots, distinct, avg, winrate, repeated = r.summarize_picks(picks, perf)
        self.assertEqual((slots, distinct), (2, 2))
        self.assertAlmostEqual(avg, 0.10, places=9)

    def test_page_states_the_overlap_instead_of_claiming_24_names(self):
        source = (ROOT / 'scripts' / 'render_full_watchlist.py').read_text(encoding='utf-8')
        self.assertIn('count_label', source)
        self.assertIn('overlap_note', source)
        self.assertIn('名額', source)
        # the fixed "24 檔" claim must be gone from the title and the footer
        self.assertNotIn('<title>台股深度選股 · {today} · 24 檔</title>', source)
        self.assertNotIn('24 檔深度報告', source)


if __name__ == '__main__':
    unittest.main()
