"""Report source date and missing-data regressions."""
from contextlib import contextmanager
from datetime import date
from pathlib import Path
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import db_client as db
import market_screen as ms
import deep_dive_prompts as ddp
import render_ticker_full as renderer


def candidate(**values):
    result = ms.build_candidate({"Ticker": "2330", "Close": 100, "Volume": 12500}, {}, {})
    for name, value in values.items():
        setattr(result, name, value)
    return result


class ReportIdentityTests(unittest.TestCase):
    def test_income_statement_comprehensive_income_is_not_roe_equity(self):
        result = renderer.section_finlab_roe({'fundamentals': {'rows': [
            {'date':'2026-06-30','type':'IncomeAfterTaxes','value':2592000},
            {'date':'2026-06-30','type':'TotalConsolidatedProfitForThePeriod','value':69452000},
            {'date':'2026-06-30','type':'EquityAttributableToOwnersOfParent','value':2592000},
        ]}}, [])
        self.assertNotIn('10717.90%',result)
        self.assertIn('| yfinance | — |',result)
        self.assertIn('不能作為 ROE 分母',result)

    def test_reported_roe_preserves_zero_negative_and_missing(self):
        for value, expected in [(0,'0.00%'),(-0.025,'-2.50%'),(None,'—'),
                                (float('nan'),'—'),(float('inf'),'—'),(True,'—')]:
            with self.subTest(value=value):
                result = renderer.section_finlab_roe({'yfinance':{'returnOnEquity':value}},[])
                self.assertIn(f'| yfinance | {expected} |',result)

    def test_quarterly_profit_uses_net_income_and_real_quarter_labels(self):
        rows = [
            {'date':'2026-06-30','type':'Revenue','value':1e8},
            {'date':'2026-06-30','type':'IncomeAfterTaxes','value':-2e7},
            {'date':'2026-06-30','type':'EPS','value':0},
            {'date':'2026-06-30','type':'TotalConsolidatedProfitForThePeriod','value':9e8},
            {'date':'2026-06-30','type':'IncomeFromContinuingOperationsBeforeTax','value':8e8},
            {'date':'2026-09-30','type':'Revenue','value':float('nan')},
            {'date':'2026-09-30','type':'EPS','value':None},
            {'date':'2026-09-30','type':'OperatingIncome','value':0},
        ]
        result = renderer.section_fundamentals({'fundamentals':{'rows':rows}})
        self.assertIn('| 2026Q2 | 1.000 | — | — | -0.200 | 0.00 |',result)
        self.assertIn('| 2026Q3 | — | — | 0.000 | — | — |',result)
        self.assertNotIn('Q06',result)

    def test_closing_snapshot_uses_shares_and_preserves_unknown_or_zero(self):
        with patch.object(db,'ticker_history',return_value=[{'Close':11},{'Close':10.85}]):
            result = renderer.section_price({'ticker':'1452'},{'Close':10.85,'Volume':27876,'Date':'2026-09-16'})
        self.assertIn('27,876 股 (27.876 張)',result)
        self.assertNotIn('27,876 張',result)
        self.assertIn('-0.15 (-1.36%)',result)
        with patch.object(db,'ticker_history',return_value=[]):
            missing = renderer.section_price({'ticker':'1452'},{'Close':10.85,'Volume':None})
            zero = renderer.section_price({'ticker':'1452'},{'Close':10.85,'Volume':0})
        self.assertIn('| 漲跌 | — |',missing)
        self.assertIn('| 成交量 | — |',missing)
        self.assertIn('0 股 (0.000 張)',zero)

    def test_missing_values_are_not_zero_and_volume_is_lots(self):
        prompt = ddp.render_prompt(candidate())
        self.assertIn("**Market Cap**: 未提供", prompt)
        self.assertIn("未提供 (60d), 未提供 (240d)", prompt)
        self.assertIn("12.5 張", prompt)
        self.assertNotIn("52-Week Return", prompt)
        self.assertNotIn("no recent news in stock_news", prompt)

    def test_real_zero_return_and_market_cap_survive_both_templates(self):
        for template in (ddp.TIGER_GLOBAL_TEMPLATE, ddp.BAUPOST_TEMPLATE):
            with patch.object(ddp, "pick_template", return_value=template):
                prompt = ddp.render_prompt(candidate(market_cap=1_500_000, excess_return_60d=0,
                                                    excess_return_240d=-0.15))
                self.assertIn("NT$2M", prompt)
                self.assertIn("+0.0% (60d), -15.0% (240d)", prompt)

    def test_nonfinite_provider_values_are_missing(self):
        prompt = ddp.render_prompt(candidate(market_cap=float("inf"), excess_return_60d=float("nan")))
        self.assertIn("**Market Cap**: 未提供", prompt)
        self.assertIn("未提供 (60d)", prompt)

    def test_history_query_binds_cutoff_and_resets_context(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [{"Date": date(2026, 9, 15)}, {"Date": date(2026, 9, 14)}]
        @contextmanager
        def mocked_cursor():
            yield cursor
        with patch.dict(os.environ, {}, clear=True), patch.object(db, "get_cursor", mocked_cursor):
            with db.report_date("2026-09-15"):
                history = db.ticker_history("2330", days=2)
                sql, params = cursor.execute.call_args.args
                self.assertIn("Date <= %s", sql)
                self.assertEqual(params, ("2330", "2026-09-15", "2026-09-15", 2))
                self.assertEqual(history[-1]["Date"], date(2026, 9, 15))
            self.assertIsNone(db.query_date())

    def test_renderer_uses_frozen_date_and_restores_after_exception(self):
        @renderer._dated_report
        def render(ticker, data):
            self.assertEqual(db.query_date(), "2026-09-15")
            raise ValueError("fixture")
        with patch.dict(os.environ, {"TW_DATA_DATE": "2026-09-15"}):
            with self.assertRaises(ValueError):
                render("2330", {"latest_date": "2026-09-16"})
        self.assertIsNone(db._REPORT_DATE.get())

    def test_prompt_uses_actual_dated_values_and_filters_news(self):
        data = {"ticker": "2330", "valuation": {"market_cap": 2e12}, "news": [
            {"date": "2026-09-16", "title": "future"},
            {"date": "2026-09-15", "title": "current"},
            {"date": "2026-09-01", "title": "old"}]}
        with patch.object(db, "long_term_returns_batch", return_value={"2330": {"ret_60d": 0}}) as returns:
            context = renderer._prompt_context(data, {"Date": date(2026, 9, 15)})
        returns.assert_called_once_with(["2330"], "2026-09-15")
        self.assertEqual(context["market_cap"], 2e12)
        self.assertEqual(context["excess_return_60d"], 0)
        self.assertIsNone(context["excess_return_240d"])
        self.assertEqual(context["news_headlines"], ["current"])

    def test_screener_keeps_unavailable_returns_missing(self):
        pick = candidate()
        with patch.object(db, "long_term_returns_batch", return_value={"2330": {"ret_60d": 0}}):
            ms.enrich_long_term_returns([pick], "2026-09-15")
        self.assertEqual(pick.excess_return_60d, 0)
        self.assertIsNone(pick.excess_return_240d)


if __name__ == "__main__":
    unittest.main()
