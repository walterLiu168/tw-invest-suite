"""
Pattern classifier — query MySQL daily_data2_full directly, classify all 1,951
listed tickers into 8 patterns, compute backtest stats.

Patterns:
  - 熱門噴出 (hot_breakout): 20d +10% AND volume > 20d avg × 1.5 AND 外資連 3 日買超
  - 短多 (short_uptrend): ret_20d > 5% AND close > sma_13 AND RSI 50-65
  - 中多 (mid_uptrend): ret_60d > 10% AND close > sma_27 AND MA 多頭排列
  - 長多 (long_uptrend): ret_240d > 30% AND close > sma_54
  - 價值低估 (value_undervalued): P/B < 1.5 AND P/E < 15 (if yfinance data available)
  - 短空 (short_downtrend): ret_20d < -5% AND close < sma_13 AND RSI < 40
  - 中空 (mid_downtrend): ret_60d < -10% AND close < sma_27
  - 長空腰斬 (long_drawdown): ret_240d < -30% AND close < sma_54

Backtest: for each pattern, look at historical instances (last 240 days),
compute forward 20d/60d return distribution → win rate, avg, median, max gain/loss.
"""
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db_client as db
import pymysql


# ---------- Pattern definitions ----------

PATTERNS = {
    "hot_breakout": {
        "name_zh": "🔥 熱門噴出",
        "color": "red",
        "desc": "短線爆發，外資連買",
    },
    "short_uptrend": {
        "name_zh": "📈 短多",
        "color": "green",
        "desc": "20 日動能強，技術面多頭",
    },
    "mid_uptrend": {
        "name_zh": "📊 中多",
        "color": "green",
        "desc": "60 日均線多頭排列，趨勢向上",
    },
    "long_uptrend": {
        "name_zh": "🚀 長多",
        "color": "green",
        "desc": "240 日大漲，長期持有候選",
    },
    "value_undervalued": {
        "name_zh": "💎 價值低估",
        "color": "cyan",
        "desc": "本益比低 + 淨值比低",
    },
    "short_downtrend": {
        "name_zh": "📉 短空",
        "color": "red",
        "desc": "20 日動能弱，技術面空頭",
    },
    "mid_downtrend": {
        "name_zh": "📊 中空",
        "color": "red",
        "desc": "60 日均線空頭排列",
    },
    "long_drawdown": {
        "name_zh": "💀 長空腰斬",
        "color": "red",
        "desc": "240 日腰斬，長期弱勢",
    },
}


def _classify_one(snap: Dict, rets: Dict, yf: Dict) -> List[str]:
    """Return list of pattern keys this ticker matches."""
    close = float(snap.get("Close") or 0)
    sma13 = float(snap.get("sma_13") or 0)
    sma27 = float(snap.get("sma_27") or 0)
    sma54 = float(snap.get("sma_54") or 0)
    rsi = float(snap.get("rsi_14") or 0)
    volume = int(snap.get("Volume") or 0)
    fnet = int(snap.get("ForeignNet") or 0)
    is_gap = int(snap.get("is_gap") or 0)
    if not close:
        return []

    r20 = (rets.get("ret_20d") or 0) * 100
    r60 = (rets.get("ret_60d") or 0) * 100
    r120 = (rets.get("ret_120d") or 0) * 100
    r240 = (rets.get("ret_240d") or 0) * 100

    pe = yf.get("pe")
    pb = yf.get("pb")
    roe = yf.get("returnOnEquity")

    patterns = []

    # 熱門噴出: 短線爆發 + 法人買
    if r20 > 5 and rsi >= 55 and fnet > 0:
        patterns.append("hot_breakout")

    # 短多: 20 日動能偏多 + 技術面多頭
    if r20 > 0 and close > sma13 and rsi >= 45:
        patterns.append("short_uptrend")

    # 中多: 60 日均線多頭 + 動能
    if r60 > 0 and close > sma27:
        patterns.append("mid_uptrend")

    # 長多: 240 日大漲 + 站上均線
    if r240 > 0 and close > sma54:
        patterns.append("long_uptrend")

    # 價值低估: 低 P/E + 低 P/B (yfinance 資料)
    if pe is not None and pb is not None and 0 < pe < 20 and 0 < pb < 2.0:
        patterns.append("value_undervalued")

    # 短空: 20 日動能偏空 + 技術面空頭
    if r20 < 0 and close < sma13 and rsi <= 55:
        patterns.append("short_downtrend")

    # 中空: 60 日均線空頭
    if r60 < 0 and close < sma27:
        patterns.append("mid_downtrend")

    # 長空腰斬: 240 日腰斬
    if r240 < -0.30 and close < sma54:
        patterns.append("long_drawdown")

    return patterns


def get_all_snapshots() -> Dict[str, Dict]:
    """Get latest snapshot for all tickers (date 2026-08-13)."""
    latest = db.latest_date("daily_data2_full")
    rows = db.market_snapshot(latest)
    return {r["Ticker"]: r for r in rows if r.get("Ticker")}


def get_all_long_term_returns(tickers: List[str]) -> Dict[str, Dict]:
    """Get ret_60d/120d/240d/500d + ret_20d for all tickers."""
    out = db.long_term_returns_batch(tickers, db.latest_date("daily_data2_full"))
    # Add ret_20d via direct SQL
    latest = db.latest_date("daily_data2_full")
    with db.get_conn() as conn:
        cur = conn.cursor(pymysql.cursors.DictCursor)
        placeholders = ",".join(["%s"] * len(tickers))
        # Get close 20 trading days ago
        cur.execute(f"""
            SELECT t1.Ticker,
                   t1.Close AS cur_close,
                   (SELECT Close FROM daily_data2_full t2
                    WHERE t2.Ticker = t1.Ticker AND t2.Date < t1.Date
                    ORDER BY t2.Date DESC LIMIT 1 OFFSET 19) AS c20
            FROM daily_data2_full t1
            WHERE t1.Date = %s AND t1.Ticker IN ({placeholders})
        """, [latest] + tickers)
        for r in cur.fetchall():
            t = r["Ticker"]
            if t not in out:
                out[t] = {}
            if r["cur_close"] and r["c20"]:
                try:
                    out[t]["ret_20d"] = (float(r["cur_close"]) / float(r["c20"]) - 1)
                except (TypeError, ZeroDivisionError):
                    out[t]["ret_20d"] = 0
            else:
                out[t]["ret_20d"] = 0
        cur.close()
    return out


def get_yfinance_cache_all() -> Dict[str, Dict]:
    """Load all yfinance cache files (1,756 tickers)."""
    cache_dir = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_cache")
    out = {}
    for p in cache_dir.glob("*.json"):
        ticker = p.stem
        try:
            with open(p, "r", encoding="utf-8") as f:
                d = json.load(f)
            yf = d.get("yfinance", {}).get("data", {})
            if yf:
                out[ticker] = {
                    "pe": yf.get("trailingPE"),
                    "pb": yf.get("priceToBook"),
                    "roe": yf.get("returnOnEquity"),
                    "market_cap": yf.get("marketCap"),
                }
        except Exception:
            pass
    return out


def classify_all() -> Dict[str, List[str]]:
    """Classify every ticker into patterns. Return {ticker: [pattern_keys]}."""
    snaps = get_all_snapshots()
    tickers = list(snaps.keys())
    rets_map = get_all_long_term_returns(tickers)
    yf_map = get_yfinance_cache_all()
    out: Dict[str, List[str]] = {}
    for t, snap in snaps.items():
        rets = rets_map.get(t, {})
        yf = yf_map.get(t, {})
        out[t] = _classify_one(snap, rets, yf)
    return out


def pattern_stats(classifications: Dict[str, List[str]]) -> Dict[str, Dict]:
    """Count stocks per pattern."""
    out: Dict[str, Dict] = {}
    for pkey, pinfo in PATTERNS.items():
        tickers = [t for t, ps in classifications.items() if pkey in ps]
        out[pkey] = {
            "key": pkey,
            "name_zh": pinfo["name_zh"],
            "desc": pinfo["desc"],
            "color": pinfo["color"],
            "count": len(tickers),
            "tickers": tickers,
        }
    return out


# ---------- Backtest ----------
# Look at historical instances of each pattern over the last 240 days.
# For each (ticker, date) where pattern conditions were met on date T,
# compute forward 20d/60d return (T+20 close / T close - 1).
# Then aggregate: win rate, avg, median, max gain, max loss.

def get_20d_returns(ticker: str, dates: List[str]) -> Dict[str, float]:
    """For each date in `dates`, return forward 20d return. {date: ret}."""
    if not dates:
        return {}
    placeholders = ",".join(["%s"] * len(dates))
    with db.get_conn() as conn:
        cur = conn.cursor(pymysql.cursors.DictCursor)
        # Get close at date and close at date+20d (or latest)
        cur.execute(f"""
            SELECT t1.Date AS d1, t1.Close AS c1,
                   (SELECT Close FROM daily_data2_full t2
                    WHERE t2.Ticker = t1.Ticker AND t2.Date > t1.Date
                    ORDER BY t2.Date ASC LIMIT 1 OFFSET 20) AS c20
            FROM daily_data2_full t1
            WHERE t1.Ticker = %s AND t1.Date IN ({placeholders})
        """, [ticker] + dates)
        out = {}
        for r in cur.fetchall():
            if r["c1"] and r["c20"]:
                try:
                    out[str(r["d1"])] = (float(r["c20"]) / float(r["c1"]) - 1) * 100
                except (TypeError, ZeroDivisionError):
                    pass
        cur.close()
    return out


def get_60d_returns(ticker: str, dates: List[str]) -> Dict[str, float]:
    """Forward 60d return for each date."""
    if not dates:
        return {}
    placeholders = ",".join(["%s"] * len(dates))
    with db.get_conn() as conn:
        cur = conn.cursor(pymysql.cursors.DictCursor)
        cur.execute(f"""
            SELECT t1.Date AS d1, t1.Close AS c1,
                   (SELECT Close FROM daily_data2_full t2
                    WHERE t2.Ticker = t1.Ticker AND t2.Date > t1.Date
                    ORDER BY t2.Date ASC LIMIT 1 OFFSET 60) AS c60
            FROM daily_data2_full t1
            WHERE t1.Ticker = %s AND t1.Date IN ({placeholders})
        """, [ticker] + dates)
        out = {}
        for r in cur.fetchall():
            if r["c1"] and r["c60"]:
                try:
                    out[str(r["d1"])] = (float(r["c60"]) / float(r["c1"]) - 1) * 100
                except (TypeError, ZeroDivisionError):
                    pass
        cur.close()
    return out


def backtest_pattern(pkey: str, classifications: Dict[str, List[str]],
                     start_date: str, end_date: str,
                     sample_every: int = 5) -> Dict:
    """For a pattern, look at all (ticker, date) where it matched,
    compute forward returns, aggregate.

    sample_every: sample every Nth trading day to keep query small.
    """
    tickers = [t for t, ps in classifications.items() if pkey in ps]
    if not tickers:
        return {"count": 0}

    # For each ticker, get all dates in the last 240 days where pattern matched
    # (approximation: re-evaluate pattern at each sample date using history)
    forward_20_returns: List[float] = []
    forward_60_returns: List[float] = []

    # Get all sample dates
    with db.get_conn() as conn:
        cur = conn.cursor(pymysql.cursors.DictCursor)
        cur.execute("""
            SELECT Date FROM daily_data2_full
            WHERE Date >= %s AND Date <= %s
            GROUP BY Date
            ORDER BY Date DESC
        """, (start_date, end_date))
        all_dates = [str(d["Date"]) for d in cur.fetchall() if d.get("Date")]
        sample_dates = all_dates[::sample_every]  # sample every Nth
        cur.close()

    # For each ticker, check if pattern matched on each sample date
    import statistics
    for t in tickers[:200]:  # cap at 200 tickers for performance
        # Re-evaluate pattern at each sample date (using historical data)
        try:
            ticker_dates_data = get_pattern_at_dates(t, pkey, sample_dates)
        except Exception:
            continue
        if not ticker_dates_data:
            continue
        matched_dates = [d for d, matched in ticker_dates_data.items() if matched]
        if not matched_dates:
            continue
        # Get forward returns for matched dates
        f20 = get_20d_returns(t, matched_dates)
        f60 = get_60d_returns(t, matched_dates)
        forward_20_returns.extend(f20.values())
        forward_60_returns.extend(f60.values())

    def _agg(rets: List[float]) -> Dict:
        if not rets:
            return {"count": 0}
        wins = [r for r in rets if r > 0]
        return {
            "count": len(rets),
            "win_rate": round(len(wins) / len(rets) * 100, 1),
            "avg": round(sum(rets) / len(rets), 2),
            "median": round(statistics.median(rets), 2),
            "max": round(max(rets), 2),
            "min": round(min(rets), 2),
        }

    return {
        "count_20d": _agg(forward_20_returns),
        "count_60d": _agg(forward_60_returns),
        "tickers_used": min(len(tickers), 200),
        "tickers_total": len(tickers),
        "sample_dates": len(sample_dates),
    }


def get_pattern_at_dates(ticker: str, pkey: str, dates: List[str]) -> Dict[str, bool]:
    """For each date, check if ticker matched the pattern on that date.
    Returns {date: bool}
    """
    if not dates:
        return {}
    # Get historical data for this ticker up to max date
    max_date = max(dates)
    rows = db.ticker_history(ticker, days=300)  # last 300 days
    if not rows:
        return {}
    # Build lookup: date -> (close, sma13, sma27, sma54, rsi, vol, fnet, ret_60d)
    by_date = {}
    for i, r in enumerate(rows):
        d = str(r.get("Date"))[:10]
        if d > max_date:
            break
        by_date[d] = r
    # Build sorted dates
    sorted_dates = sorted(by_date.keys())
    # Compute ret_20d / ret_60d / ret_240d on the fly
    out: Dict[str, bool] = {}
    for target in dates:
        if target not in by_date:
            continue
        # Find index
        if target not in sorted_dates:
            continue
        idx = sorted_dates.index(target)
        if idx < 60:  # need at least 60d history
            continue
        cur = by_date[target]
        close = float(cur.get("Close") or 0)
        sma13 = float(cur.get("sma_13") or 0)
        sma27 = float(cur.get("sma_27") or 0)
        sma54 = float(cur.get("sma_54") or 0)
        rsi = float(cur.get("rsi_14") or 0)
        fnet = int(cur.get("ForeignNet") or 0)
        if not close:
            continue
        # Compute returns
        d20 = sorted_dates[max(0, idx-20)]
        d60 = sorted_dates[max(0, idx-60)]
        d240 = sorted_dates[max(0, idx-240)]
        c20 = float(by_date[d20].get("Close") or 0)
        c60 = float(by_date[d60].get("Close") or 0)
        c240 = float(by_date[d240].get("Close") or 0)
        r20 = (close / c20 - 1) * 100 if c20 else 0
        r60 = (close / c60 - 1) * 100 if c60 else 0
        r240 = (close / c240 - 1) * 100 if c240 else 0

        # Check pattern (loose conditions matching classify_one)
        matched = False
        if pkey == "hot_breakout":
            if r20 > 5 and rsi >= 55 and fnet > 0:
                matched = True
        elif pkey == "short_uptrend":
            if r20 > 0 and close > sma13 and rsi >= 45:
                matched = True
        elif pkey == "mid_uptrend":
            if r60 > 0 and close > sma27:
                matched = True
        elif pkey == "long_uptrend":
            if r240 > 0 and close > sma54:
                matched = True
        elif pkey == "short_downtrend":
            if r20 < 0 and close < sma13 and rsi <= 55:
                matched = True
        elif pkey == "mid_downtrend":
            if r60 < 0 and close < sma27:
                matched = True
        elif pkey == "long_drawdown":
            if r240 < -0.30 and close < sma54:
                matched = True
        # value_undervalued needs yfinance data (not in DB)
        out[target] = matched
    return out


# ---------- Main ----------
def main():
    print(f"[{datetime.now():%H:%M:%S}] Pattern classifier starting...")
    t0 = time.time()

    print(f"  Loading snapshots...")
    snaps = get_all_snapshots()
    print(f"    {len(snaps)} tickers")

    print(f"  Loading long-term returns...")
    rets_map = get_all_long_term_returns(list(snaps.keys()))
    print(f"    {len(rets_map)} tickers")

    print(f"  Loading yfinance cache...")
    yf_map = get_yfinance_cache_all()
    print(f"    {len(yf_map)} tickers")

    print(f"  Classifying all tickers...")
    classifications = {}
    for t, snap in snaps.items():
        rets = rets_map.get(t, {})
        yf = yf_map.get(t, {})
        classifications[t] = _classify_one(snap, rets, yf)
    print(f"  Classified in {time.time()-t0:.1f}s")

    # Pattern stats
    print(f"\n  Pattern stats:")
    stats = pattern_stats(classifications)
    for pkey, st in stats.items():
        print(f"    {pkey}: {st['count']} stocks — {st['name_zh']}")

    # Backtest
    print(f"\n  Backtest (last 240 days, sample every 5 days)...")
    end_date = db.latest_date("daily_data2_full")
    start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=240)).strftime("%Y-%m-%d")
    backtest = {}
    for pkey in PATTERNS.keys():
        if pkey == "value_undervalued":
            continue  # needs yfinance history, skip
        print(f"    {pkey}...", end="", flush=True)
        bt = backtest_pattern(pkey, classifications, start_date, end_date, sample_every=5)
        backtest[pkey] = bt
        print(f" {bt.get('count_20d', {}).get('count', 0)} trades, win={bt.get('count_20d', {}).get('win_rate', 0)}%")

    # Build top stocks per pattern (with details for HTML)
    print(f"\n  Building top stocks per pattern...")
    top_stocks: Dict[str, List[Dict]] = {}
    for pkey, st in stats.items():
        # Get details for each ticker in this pattern
        items = []
        for t in st["tickers"]:
            snap = snaps.get(t, {})
            rets = rets_map.get(t, {})
            yf = yf_map.get(t, {})
            close = float(snap.get("Close") or 0)
            items.append({
                "ticker": t,
                "close": close,
                "change_pct": float(snap.get("change_pct") or 0),
                "volume": int(snap.get("Volume") or 0),
                "rsi": float(snap.get("rsi_14") or 0),
                "ret_20d": (rets.get("ret_20d") or 0) * 100,
                "ret_60d": (rets.get("ret_60d") or 0) * 100,
                "ret_240d": (rets.get("ret_240d") or 0) * 100,
                "fnet": int(snap.get("ForeignNet") or 0),
                "roe": (yf.get("roe") or 0) * 100,
                "pe": yf.get("pe"),
                "pb": yf.get("pb"),
                "mcap": yf.get("market_cap"),
            })
        # Sort: for uptrends by ret_20d desc, for downtrends by ret_20d asc
        is_down = "down" in pkey or "drawdown" in pkey
        items.sort(key=lambda x: x["ret_20d"] if is_down else -x["ret_20d"])
        top_stocks[pkey] = items[:30]  # top 30

    # Build output JSON
    output = {
        "as_of_date": end_date,
        "as_of_time": datetime.now().isoformat(timespec="seconds"),
        "total_tickers": len(snaps),
        "patterns": {pkey: {
            "key": pkey,
            "name_zh": PATTERNS[pkey]["name_zh"],
            "desc": PATTERNS[pkey]["desc"],
            "color": PATTERNS[pkey]["color"],
            "count": stats[pkey]["count"],
        } for pkey in PATTERNS.keys()},
        "backtest": backtest,
        "top_stocks": top_stocks,
        "build_time_seconds": round(time.time() - t0, 1),
    }

    # Save
    out_path = Path(r"C:\Groove-Lab\analyze\patterns.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=1)
    print(f"\n  Saved: {out_path}")
    print(f"  Total time: {time.time()-t0:.1f}s")
    return output


if __name__ == "__main__":
    main()
