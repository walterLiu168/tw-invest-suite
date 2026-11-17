"""Contract tests for the mutual-exclusion change in the market screen."""
import sys
from dataclasses import dataclass
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import market_screen as ms  # noqa: E402


@dataclass
class FakeCandidate:
    """Only the fields the selection glue touches."""

    ticker: str
    long_score: float = 0.0
    short_score: float = 0.0
    score: object = None
    score_details: object = None
    horizon: str = ''
    market_cap: float = 1_000_000_000
    excess_return_240d: float = 0.10
    excess_return_120d: float = 0.05
    excess_return_60d: float = 0.02


def _stub_scores(long_map, short_map):
    def long_term_score(candidates):
        return {c.ticker: long_map[c.ticker] for c in candidates}

    def short_term_score(c):
        return short_map[c.ticker]

    return long_term_score, short_term_score


class MutualExclusionTests(unittest.TestCase):
    def test_a_name_that_tops_both_rankings_is_kept_only_once(self):
        cands = [FakeCandidate('A', 90, 10), FakeCandidate('B', 80, 9),
                 FakeCandidate('C', 70, 8), FakeCandidate('D', 60, 7),
                 FakeCandidate('E', 50, 6), FakeCandidate('F', 40, 5)]
        long_map = {c.ticker: c.long_score for c in cands}
        short_map = {c.ticker: c.short_score for c in cands}
        with patch.object(ms, 'long_term_score', _stub_scores(long_map, short_map)[0]), \
                patch.object(ms, 'short_term_score', _stub_scores(long_map, short_map)[1]):
            longs, shorts, reused = ms.pick_horizons(cands, 3)
        self.assertEqual([c.ticker for c in longs], ['A', 'B', 'C'])
        # A tops both rankings; the short list must take the next best instead.
        self.assertEqual([c.ticker for c in shorts], ['D', 'E', 'F'])
        self.assertEqual(reused, [])
        self.assertEqual(len({c.ticker for c in longs} | {c.ticker for c in shorts}), 6)

    def test_short_picks_keep_their_own_score(self):
        cands = [FakeCandidate('A', 90, 10), FakeCandidate('B', 80, 9),
                 FakeCandidate('C', 70, 8), FakeCandidate('D', 60, 7),
                 FakeCandidate('E', 50, 6), FakeCandidate('F', 40, 5)]
        long_map = {c.ticker: c.long_score for c in cands}
        short_map = {c.ticker: c.short_score for c in cands}
        with patch.object(ms, 'long_term_score', _stub_scores(long_map, short_map)[0]), \
                patch.object(ms, 'short_term_score', _stub_scores(long_map, short_map)[1]):
            longs, shorts, _ = ms.pick_horizons(cands, 3)
        self.assertEqual(longs[0].score, 90)
        self.assertEqual(shorts[0].score, 7)   # D's short score, not a long score

    def test_a_bucket_without_enough_distinct_names_keeps_the_slot_count(self):
        # only four distinct names, three slots per horizon
        cands = [FakeCandidate('A', 90, 10), FakeCandidate('B', 80, 9),
                 FakeCandidate('C', 70, 8), FakeCandidate('D', 60, 7)]
        long_map = {c.ticker: c.long_score for c in cands}
        short_map = {c.ticker: c.short_score for c in cands}
        with patch.object(ms, 'long_term_score', _stub_scores(long_map, short_map)[0]), \
                patch.object(ms, 'short_term_score', _stub_scores(long_map, short_map)[1]):
            longs, shorts, reused = ms.pick_horizons(cands, 3)
        self.assertEqual(len(longs), 3)
        self.assertEqual(len(shorts), 3)
        self.assertEqual(len(reused), 2)
        # the long ranking was A(90) > B(80) > C(70); the lowest ranked slots
        # are given back first, so C then B.
        self.assertEqual(reused, ['C', 'B'])

    def test_every_bucket_yields_three_long_and_three_short(self):
        cands = [FakeCandidate(f'T{i}', 100 - i, 100 - i) for i in range(12)]
        long_map = {c.ticker: c.long_score for c in cands}
        short_map = {c.ticker: c.short_score for c in cands}
        with patch.object(ms, 'long_term_score', _stub_scores(long_map, short_map)[0]), \
                patch.object(ms, 'short_term_score', _stub_scores(long_map, short_map)[1]):
            longs, shorts, reused = ms.pick_horizons(cands, 3)
        self.assertEqual(len(longs), 3)
        self.assertEqual(len(shorts), 3)
        self.assertEqual(reused, [])
        self.assertFalse({c.ticker for c in longs} & {c.ticker for c in shorts})


if __name__ == '__main__':
    unittest.main()
