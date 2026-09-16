"""Percentage, source-unit and historical-signal regressions."""
from concurrent.futures import ProcessPoolExecutor
from datetime import date, timedelta
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import db_client as db
import pattern_classifier as pc
import render_ticker_full as rtf
import render_full_watchlist as watchlist
import market_screen as ms
import build_patterns_html as patterns_html
import render_only


class PatternSemanticsTests(unittest.TestCase):
    def test_drawdown_threshold_is_thirty_percent(self):
        row = {"Close": 60, "sma_54": 100}
        for fraction, expected in ((-0.0031, False), (-0.29, False), (-0.30, False), (-0.31, True)):
            self.assertEqual("long_drawdown" in pc._classify_one(row, {"ret_240d": fraction}, {}), expected)

    def test_missing_moving_average_cannot_confirm_trend(self):
        patterns = pc._classify_one({"Close": 100, "rsi_14": 60},
                                   {"ret_20d": 0.1, "ret_60d": 0.1, "ret_240d": 0.1}, {})
        self.assertNotIn("short_uptrend", patterns)
        self.assertNotIn("mid_uptrend", patterns)
        self.assertNotIn("long_uptrend", patterns)

    def test_margin_candidate_requires_one_hundred_lots(self):
        row = {"Close": 10, "MarginBalance": 5000}
        for volume, expected in ((100, False), (99_999, False), (100_000, True)):
            row["Volume"] = volume
            self.assertEqual("margin_distress_rebound" in pc._classify_one(row, {}, {}, avg_cost=10), expected)

    def test_historical_signal_uses_same_calendar_return_as_current(self):
        target = date(2026, 9, 16)
        rows = []
        for n in range(599, -1, -1):
            day = target - timedelta(days=n)
            if day.weekday() < 5:
                rows.append({"Date": day, "Close": 200 if n > 300 else 100, "sma_54": 140})
        rows[-1]["Close"] = 150
        with patch.object(db, "ticker_history", return_value=rows) as history:
            actual = pc.get_pattern_at_dates("2330", "long_uptrend", [str(target)])
        self.assertTrue(actual[str(target)])
        history.assert_called_once_with("2330", days=600, as_of=str(target))

    def test_short_history_does_not_invent_240_day_return(self):
        target = date(2026, 9, 16)
        rows = [{"Date": target - timedelta(days=n), "Close": 100, "sma_54": 150}
                for n in range(100, -1, -1)]
        rows[-1]["Close"] = 60
        with patch.object(db, "ticker_history", return_value=rows):
            actual = pc.get_pattern_at_dates("2330", "long_drawdown", [str(target)])
        self.assertFalse(actual[str(target)])

    def test_three_day_buy_requires_every_day_positive(self):
        rows = [{"Date": date(2026, 1, 1) + timedelta(days=i), "Close": 100+i,
                 "sma_27": 80, "rsi_14": 50, "ForeignNet": 1} for i in range(100)]
        rows[58]["ForeignNet"] = -1
        rows[59]["ForeignNet"] = -1
        rows[60]["ForeignNet"] = 100
        result = rtf.section_backtest({"ticker": "2330"}, {}, rows)
        self.assertIn("| 外資 3 日連買 | 0 |", result)
        self.assertNotIn("Sharpe", result)

    def test_margin_change_preserves_warehouse_lots(self):
        rows = [{"MarginBalance": 1000, "ShortBalance": 500},
                {"MarginBalance": 1100, "ShortBalance": 450}]
        with patch.object(db, "ticker_history", return_value=rows):
            result = rtf.section_margin("2330", rows[-1])
        self.assertIn("**1,100 張** | +100 張", result)
        self.assertIn("**450 張** | -50 張", result)

    def test_watchlist_cap_volume_and_missing_return_units(self):
        pick = ms.build_candidate({"Ticker": "2330", "Close": 100, "Volume": 12500}, {}, {})
        pick.market_cap = 2e9
        header = watchlist.render_pick_header(pick)
        self.assertIn("20.0 億", header)
        self.assertIn("12.5 張", header)
        self.assertNotIn("K 張", header)
        result = watchlist.render_valuation_section(pick)
        self.assertIn("未提供", result)
        self.assertNotIn("+0.0%", result)

    def test_empty_backtest_is_unavailable_instead_of_zero_percent(self):
        result = patterns_html._build_pattern_section("value_undervalued", dict(pc.PATTERNS["value_undervalued"], count=0), [],
                                                     {"value_undervalued": {"unavailable_reason": "fixture missing history"}})
        self.assertIn("fixture missing history", result)
        self.assertIn("未計算勝率", result)
        self.assertNotIn("0%", result)
        self.assertNotIn("0.00%", result)

    def test_windows_process_worker_retains_failure_identity(self):
        with tempfile.TemporaryDirectory() as folder, ProcessPoolExecutor(max_workers=2) as pool:
            future = pool.submit(render_only._render_one, "2330", {"_err": "fixture source failure"},
                                 folder, "2026-09-16")
            self.assertEqual(future.result(timeout=30), ("2330", "fixture source failure"))
            self.assertFalse((Path(folder) / "2330.html").exists())


if __name__ == "__main__":
    unittest.main()
