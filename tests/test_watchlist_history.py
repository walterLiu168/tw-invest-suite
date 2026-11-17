"""Contracts for the watchlist history document and its page."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'scripts')]
import watchlist_history as wh
import pipeline_state as ps


class FakeCursor:
    """Answers the three queries build_history() issues, in order."""

    def __init__(self, runs, picks, closes):
        self._results = [runs, picks, closes]
        self._last = None

    def execute(self, sql, params=()):
        self._last = self._results.pop(0) if self._results else []

    def fetchall(self):
        return self._last

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConn:
    """Stands in for db.get_cursor(), which is a context manager over a cursor."""

    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self._cursor

    def __exit__(self, *exc):
        return False


def _pick(run_id, ticker, **extra):
    row = {
        'id': run_id * 100 + len(str(ticker)), 'run_id': run_id, 'ticker': ticker,
        'name': extra.get('name', '測試名'), 'industry': extra.get('industry', '測試業'),
        'horizon': 'long', 'bucket': '100-300', 'close_at_pick': 100.0,
        'change_pct': 1.0, 'volume': 1000, 'market_cap': 1e9,
        'excess_return_60d': 1.5, 'excess_return_240d': 4.5, 'score': 88,
        'rationale': '**級別**：日 K **方向**：偏多', 'status': 'active',
    }
    row.update(extra)
    return row


class WatchlistHistoryTests(unittest.TestCase):
    def test_rationale_is_split_into_labelled_facts(self):
        facts = wh.parse_rationale('**級別**：日 K **方向**：偏多 **失效條件**：若收盤跌破失效')
        self.assertEqual(facts['級別'], '日 K')
        self.assertEqual(facts['方向'], '偏多')
        self.assertEqual(facts['失效條件'], '若收盤跌破失效')
        self.assertIsNone(wh.parse_rationale(None))
        self.assertEqual(wh.parse_rationale('沒有標籤的純文字'), {'說明': '沒有標籤的純文字'})

    def test_duplicate_pick_rows_are_not_counted_twice(self):
        runs = [
            {'id': 1, 'run_date': '2026-11-02', 'picks_count': 24},
            {'id': 2, 'run_date': '2026-11-03', 'picks_count': 24},
        ]
        picks = [
            _pick(1, '2330'), _pick(1, '2330'),   # same name twice in one run
            _pick(1, '2454'),
            _pick(2, '2330'), _pick(2, '9999'),
        ]
        closes = [
            {'ticker': '2330', 'trade_date': '2026-11-02', 'close': 100.0},
            {'ticker': '2330', 'trade_date': '2026-11-03', 'close': 110.0},
        ]
        cursor = FakeCursor(runs, picks, closes)
        with patch.object(wh.db, 'get_cursor', return_value=FakeConn(cursor)), \
                patch.object(wh.db, 'all_industries', return_value={}):
            history = wh.build_history()
        self.assertEqual(history['tickers']['2330']['appearances'], 2)
        self.assertEqual(len(history['tickers']['2330']['entries']), 2)
        self.assertEqual(history['duplicate_pick_rows'], {'2026-11-02': ['2330']})
        self.assertEqual(history['current']['date'], '2026-11-03')
        self.assertTrue(history['tickers']['2330']['in_current'])
        self.assertFalse(history['tickers']['2454']['in_current'])
        self.assertTrue(history['tickers']['9999']['in_current'])
        self.assertEqual(history['tickers']['2330']['path'][0][2], 0.0)
        self.assertAlmostEqual(history['tickers']['2330']['path'][1][2], 0.1, places=6)

    def test_document_carries_the_nightly_identity_and_is_compact(self):
        history = {'runs': 1, 'dates': ['2026-11-03'], 'current': {}, 'tickers': {}}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'watchlist-history.json'
            payload = wh.write_json(history, path, '2026-11-03', 'nightly-1')
            self.assertEqual(payload['date'], '2026-11-03')
            self.assertEqual(payload['nightly_id'], 'nightly-1')
            raw = path.read_text(encoding='utf-8')
            self.assertNotIn('\n', raw.strip(), 'history document must be compact')
            self.assertEqual(json.loads(raw)['source'], wh.SOURCE)

    def test_certified_artifact_set_includes_the_history_outputs(self):
        expected = ps.REPORT_FRONTEND_FILES
        self.assertIn('watchlist-history.html', expected)
        source = (ROOT / 'src' / 'all_reports.py').read_text(encoding='utf-8')
        self.assertIn("'data/watchlist-history.json'", source)
        self.assertIn('watchlist_history.write_json', source)

    def test_history_page_fetches_the_document_and_links_back(self):
        page = (ROOT / 'public' / 'watchlist-history.html').read_text(encoding='utf-8')
        self.assertIn('data/watchlist-history.json', page)
        self.assertIn('?ticker=', page)
        renderer = (ROOT / 'scripts' / 'render_full_watchlist.py').read_text(encoding='utf-8')
        self.assertIn('watchlist-history.html?ticker=', renderer)

    def test_history_link_sits_on_the_curated_card_not_the_margin_tab(self):
        """The margin rebound tab is a different population with no pick history.

        Linking it would produce dead links for names that never entered
        market_screen_picks, and would leave the curated picks without one.
        """
        source = (ROOT / 'scripts' / 'render_full_watchlist.py').read_text(encoding='utf-8')
        margin = source.split('def _render_margin_tab', 1)[1]
        curated = source.split('def render_pick_card', 1)[1].split('def ', 1)[0]
        self.assertNotIn('watchlist-history.html', margin)
        self.assertIn('watchlist-history.html?ticker=', curated)

    def test_taiwan_colour_convention_is_kept(self):
        page = (ROOT / 'public' / 'watchlist-history.html').read_text(encoding='utf-8')
        self.assertIn('.up { color: var(--red); }', page)
        self.assertIn('.down { color: var(--green); }', page)


if __name__ == '__main__':
    unittest.main()
