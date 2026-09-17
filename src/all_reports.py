"""Generate every existing market report from one canonical dated input set."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / 'scripts'))
import pipeline_state as ps
from report_inputs import load_inputs, institutional_rows, price_rows


def stamp(path, inputs, nightly_id):
    value = ps.read_json(path)
    if isinstance(value,dict):
        value.update(date=inputs['date'],nightly_id=nightly_id,source=inputs['source'])
    ps.atomic_json(path,value)
    return value


def main():
    run = ps.read_json(ps.STATE)
    if run.get('status') != 'running' or os.environ.get('TW_NIGHTLY_ID') != run['nightly_id']:
        raise ValueError('All-report run identity mismatch')
    inputs = load_inputs()
    if inputs['date'] != run['data_date']:
        raise ValueError('All-report frozen date mismatch')
    data = ps.PUBLIC / 'data'
    receipt_path = ps.RUNTIME / '_debug' / 'all_reports_receipt.json'
    receipt = {'nightly_id':run['nightly_id'],'data_date':run['data_date'],'status':'running'}
    ps.atomic_json(receipt_path,receipt)
    try:
        metadata, dates = inputs['metadata'], inputs['dates']
        by_ticker = {t:{'name':m['name'],'industry':m['industry']} for t,m in metadata.items()}
        ps.atomic_json(data / 'tw-industry.json',{'date':inputs['date'],'nightly_id':run['nightly_id'],
            'source':'canonical industry_type','total':len(by_ticker),'by_ticker':by_ticker,
            'industry_count':len({m['industry'] for m in metadata.values()})})
        # Import after writing the current industry map; existing helpers cache it.
        import concept_stocks as concepts
        import chip_advanced as advanced
        import chip_rank as rank
        import sector_aggregate as sectors
        import render_chips_advanced as advanced_html
        import render_concepts as concepts_html
        import build_ticker_meta as ticker_meta
        import generate_og as og
        concepts.main()
        stamp(data / 'concept-stocks.json',inputs,run['nightly_id'])
        print('all_reports: concepts/industry ready',flush=True)
        ohlcv = price_rows(inputs,20)
        features, used = advanced.build_features(ohlcv,institutional_rows(inputs,20),metadata)
        calendars = rank.build_per_ticker_calendar(institutional_rows(inputs,20))
        complete_calendars = {t:rows for t,rows in calendars.items() if [r['date'] for r in rows] == dates[:20]}
        expected_advanced = {t for t in metadata if t in complete_calendars and all(t in ohlcv[d] for d in dates[:20])}
        if not features or {f['ticker'] for f in features} != expected_advanced or used[0] != inputs['date']:
            raise ValueError('Advanced chips date/coverage incomplete')
        advanced.write_json(features,used,ohlcv)
        stamp(data / 'chips-advanced.json',inputs,run['nightly_id'])
        advanced_html.main()
        calendars = complete_calendars
        ranked = rank.compute_features(calendars,metadata)
        if len(ranked) < 1900:
            raise ValueError('Chips ranking coverage incomplete')
        result = rank.write_json(ranked,dates[:20],features)
        result.update(date=inputs['date'],nightly_id=run['nightly_id'],source=inputs['source'],price_date=inputs['date'])
        ps.atomic_json(data / 'chips.json',result)
        rank.render_html(result,ps.PUBLIC / 'chips.html')
        print('all_reports: chips/advanced ready',flush=True)
        inst5 = {}
        for row in institutional_rows(inputs,5):
            if row['stock_id'] not in calendars:
                continue
            slot = inst5.setdefault(row['stock_id'],{'foreign_5d_shares':0,'trust_5d_shares':0,'dealer_5d_shares':0,'three_net_5d_shares':0})
            key = {'Foreign_Investor':'foreign_5d_shares','Investment_Trust':'trust_5d_shares','Dealer':'dealer_5d_shares'}[row['name']]
            slot[key] += row['net']
            slot['three_net_5d_shares'] += row['net']
        groups = sectors.aggregate(metadata,sectors.compute_revenue_yoy(metadata),inst5)
        sectors.write_json(groups,dates[:5])
        stamp(data / 'sectors.json',inputs,run['nightly_id'])
        sectors.render_html(groups,dates[:5],len(metadata))
        concepts_html.main()
        print('all_reports: sectors/concepts HTML ready',flush=True)
        history = data / 'chips-history'
        history.mkdir(parents=True,exist_ok=True)
        for day in dates:
            daily = {}
            for row in inputs['rows']:
                if str(row['Date'])[:10] == day:
                    daily[row['Ticker']] = {k:float(row[col]) for k,col in
                        (('f','ForeignNet'),('t','InvestmentNet'),('d','DealerNet'))}
            ps.atomic_json(history / f'{day}.json',{'date':day,'nightly_id':run['nightly_id'],
                'source':inputs['source'],'tickers':daily})
        ticker_meta.main()
        ps.atomic_json(data / 'chips-history-index.json',{'date':inputs['date'],'nightly_id':run['nightly_id'],'source':inputs['source'],'dates':sorted(dates),'count':len(dates)})
        picks = [p for p in og.parse_watchlist(ps.PUBLIC / 'watchlist.html') if p['horizon'] != 'margin']
        if {p['ticker'] for p in picks} != {p['ticker'] for p in run['picks']}:
            raise ValueError('OG selected-pick identity mismatch')
        og.render_og(picks,data / 'og.png',inputs['date'])
        paths = ['sectors.html','chips.html','chips-advanced.html','concepts.html',
            'data/sectors.json','data/chips.json','data/chips-advanced.json','data/concept-stocks.json',
            'data/tw-industry.json','data/tickers.json','data/chips-history-index.json','data/og.png']
        paths += [f'data/chips-history/{day}.json' for day in dates]
        artifacts = [ps.artifact(ps.PUBLIC / relative,relative) for relative in paths]
        receipt.update(status='ok',source=inputs['source'],current_rows=inputs['current_rows'],
            metadata_tickers=len(metadata),rank_tickers=len(ranked),advanced_tickers=len(features),
            advanced_excluded_incomplete_price=len(calendars)-len(features),history_dates=dates,artifacts=artifacts)
        ps.atomic_json(receipt_path,receipt)
        print(f"all_reports: certified candidates={len(artifacts)} data_date={inputs['date']}",flush=True)
    except Exception as error:
        ps.atomic_json(receipt_path,{**receipt,'status':'failed','error':str(error)})
        raise
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
