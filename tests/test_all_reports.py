"""Canonical input and real-delivery safety contracts; no external sends."""
from contextlib import nullcontext
from datetime import date, timedelta
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'),str(ROOT/'scripts')]
import report_inputs as inputs
import chip_rank as rank
import chip_advanced as advanced
import render_chips_advanced as advanced_html
import chip_push as push
import pipeline_state as ps
import publish_ghpages as publisher
import company_refresh as company


class AllReportsTests(unittest.TestCase):
    def test_name_repair_ignores_invalid_dates_and_old_emerging_names(self):
        today = date.today().isoformat()
        rows = [{'stock_id':'2353','stock_name':'wrong','type':'twse','date':'None'},
                {'stock_id':'2353','stock_name':'old','type':'emerging','date':today},
                {'stock_id':'2353','stock_name':'宏碁','type':'twse','date':today},
                {'stock_id':'2353','stock_name':'宏碁','type':'twse','date':today}]
        repairs = company.name_repairs({'2353':'宏\ufffd','2330':'台積電'},rows)
        self.assertEqual(repairs,[{'ticker':'2353','before':'宏\ufffd','after':'宏碁','source_date':today}])
        with self.assertRaisesRegex(ValueError,'ambiguous'):
            company.name_repairs({'2353':'宏\ufffd'},rows+[dict(rows[-1],stock_name='different')])
        with self.assertRaisesRegex(ValueError,'stale'):
            company.name_repairs({'2353':'宏\ufffd'},[dict(rows[-1],date=(date.today()-timedelta(days=8)).isoformat())])

    def test_negative_lot_format_has_one_sign(self):
        self.assertEqual(advanced_html.fmt_shares(-15000000),'−1.5萬張')

    def test_price_discontinuity_does_not_create_proxy_discount(self):
        dates = [(date(2026,9,16)-timedelta(days=i)).isoformat() for i in range(20)]
        prices = {day:{'2330':100 if i==0 else 300} for i,day in enumerate(dates)}
        rows = [{'stock_id':'2330','date':day,'name':'Dealer','net':100} for day in dates]
        features,used = advanced.build_features(prices,rows,{'2330':{'name':'台積電','industry':'半導體'}})
        self.assertTrue(features[0]['price_discontinuity'])
        self.assertIsNone(features[0]['vs_vwap_pct'])
        self.assertIsNone(features[0]['vwap_buy_20d'])

    def test_selling_force_retains_direction_and_card_uses_today_not_five_days(self):
        dates = [(date(2026,9,16)-timedelta(days=i)).isoformat() for i in range(20)]
        prices = {day:{'2330':100} for day in dates}
        rows = [{'stock_id':'2330','date':day,'name':'Dealer','net':-100} for day in dates]
        features,used = advanced.build_features(prices,rows,{'2330':{'name':'台積電','industry':'半導體'}})
        self.assertEqual(features[0]['force_ratio'],-1)
        self.assertEqual(features[0]['today_three_shares'],-100)
        self.assertEqual(features[0]['cum_5d_shares'],-500)
        body = advanced_html.card(features[0],'force')
        self.assertIn('今日 3 法人',body)
        self.assertNotIn('−0張',body)

    def test_daily_json_worker_uses_network_and_preserves_unrelated_caches(self):
        worker = (ROOT/'public/sw.js').read_text(encoding='utf-8')
        self.assertIn("path.endsWith('.json')",worker)
        self.assertIn("fetch(req,{cache:'no-store'})",worker)
        self.assertIn("k.startsWith('tw-invest-')",worker)
        self.assertIn('GrooveLab music app',worker)

    def test_advanced_receipt_rejects_wrong_run_missing_artifacts_and_short_history(self):
        run = {'nightly_id':'current','data_date':'2026-09-16','render_tickers':['2330']}
        days = [(date(2026,9,16)-timedelta(days=i)).isoformat() for i in range(30)]
        receipt = {'status':'ok','nightly_id':'current','data_date':run['data_date'],
            'current_rows':1949,'metadata_tickers':1,'rank_tickers':1949,'advanced_tickers':1799,'history_dates':days,'artifacts':[]}
        for value,reason in ((dict(receipt,nightly_id='older'),'identity'),
            (dict(receipt,history_dates=days[:29]),'history'),(receipt,'artifact set')):
            with self.assertRaisesRegex(ValueError,reason):
                ps.validate_all_reports(value,run)

    def test_canonical_net_has_no_fabricated_gross_buy_sell(self):
        source = {'dates':['2026-09-16'],'rows':[{'Date':'2026-09-16','Ticker':'2330',
            'ForeignNet':0,'InvestmentNet':10,'DealerNet':-3}]}
        rows = inputs.institutional_rows(source,1)
        self.assertNotIn('buy',rows[0])
        self.assertEqual(rank.build_per_ticker_calendar(rows)['2330'][0]['d'],-3)
        self.assertEqual(rank.build_per_ticker_calendar(rows)['2330'][0]['f'],0)

    def test_advanced_report_rejects_partial_twenty_day_window(self):
        prices = {'2026-09-16':{'2330':100}}
        rows = [{'stock_id':'2330','date':'2026-09-16','name':'Dealer','net':100}]
        features, dates = advanced.build_features(prices,rows,{'2330':{'name':'台積電','industry':'半導體'}})
        self.assertEqual(features,[])

    def test_inputs_reject_null_stale_and_duplicate_current_rows(self):
        days = [(date(2026,9,16)-timedelta(days=i)).isoformat() for i in range(30)]
        row = {'Date':days[0],'Ticker':'2330','ForeignNet':0,'InvestmentNet':1,'DealerNet':0}
        self.assertEqual(inputs.validate_rows([row],days,days[0],1),[row])
        for rows,dates in (([dict(row,ForeignNet=None)],days),([row,row],days),([row],days[1:])):
            with self.assertRaises(ValueError):
                inputs.validate_rows(rows,dates,days[0],1)

    def test_remote_verification_includes_advanced_and_history_artifacts(self):
        manifest = {'nightly_id':'x','data_date':'2026-09-16','tickers':[],
            'artifacts':[{'gh_path':'chips.html'},{'gh_path':'data/chips-history/2026-09-16.json'}]}
        with patch.object(publisher,'remote_verify_paths',return_value=[]) as check:
            publisher.remote_verify(Path('.'),manifest)
        self.assertIn('chips.html',check.call_args.args[2])
        self.assertIn('data/chips-history/2026-09-16.json',check.call_args.args[2])

    def test_telegram_same_day_is_sent_once_and_unknown_is_not_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(push,'LEDGER',root/'ledger.json'),patch.object(push,'RESULT',root/'result.json'),patch.object(ps,'state_lock',nullcontext),patch.object(push,'send_telegram',return_value={'status':'sent','message_id':123}) as send:
                marker = {'nightly_id':'a','data_date':'2026-09-16'}
                push.deliver(marker,'test-token','test-chat','message')
                repeated = push.deliver({**marker,'nightly_id':'b'},'test-token','test-chat','message')
                self.assertTrue(repeated['already_sent'])
                self.assertEqual(send.call_count,1)
                send.return_value = {'status':'unknown','reason':'uncertain'}
                next_day = {**marker,'data_date':'2026-09-17'}
                with self.assertRaisesRegex(ValueError,'uncertain'):
                    push.deliver(next_day,'test-token','test-chat','message')
                with self.assertRaisesRegex(ValueError,'manual receipt'):
                    push.deliver(next_day,'test-token','test-chat','message')
                self.assertEqual(send.call_count,2)

    def test_telegram_receipt_requires_api_ok_message_id_and_correct_chat(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value = response
        with patch.object(push.urllib.request,'urlopen',return_value=response):
            response.read.return_value = b'{"ok":true,"result":{"message_id":1,"chat":{"id":123}}}'
            self.assertEqual(push.send_telegram('summary','test-token','123')['status'],'sent')
            self.assertEqual(push.send_telegram('summary','test-token','456')['status'],'unknown')
            response.read.return_value = b'{"ok":false}'
            self.assertEqual(push.send_telegram('summary','test-token','123')['status'],'failed')

    def test_telegram_uses_foreign_amount_and_escapes_company_html(self):
        pick = {'ticker':'2330','name':'A&B<公司>','f_5d_twd':6,'t_5d_twd':None,'f_streak':3}
        chips = {'date':'2026-09-16','nightly_id':'a','tabs':{'same_buy':[pick],'same_sell':[], 'f_consec_buy':[pick]}}
        message = push.compose_message(chips,{'date':chips['date'],'nightly_id':'a'})
        self.assertIn('A&amp;B&lt;公司&gt;',message)
        self.assertIn('投信 —',message)
        self.assertIn('3 日／+6.00 億',message)
        with self.assertRaises(ValueError):
            push.compose_message(chips,{'date':'2026-09-15','nightly_id':'a'})


if __name__ == '__main__':
    unittest.main()
