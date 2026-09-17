"""Shared dated canonical warehouse inputs for the existing market reports."""
from datetime import date
from functools import lru_cache
import math
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import db_client as db
import cache_manager as cache


def report_date():
    value = os.environ.get('TW_DATA_DATE') or db.latest_date('daily_data2_full')
    return date.fromisoformat(str(value)[:10]).isoformat()


def finite(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def validate_rows(rows, dates, target, minimum=1900):
    if not dates or dates[0] != target or len(dates) < 30:
        raise ValueError('Market-report source date/history coverage mismatch')
    latest = [r for r in rows if str(r['Date'])[:10] == target]
    if len(latest) < minimum or len({r['Ticker'] for r in latest}) != len(latest):
        raise ValueError('Market-report current coverage incomplete/duplicated')
    for row in rows:
        if any(finite(row.get(key)) is None for key in ('ForeignNet','InvestmentNet','DealerNet')):
            raise ValueError(f"Incomplete institutional source: {row['Ticker']} {row['Date']}")
    return latest


@lru_cache(maxsize=1)
def load_inputs():
    target = report_date()
    with db.get_cursor() as cursor:
        cursor.execute('SELECT DISTINCT Date FROM daily_data2_full WHERE Date <= %s ORDER BY Date DESC LIMIT 30',(target,))
        dates = [str(r['Date'])[:10] for r in cursor.fetchall()]
        if not dates:
            raise ValueError('No market-report history')
        marks = ','.join(['%s']*len(dates))
        cursor.execute(f'''SELECT Ticker, Date, Close, ForeignNet, InvestmentNet, DealerNet
            FROM daily_data2_full WHERE Date IN ({marks}) ORDER BY Date DESC, Ticker''',tuple(dates))
        rows = cursor.fetchall()
    latest = validate_rows(rows, dates, target)
    metadata = {}
    prices = {r['Ticker']:finite(r['Close']) for r in latest}
    for ticker, industry in db.all_industries().items():
        yf_entry = cache.get_fresh(ticker,'yfinance') or {}
        pe_entry = cache.get_fresh(ticker,'finmind_pe') or {}
        yf, pe = yf_entry.get('data') or {}, pe_entry.get('data') or {}
        market_cap = finite(yf.get('marketCap'))
        earnings_multiple = finite(pe.get('PER'))
        if earnings_multiple is None:
            earnings_multiple = finite(yf.get('trailingPE'))
        metadata[ticker] = {'name':industry.get('company') or ticker,
            'industry':industry.get('industry') or '未分類',
            'sector':yf.get('sector') or '', 'mkt_cap':market_cap if market_cap and market_cap > 0 else 0,
            'pe':earnings_multiple if earnings_multiple and earnings_multiple > 0 else None,
            'price':prices.get(ticker) or 0}
    return {'date':target,'dates':dates,'rows':rows,'metadata':metadata,
            'current_rows':len(latest),'source':'canonical MySQL daily_data2_full / industry_type'}


def institutional_rows(inputs, days):
    dates = set(inputs['dates'][:days])
    result = []
    for row in inputs['rows']:
        day = str(row['Date'])[:10]
        if day in dates:
            for key, name in (('ForeignNet','Foreign_Investor'),('InvestmentNet','Investment_Trust'),('DealerNet','Dealer')):
                result.append({'stock_id':row['Ticker'],'date':day,'name':name,'net':finite(row[key])})
    return result


def price_rows(inputs, days):
    dates = set(inputs['dates'][:days])
    result = {}
    for row in inputs['rows']:
        day, close = str(row['Date'])[:10], finite(row['Close'])
        if day in dates and close is not None and close > 0:
            result.setdefault(day,{})[row['Ticker']] = close
    return result
