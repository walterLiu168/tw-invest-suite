#!/usr/bin/env python3
"""Refresh the canonical ``stock_features`` snapshot for one market date.

The job is intentionally DB-local: it derives features from the already
verified ``daily_data2_full`` history, so the daily pipeline does not depend
on an agent or a per-ticker API loop.  It is idempotent on ``ticker,date``.
"""
from __future__ import annotations

import argparse
import sys
import subprocess
import json
from pathlib import Path
from datetime import date

import pymysql

import db_client as db


MIN_TICKERS_DEFAULT = 1900
PREDICTION_TIMEOUT_SECONDS = 720


def _target_date(value: str | None) -> str:
    if value:
        date.fromisoformat(value)
        return value
    with db.get_cursor() as cur:
        cur.execute("SELECT MAX(Date) AS d FROM daily_data2_full")
        row = cur.fetchone() or {}
    if not row.get("d"):
        raise RuntimeError("daily_data2_full is empty")
    return str(row["d"])[:10]


FEATURE_SQL = """
SELECT c.*,
    p1.Close AS c1, p20.Close AS c20, p40.Close AS c40,
    p60.Close AS c60, p80.Close AS c80, p100.Close AS c100,
    p120.Close AS c120, p140.Close AS c140, p160.Close AS c160,
    p180.Close AS c180, p200.Close AS c200, p220.Close AS c220,
    p240.Close AS c240,
    (SELECT CASE WHEN COUNT(v.Volume)=20 THEN AVG(v.Volume) ELSE NULL END FROM (
        SELECT h.Volume FROM daily_data2_full h
        WHERE h.Ticker=c.Ticker AND h.Date < c.Date
        ORDER BY h.Date DESC LIMIT 20
    ) v) AS avg_volume_20
FROM daily_data2_full c
LEFT JOIN daily_data2_full p1 ON p1.Ticker=c.Ticker AND p1.Date=(
    SELECT MAX(h.Date) FROM daily_data2_full h WHERE h.Ticker=c.Ticker
      AND h.Date < c.Date AND h.Close > 0)
LEFT JOIN daily_data2_full p20 ON p20.Ticker=c.Ticker AND p20.Date=(
    SELECT MAX(h.Date) FROM daily_data2_full h WHERE h.Ticker=c.Ticker
      AND h.Date <= DATE_SUB(c.Date, INTERVAL 20 DAY) AND h.Close > 0)
LEFT JOIN daily_data2_full p40 ON p40.Ticker=c.Ticker AND p40.Date=(
    SELECT MAX(h.Date) FROM daily_data2_full h WHERE h.Ticker=c.Ticker
      AND h.Date <= DATE_SUB(c.Date, INTERVAL 40 DAY) AND h.Close > 0)
LEFT JOIN daily_data2_full p60 ON p60.Ticker=c.Ticker AND p60.Date=(
    SELECT MAX(h.Date) FROM daily_data2_full h WHERE h.Ticker=c.Ticker
      AND h.Date <= DATE_SUB(c.Date, INTERVAL 60 DAY) AND h.Close > 0)
LEFT JOIN daily_data2_full p80 ON p80.Ticker=c.Ticker AND p80.Date=(
    SELECT MAX(h.Date) FROM daily_data2_full h WHERE h.Ticker=c.Ticker
      AND h.Date <= DATE_SUB(c.Date, INTERVAL 80 DAY) AND h.Close > 0)
LEFT JOIN daily_data2_full p100 ON p100.Ticker=c.Ticker AND p100.Date=(
    SELECT MAX(h.Date) FROM daily_data2_full h WHERE h.Ticker=c.Ticker
      AND h.Date <= DATE_SUB(c.Date, INTERVAL 100 DAY) AND h.Close > 0)
LEFT JOIN daily_data2_full p120 ON p120.Ticker=c.Ticker AND p120.Date=(
    SELECT MAX(h.Date) FROM daily_data2_full h WHERE h.Ticker=c.Ticker
      AND h.Date <= DATE_SUB(c.Date, INTERVAL 120 DAY) AND h.Close > 0)
LEFT JOIN daily_data2_full p140 ON p140.Ticker=c.Ticker AND p140.Date=(
    SELECT MAX(h.Date) FROM daily_data2_full h WHERE h.Ticker=c.Ticker
      AND h.Date <= DATE_SUB(c.Date, INTERVAL 140 DAY) AND h.Close > 0)
LEFT JOIN daily_data2_full p160 ON p160.Ticker=c.Ticker AND p160.Date=(
    SELECT MAX(h.Date) FROM daily_data2_full h WHERE h.Ticker=c.Ticker
      AND h.Date <= DATE_SUB(c.Date, INTERVAL 160 DAY) AND h.Close > 0)
LEFT JOIN daily_data2_full p180 ON p180.Ticker=c.Ticker AND p180.Date=(
    SELECT MAX(h.Date) FROM daily_data2_full h WHERE h.Ticker=c.Ticker
      AND h.Date <= DATE_SUB(c.Date, INTERVAL 180 DAY) AND h.Close > 0)
LEFT JOIN daily_data2_full p200 ON p200.Ticker=c.Ticker AND p200.Date=(
    SELECT MAX(h.Date) FROM daily_data2_full h WHERE h.Ticker=c.Ticker
      AND h.Date <= DATE_SUB(c.Date, INTERVAL 200 DAY) AND h.Close > 0)
LEFT JOIN daily_data2_full p220 ON p220.Ticker=c.Ticker AND p220.Date=(
    SELECT MAX(h.Date) FROM daily_data2_full h WHERE h.Ticker=c.Ticker
      AND h.Date <= DATE_SUB(c.Date, INTERVAL 220 DAY) AND h.Close > 0)
LEFT JOIN daily_data2_full p240 ON p240.Ticker=c.Ticker AND p240.Date=(
    SELECT MAX(h.Date) FROM daily_data2_full h WHERE h.Ticker=c.Ticker
      AND h.Date <= DATE_SUB(c.Date, INTERVAL 240 DAY) AND h.Close > 0)
WHERE c.Date=%s AND c.Close > 0
"""


UPSERT_SQL = """
INSERT INTO stock_features (
    ticker, `date`, ret_1d, ret_20d, ret_40d, ret_60d, ret_80d,
    ret_100d, ret_120d, ret_140d, ret_160d, ret_180d, ret_200d,
    ret_220d, ret_240d, foreign_net_ratio, investment_net_ratio,
    dealer_net_ratio, three_net_sum, three_agreement, margin_usage,
    short_ratio, daytrade_vol_ratio, daytrade_amt_ratio,
    volatility_20d, relative_vol, volume_ratio_20d, market_return_20d,
    excess_return_20d
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
)
ON DUPLICATE KEY UPDATE
    ret_1d=VALUES(ret_1d), ret_20d=VALUES(ret_20d),
    ret_40d=VALUES(ret_40d), ret_60d=VALUES(ret_60d),
    ret_80d=VALUES(ret_80d), ret_100d=VALUES(ret_100d),
    ret_120d=VALUES(ret_120d), ret_140d=VALUES(ret_140d),
    ret_160d=VALUES(ret_160d), ret_180d=VALUES(ret_180d),
    ret_200d=VALUES(ret_200d), ret_220d=VALUES(ret_220d),
    ret_240d=VALUES(ret_240d), foreign_net_ratio=VALUES(foreign_net_ratio),
    investment_net_ratio=VALUES(investment_net_ratio),
    dealer_net_ratio=VALUES(dealer_net_ratio), three_net_sum=VALUES(three_net_sum),
    three_agreement=VALUES(three_agreement), margin_usage=VALUES(margin_usage),
    short_ratio=VALUES(short_ratio), daytrade_vol_ratio=VALUES(daytrade_vol_ratio),
    daytrade_amt_ratio=VALUES(daytrade_amt_ratio), volatility_20d=VALUES(volatility_20d),
    relative_vol=VALUES(relative_vol), volume_ratio_20d=VALUES(volume_ratio_20d),
    market_return_20d=VALUES(market_return_20d), excess_return_20d=VALUES(excess_return_20d)
"""


def _ratio(numerator, denominator):
    if numerator is None or denominator in (None, 0):
        return None
    return float(numerator) / float(denominator)


def refresh(target_date: str, min_tickers: int = MIN_TICKERS_DEFAULT) -> int:
    with db.get_cursor() as cur:
        cur.execute(
            "SELECT COUNT(DISTINCT Ticker) AS n FROM daily_data2_full "
            "WHERE Date=%s AND Close>0", (target_date,)
        )
        expected = int((cur.fetchone() or {}).get("n") or 0)
    if expected < min_tickers:
        raise RuntimeError(
            f"daily_data2_full {target_date} has only {expected} tickers "
            f"(required {min_tickers})"
        )

    conn = db.connect(cursorclass=pymysql.cursors.DictCursor)
    try:
        cur = conn.cursor()
        cur.execute(FEATURE_SQL, (target_date,))
        rows = cur.fetchall()
        if len(rows) < min_tickers:
            raise RuntimeError(
                f"feature derivation returned {len(rows)} rows for {target_date} "
                f"(required {min_tickers})"
            )
        def ret(row, n):
            prior = row.get(f"c{n}")
            close = row.get("Close")
            return (float(close) / float(prior)) - 1 if close and prior else None

        for r in rows:
            r["ret1"] = ret(r, 1)
            for n in (20, 40, 60, 80, 100, 120, 140, 160, 180, 200, 220, 240):
                r[f"ret{n}"] = ret(r, n)
        market_returns = [r["ret20"] for r in rows if r.get("ret20") is not None]
        market_ret20 = sum(market_returns) / len(market_returns) if market_returns else None
        values = []
        for r in rows:
            agreement = 1 if all((r.get(k) or 0) > 0 for k in ("ForeignNet", "InvestmentNet", "DealerNet")) else \
                -1 if all((r.get(k) or 0) < 0 for k in ("ForeignNet", "InvestmentNet", "DealerNet")) else 0
            market_ret = market_ret20
            ret20 = r.get("ret20")
            values.append((
                r["Ticker"], r["Date"], r.get("ret1"), ret20, r.get("ret40"),
                r.get("ret60"), r.get("ret80"), r.get("ret100"), r.get("ret120"),
                r.get("ret140"), r.get("ret160"), r.get("ret180"), r.get("ret200"),
                r.get("ret220"), r.get("ret240"),
                _ratio(r.get("ForeignNet"), r.get("Volume")),
                _ratio(r.get("InvestmentNet"), r.get("Volume")),
                _ratio(r.get("DealerNet"), r.get("Volume")), r.get("ThreeNet"), agreement,
                _ratio(r.get("MarginBalance"), r.get("SharesOutstanding_shares")),
                _ratio(r.get("ShortBalance"), r.get("SharesOutstanding_shares")),
                _ratio(r.get("DayTradeVol"), r.get("Volume")),
                _ratio((r.get("DayTradeBuyAmt") or 0) + (r.get("DayTradeSellAmt") or 0),
                       (r.get("Close") or 0) * (r.get("Volume") or 0)),
                None, _ratio(r.get("Volume"), r.get("avg_volume_20")),
                _ratio(r.get("Volume"), r.get("avg_volume_20")), market_ret,
                (float(ret20) - float(market_ret)) if ret20 is not None and market_ret is not None else None,
            ))
        cur.executemany(UPSERT_SQL, values)
        db.refresh_chip_signals(cur, target_date)
        conn.commit()
        return len(values)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-date")
    parser.add_argument("--min-tickers", type=int, default=MIN_TICKERS_DEFAULT)
    parser.add_argument('--refresh-forward-ledger', action='store_true')
    args = parser.parse_args(argv)
    target = _target_date(args.data_date)
    count = refresh(target, args.min_tickers)
    print(f"stock_features: refreshed {count} rows for {target}")
    if args.refresh_forward_ledger:
        # Existing Windows daily/nightly actions invoke this child anew; no
        # daemon restart or second scheduler owner is required. A failure is
        # explicit but cannot block otherwise valid daily market reports.
        script = Path(r'D:\CODEX\AI-Telegram\taiwan_stock_report\forward_validation_log.py')
        receipt = {'data_date': target, 'status': 'failed', 'script': str(script)}
        prediction_script = script.with_name('daily_prediction_refresh.py')
        try:
            prediction = subprocess.run([sys.executable, '-X', 'utf8', str(prediction_script), '--as-of', target],
                                        cwd=script.parent.parent, timeout=PREDICTION_TIMEOUT_SECONDS, capture_output=True,
                                        text=True, encoding='utf-8', errors='replace')
            receipt['prediction_exit_code'] = prediction.returncode
            logs = Path(__file__).parent / '_debug'
            logs.mkdir(exist_ok=True)
            (logs / 'daily_prediction_refresh.log').write_text(prediction.stdout + '\n' + prediction.stderr, encoding='utf-8')
        except (OSError, subprocess.TimeoutExpired) as exc:
            receipt['prediction_error_type'] = type(exc).__name__
        try:
            proc = subprocess.run([sys.executable, '-X', 'utf8', str(script), '--refresh-only', '--date', target],
                                  cwd=script.parent.parent, timeout=120, capture_output=True, text=True,
                                  encoding='utf-8', errors='replace')
            receipt.update(status='ok' if proc.returncode == 0 else 'failed', exit_code=proc.returncode)
        except (OSError, subprocess.TimeoutExpired) as exc:
            receipt['error_type'] = type(exc).__name__
        if receipt.get('prediction_exit_code') != 0:
            receipt['status'] = 'failed'
        dest = Path(__file__).parent / '_debug' / 'forward_validation_refresh.json'
        dest.parent.mkdir(exist_ok=True)
        temp = dest.with_suffix('.tmp')
        temp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(dest)
        print('forward_validation_refresh: ' + json.dumps(receipt, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"stock_features: FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
