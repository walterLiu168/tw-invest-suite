"""Send the certified daily chips summary after both sites are verified."""
from datetime import datetime
import hashlib
from html import escape
import importlib.util
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import pipeline_state as ps

CONFIG_ROOT = Path(r'D:\CODEX\AI-Telegram')
LEDGER = ps.RUNTIME / '_debug' / 'chip_telegram_deliveries.json'
RESULT = ps.RUNTIME / '_debug' / 'chip_telegram_result.json'


def credentials():
    spec = importlib.util.spec_from_file_location('chips_env_config', CONFIG_ROOT / 'config' / 'env_config.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    api = module.load_shared_config(CONFIG_ROOT / 'config' / 'shared_config.json').get('api_keys', {})
    token = os.environ.get('TELEGRAM_BOT_TOKEN') or api.get('telegram_bot_signal') or api.get('telegram_bot_stock') or api.get('telegram_token')
    chat = os.environ.get('TELEGRAM_CHAT_ID') or api.get('chat_id') or api.get('telegram_chat_id')
    if not token or not chat:
        raise ValueError('Existing Telegram bot/chat configuration unavailable')
    return str(token).strip(), str(chat).strip()


def compose_message(chips, advanced):
    if chips['date'] != advanced['date'] or chips.get('nightly_id') != advanced.get('nightly_id'):
        raise ValueError('Telegram report date/run mismatch')
    lines = [f"<b>台股籌碼摘要</b> · {chips['date']}",
             '來源：canonical MySQL；金額為淨股數 × 當日收盤價估算。']
    for title, key in (('土洋同買（5 日）','same_buy'),('土洋同賣（5 日）','same_sell')):
        picks = chips['tabs'][key][:5]
        lines.append('\n<b>' + title + '</b>')
        for pick in picks:
            def amount(value):
                return '—' if value is None else f'{value:+.2f} 億'
            lines.append(f"{escape(pick['ticker'])} {escape(pick['name'][:14])} 外資 {amount(pick.get('f_5d_twd'))}／投信 {amount(pick.get('t_5d_twd'))}")
        if not picks:
            lines.append('無符合門檻個股')
    big = [p for p in chips['tabs']['f_consec_buy'] if p['f_streak'] >= 3 and (p.get('f_5d_twd') or 0) >= 5]
    lines.append('\n<b>外資連買 ≥ 3 日且 5 日估算淨買超 ≥ 5 億</b>')
    for pick in sorted(big, key=lambda p:-p['f_5d_twd'])[:5]:
        lines.append(f"{escape(pick['ticker'])} {escape(pick['name'][:14])} {pick['f_streak']} 日／{pick['f_5d_twd']:+.2f} 億")
    if not big:
        lines.append('無符合門檻個股')
    lines += ['\n代理價使用正淨買超加權收盤價，並非實際成交均價或法人持倉成本。',
        '<a href="https://walterliu168.github.io/tw-invest-suite/chips.html">籌碼排行</a> · <a href="https://walterliu168.github.io/tw-invest-suite/chips-advanced.html">籌碼進階</a>',
        '<a href="https://groovelab.dev/concepts.html">概念股</a> · <a href="https://groovelab.dev/sectors.html">產業</a>']
    message = '\n'.join(lines)
    if len(message) > 4000:
        raise ValueError('Telegram summary exceeds one-message budget')
    return message


def send_telegram(text, token, chat):
    data = urllib.parse.urlencode({'chat_id':chat,'text':text,'parse_mode':'HTML','disable_web_page_preview':'true'}).encode()
    request = urllib.request.Request(f'https://api.telegram.org/bot{token}/sendMessage', data=data)
    try:
        with urllib.request.urlopen(request,timeout=30) as response:
            value = json.loads(response.read())
    except urllib.error.HTTPError as error:
        return {'status':'failed','reason':f'Telegram HTTP {error.code}'}
    except Exception as error:
        return {'status':'unknown','reason':f'Telegram response uncertain: {type(error).__name__}'}
    result = value.get('result', {})
    if not value.get('ok'):
        return {'status':'failed','reason':'Telegram API rejected request'}
    if not result.get('message_id') or str(result.get('chat',{}).get('id')) != chat:
        return {'status':'unknown','reason':'Telegram receipt identity unavailable/mismatched'}
    return {'status':'sent','message_id':result['message_id'],'telegram_date':result.get('date')}


def deliver(marker, token, chat, message):
    chat_hash = hashlib.sha256(chat.encode()).hexdigest()
    key = marker['data_date'] + ':' + chat_hash
    digest = hashlib.sha256(message.encode()).hexdigest()
    with ps.state_lock():
        ledger = ps.read_json(LEDGER) if LEDGER.exists() else {}
        old = ledger.get(key, {})
        if old.get('status') == 'sent':
            receipt = {**old,'status':'sent','already_sent':True,'nightly_id':marker['nightly_id']}
            ps.atomic_json(RESULT,receipt)
            return receipt
        if old.get('status') in ('sending','unknown'):
            raise ValueError('Prior Telegram delivery uncertain; manual receipt check required to avoid duplicates')
        receipt = {'nightly_id':marker['nightly_id'],'data_date':marker['data_date'],
            'status':'sending','chat_hash':chat_hash,'message_sha256':digest,'attempted_at':datetime.now().isoformat()}
        ledger[key] = receipt
        ps.atomic_json(LEDGER,ledger)
        result = send_telegram(message,token,chat)
        receipt.update(result, completed_at=datetime.now().isoformat())
        ledger[key] = receipt
        ps.atomic_json(LEDGER,ledger)
        ps.atomic_json(RESULT,receipt)
        if receipt['status'] != 'sent':
            raise ValueError(receipt['reason'])
        return receipt


def main():
    marker = ps.verify_marker()
    canonical = ps.read_json(ps.RUNTIME / '_debug' / 'publication_result.json')
    groove = ps.read_json(ps.RUNTIME / '_debug' / 'groove_publication_result.json')
    if (canonical.get('nightly_id') != marker['nightly_id'] or canonical.get('status') != 'verified'
        or canonical.get('report_status') != 'verified' or canonical.get('postflight_exit') != 0
        or groove.get('nightly_id') != marker['nightly_id'] or groove.get('status') != 'verified'):
        raise ValueError('Both sites and final postflight must pass before Telegram')
    chips = ps.read_json(ps.PUBLIC / 'data' / 'chips.json')
    advanced = ps.read_json(ps.PUBLIC / 'data' / 'chips-advanced.json')
    if chips.get('nightly_id') != marker['nightly_id'] or chips['date'] != marker['data_date']:
        raise ValueError('Telegram summary differs from certified run')
    token, chat = credentials()
    receipt = deliver(marker,token,chat,compose_message(chips,advanced))
    print(f"Telegram {receipt['status']} data_date={receipt['data_date']} message_id={receipt['message_id']} already_sent={receipt.get('already_sent',False)}")
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f'Telegram delivery failed: {type(error).__name__}: {error}',file=sys.stderr)
        raise SystemExit(1)
