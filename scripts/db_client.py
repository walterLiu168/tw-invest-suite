"""
MySQL data layer for tw-invest-suite.

Reuses existing tables in the user's `tw_elec` database:
- `daily_data2_full`        — daily OHLCV + institutional + margin + technicals (primary)
- `industry_type`           — ticker → industry mapping
- `chipscore_daily`         — chip-derived signals (Inv_FirstIn, VolumeBurst, etc.)
- `stock_features`          — return features (ret_1d … ret_240d, foreign_net_ratio, etc.)
- `stock_news`              — news with sentiment_score, related_tickers
- `topn_daily`              — daily TopN picks with reason

Goal: never call an external API if DB has the data. Fallback to FinMind/TWSE
only when DB is stale or the dataset is missing.
"""
import os
from contextlib import contextmanager
from typing import Dict, List, Optional, Tuple

import pymysql
import pymysql.cursors


DB_CONFIG = {
    "host": os.environ.get("TW_DB_HOST", "localhost"),
    "user": os.environ.get("TW_DB_USER", "root"),
    "password": os.environ.get("TW_DB_PASSWORD", "1234"),
    "database": os.environ.get("TW_DB_NAME", "tw_elec"),
    "charset": "utf8mb4",
}


@contextmanager
def get_conn():
    conn = pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_cursor():
    with get_conn() as conn:
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise


# ---------- date helpers ----------

def latest_date(table: str = "daily_data2_full") -> str:
    """Return the most recent date in the given table (str YYYY-MM-DD)."""
    with get_cursor() as cur:
        cur.execute(f"SELECT MAX(Date) AS d FROM {table}")
        row = cur.fetchone()
    return str(row["d"]) if row and row["d"] else ""


def is_stale(table: str = "daily_data2_full", max_age_days: int = 3) -> bool:
    """True if the latest date in the table is more than `max_age_days` old."""
    from datetime import datetime, timedelta
    ld = latest_date(table)
    if not ld:
        return True
    latest = datetime.strptime(ld, "%Y-%m-%d").date()
    return (datetime.now().date() - latest) > timedelta(days=max_age_days)


# ---------- core screener queries ----------

def market_snapshot(target_date: Optional[str] = None) -> List[Dict]:
    """Latest snapshot of every ticker in daily_data2_full.

    Returns one row per ticker with OHLCV, institutional net, margin, technicals.
    """
    if not target_date:
        target_date = latest_date("daily_data2_full")
    sql = f"""
        SELECT
            Ticker, Date, Open, High, Low, Close, change_pct, Volume,
            ForeignNet, InvestmentNet, DealerNet, ThreeNet,
            MarginBalance, ShortBalance,
            ForeignRatio, SharesOutstanding_shares,
            sma_13, sma_27, sma_54, atr_14, rsi_14, is_gap
        FROM daily_data2_full
        WHERE Date = %s
          AND Close > 0
          AND Ticker REGEXP '^[0-9]{{4}}$|^[0-9]{{4}}[A-Z]$'
        ORDER BY Ticker
    """
    with get_cursor() as cur:
        cur.execute(sql, (target_date,))
        return cur.fetchall()


def ticker_history(ticker: str, days: int = 240) -> List[Dict]:
    """Last `days` trading days of OHLCV for one ticker (asc by date)."""
    sql = """
        SELECT Date, Open, High, Low, Close, Volume,
               ForeignNet, InvestmentNet, DealerNet, ThreeNet,
               MarginBalance, ShortBalance,
               sma_13, sma_27, sma_54, rsi_14, atr_14
        FROM daily_data2_full
        WHERE Ticker = %s
        ORDER BY Date DESC
        LIMIT %s
    """
    with get_cursor() as cur:
        cur.execute(sql, (ticker, days))
        rows = cur.fetchall()
    return list(reversed(rows))  # ascending by date


def market_cap_estimate(ticker: str) -> Optional[float]:
    """Estimate market cap from shares_master × latest close price.

    Returns None if shares or price not available.
    """
    sql_shares = "SELECT shares_outstanding FROM shares_master WHERE ticker = %s"
    sql_price = "SELECT Close FROM daily_data2_full WHERE Ticker = %s ORDER BY Date DESC LIMIT 1"
    with get_cursor() as cur:
        cur.execute(sql_shares, (ticker,))
        r = cur.fetchone()
        if not r or not r.get("shares_outstanding"):
            return None
        shares = float(r["shares_outstanding"])
        cur.execute(sql_price, (ticker,))
        pr = cur.fetchone()
        if not pr or not pr.get("Close"):
            return None
        price = float(pr["Close"])
    return shares * price


def ticker_features(ticker: str, latest_n: int = 1) -> List[Dict]:
    """Return `latest_n` rows of stock_features for the ticker (most recent)."""
    sql = """
        SELECT * FROM stock_features
        WHERE ticker = %s
        ORDER BY date DESC
        LIMIT %s
    """
    with get_cursor() as cur:
        cur.execute(sql, (ticker, latest_n))
        return cur.fetchall()


def chip_features(ticker: str, latest_n: int = 5) -> List[Dict]:
    """Recent chip-derived signals from chipscore_daily."""
    sql = """
        SELECT * FROM chipscore_daily
        WHERE Ticker = %s
        ORDER BY Date DESC
        LIMIT %s
    """
    with get_cursor() as cur:
        cur.execute(sql, (ticker, latest_n))
        return cur.fetchall()


def industry_for(ticker: str) -> str:
    """Look up industry classification. Empty string if not found."""
    with get_cursor() as cur:
        cur.execute("SELECT industry FROM industry_type WHERE ticker = %s LIMIT 1", (ticker,))
        row = cur.fetchone()
    return row["industry"] if row else ""


def all_industries() -> Dict[str, Dict[str, str]]:
    """ticker → {industry, company} (full table)."""
    with get_cursor() as cur:
        cur.execute("SELECT ticker, industry, company FROM industry_type")
        return {r["ticker"]: {"industry": r["industry"], "company": r["company"]} for r in cur.fetchall()}


def close_on_or_before(ticker: str, cutoff_date: str) -> Optional[float]:
    """Most recent close for a ticker on or before cutoff_date. For long-term return calc."""
    sql = """
        SELECT Close FROM daily_data2_full
        WHERE Ticker = %s AND Date <= %s AND Close > 0
        ORDER BY Date DESC LIMIT 1
    """
    with get_cursor() as cur:
        cur.execute(sql, (ticker, cutoff_date))
        row = cur.fetchone()
    return float(row["Close"]) if row and row.get("Close") else None


def long_term_returns_batch(tickers: List[str], target_date: str) -> Dict[str, Dict[str, float]]:
    """For each ticker, compute ret against prior ~60d/120d/240d/500d dates.

    Returns {ticker: {ret_60d, ret_120d, ret_240d, ret_500d}}.
    Single round-trip per ticker (4 small queries), batched in a loop.
    """
    from datetime import datetime, timedelta
    end = datetime.strptime(target_date, "%Y-%m-%d")
    cutoffs = {
        "ret_60d": (end - timedelta(days=60)).strftime("%Y-%m-%d"),
        "ret_120d": (end - timedelta(days=120)).strftime("%Y-%m-%d"),
        "ret_240d": (end - timedelta(days=240)).strftime("%Y-%m-%d"),
        "ret_500d": (end - timedelta(days=500)).strftime("%Y-%m-%d"),
    }
    out: Dict[str, Dict[str, float]] = {t: {} for t in tickers}
    # Get current close for all tickers in one query
    placeholders = ",".join(["%s"] * len(tickers))
    sql = f"""
        SELECT Ticker, Close FROM daily_data2_full
        WHERE Ticker IN ({placeholders}) AND Date = %s
    """
    with get_cursor() as cur:
        cur.execute(sql, (*tickers, target_date))
        cur_close = {r["Ticker"]: float(r["Close"]) for r in cur.fetchall() if r.get("Close")}
    # For each cutoff, query the historical close
    for label, cutoff in cutoffs.items():
        sql = f"""
            SELECT t.Ticker, t.Close FROM daily_data2_full t
            INNER JOIN (
                SELECT Ticker, MAX(Date) AS max_date
                FROM daily_data2_full
                WHERE Ticker IN ({placeholders}) AND Date <= %s AND Close > 0
                GROUP BY Ticker
            ) m ON t.Ticker = m.Ticker AND t.Date = m.max_date
        """
        with get_cursor() as cur:
            cur.execute(sql, (*tickers, cutoff))
            prior = {r["Ticker"]: float(r["Close"]) for r in cur.fetchall() if r.get("Close")}
        for t in tickers:
            if t in cur_close and t in prior and prior[t] > 0:
                out[t][label] = (cur_close[t] - prior[t]) / prior[t]
    return out


def recent_news(ticker: str, limit: int = 5) -> List[Dict]:
    """Latest news mentioning the ticker. related_tickers is a JSON array string."""
    sql = """
        SELECT id, title, source, published_at, sentiment_score, summary
        FROM stock_news
        WHERE related_tickers LIKE %s
        ORDER BY published_at DESC
        LIMIT %s
    """
    with get_cursor() as cur:
        cur.execute(sql, (f'%"{ticker}"%', limit))
        return cur.fetchall()


def shares_outstanding(ticker: str) -> Optional[int]:
    """Most recent SharesOutstanding_shares for a ticker. Try daily_data2_full,
    then shares_master (broader coverage)."""
    with get_cursor() as cur:
        cur.execute(
            """SELECT SharesOutstanding_shares FROM daily_data2_full
               WHERE Ticker = %s AND SharesOutstanding_shares IS NOT NULL
               ORDER BY Date DESC LIMIT 1""",
            (ticker,),
        )
        row = cur.fetchone()
        if row and row.get("SharesOutstanding_shares"):
            return int(row["SharesOutstanding_shares"])
        # Fallback to shares_master
        cur.execute(
            """SELECT SharesOutstanding_shares FROM shares_master
               WHERE Ticker = %s LIMIT 1""",
            (ticker,),
        )
        row = cur.fetchone()
    return int(row["SharesOutstanding_shares"]) if row and row.get("SharesOutstanding_shares") else None


def all_shares_outstanding() -> Dict[str, int]:
    """Bulk lookup ticker → shares outstanding (from shares_master)."""
    with get_cursor() as cur:
        cur.execute("SELECT Ticker, SharesOutstanding_shares FROM shares_master")
        return {r["Ticker"]: int(r["SharesOutstanding_shares"])
                for r in cur.fetchall() if r.get("SharesOutstanding_shares")}


# ---------- batch queries (for fast full-market scans) ----------

def all_latest_chipscore(target_date: Optional[str] = None) -> Dict[str, Dict]:
    """ticker → chip row (most recent date). One round-trip."""
    if not target_date:
        target_date = latest_date("chipscore_daily")
    sql = f"""
        SELECT * FROM chipscore_daily
        WHERE Date = %s
    """
    with get_cursor() as cur:
        cur.execute(sql, (target_date,))
        return {r["Ticker"]: r for r in cur.fetchall()}


def all_latest_features(target_date: Optional[str] = None) -> Dict[str, Dict]:
    """ticker → feature row (most recent date). One round-trip."""
    if not target_date:
        # Find the latest date present in stock_features
        with get_cursor() as cur:
            cur.execute("SELECT MAX(date) AS d FROM stock_features")
            target_date = str(cur.fetchone()["d"])
    sql = """
        SELECT * FROM stock_features
        WHERE date = %s
    """
    with get_cursor() as cur:
        cur.execute(sql, (target_date,))
        return {r["ticker"]: r for r in cur.fetchall()}


def news_for_tickers(tickers: List[str], limit_per: int = 10, days: int = 5) -> Dict[str, List[Dict]]:
    """Get recent news for a small set of tickers (one query per ticker).

    Only call this for the final ~24 picks, not the full universe.
    """
    from datetime import datetime, timedelta
    cutoff = datetime.now() - timedelta(days=days)
    out: Dict[str, List[Dict]] = {t: [] for t in tickers}
    for t in tickers:
        sql = """
            SELECT id, title, source, published_at, sentiment_score, summary
            FROM stock_news
            WHERE related_tickers LIKE %s
              AND published_at >= %s
            ORDER BY published_at DESC
            LIMIT %s
        """
        with get_cursor() as cur:
            cur.execute(sql, (f'%"{t}"%', cutoff, limit_per))
            out[t] = cur.fetchall()
    return out


# ---------- quick smoke test ----------

if __name__ == "__main__":
    print(f"latest daily_data2_full date: {latest_date('daily_data2_full')}")
    print(f"latest daily_data2 date:     {latest_date('daily_data2')}")
    print(f"latest daily_data date:      {latest_date('daily_data')}")
    print(f"daily_data2_full stale?     {is_stale('daily_data2_full', 3)}")
    print(f"industry for 2330:           {industry_for('2330')}")
    snap = market_snapshot()
    print(f"snapshot rows:               {len(snap)}")
    if snap:
        print(f"sample row 2330:             {next((r for r in snap if r['Ticker'] == '2330'), None)}")
    print(f"2330 history (5d):")
    for r in ticker_history("2330", days=5):
        print(f"  {r['Date']} C={r['Close']} V={r['Volume']} FNet={r['ForeignNet']} Rsi={r['rsi_14']}")
