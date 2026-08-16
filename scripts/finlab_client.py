"""
FinLab client — Taiwan stock fundamentals (ROE, monthly revenue, broker data).

Auth: read FINLAB_API_TOKEN from environment (~/.env supported via python-dotenv).
Tier: free tier has 500 MB/day, and historical data may be limited to ~2018.
      broker_transactions (raw + etl) is VIP only.

Usage:
    import finlab_client as fl
    roe = fl.roe()                  # DataFrame index=date, columns=stock_id
    rev = fl.monthly_revenue()
    df_2330 = fl.roe_for("2330")
"""
import os
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd


# ---- token resolution ----

def _load_token() -> str:
    """Read FINLAB_API_TOKEN from env, falling back to ~/.env."""
    # 1. Direct env (highest priority)
    tok = os.environ.get("FINLAB_API_TOKEN", "").strip()
    if tok:
        return tok
    # 2. ~/.env via dotenv if available
    try:
        from dotenv import load_dotenv
        load_dotenv(Path.home() / ".env")
        tok = os.environ.get("FINLAB_API_TOKEN", "").strip()
        if tok:
            return tok
    except ImportError:
        pass
    raise RuntimeError(
        "FINLAB_API_TOKEN not found. Set it in env or in ~/.env "
        "(get token at https://www.finlab.finance/ → user settings)"
    )


def _ensure_auth() -> None:
    """Make sure FINLAB_API_TOKEN is loaded into the environment.
    Newer finlab versions auto-read FINLAB_API_TOKEN at import time; older
    versions need finlab.login(token). We try the env-var route first; if a
    data call later complains about auth, the user can patch in login().

    Must be called BEFORE `from finlab import data` is hit in the user's
    process — but since we import lazily inside each fetcher, calling this
    upfront works.
    """
    try:
        tok = _load_token()
        os.environ["FINLAB_API_TOKEN"] = tok
    except RuntimeError:
        pass


# ---- public data fetchers ----

def _data():
    from finlab import data
    return data


def roe() -> pd.DataFrame:
    """Return ROE 稅後 DataFrame. Index=date (Q1, Q2, ...), columns=stock_id."""
    _ensure_auth()
    return _data().get("fundamental_features:ROE稅後")


def monthly_revenue() -> pd.DataFrame:
    """Return monthly revenue DataFrame. Index=date, columns=stock_id."""
    _ensure_auth()
    return _data().get("monthly_revenue:當月營收")


def roe_for(stock_id: str) -> pd.Series:
    """Return ROE history for one stock (dropna, sorted asc)."""
    df = roe()
    if stock_id not in df.columns:
        return pd.Series(dtype=float)
    return df[stock_id].dropna().sort_index()


def monthly_revenue_for(stock_id: str, months: int = 12) -> pd.Series:
    """Return last `months` months of revenue for one stock (sorted desc)."""
    df = monthly_revenue()
    if stock_id not in df.columns:
        return pd.Series(dtype=float)
    s = df[stock_id].dropna().sort_index(ascending=False).head(months)
    return s.sort_index()


def roe_for_dict(stock_id: str) -> List[Dict]:
    """ROE as a list of {date, value} dicts (for the report builder)."""
    s = roe_for(stock_id)
    return [{"date": str(idx), "value": float(v)} for idx, v in s.items()]


def monthly_revenue_for_dict(stock_id: str, months: int = 12) -> List[Dict]:
    """Monthly revenue as list of {date, value, yoy} dicts.

    yoy is computed against the same month one year prior.
    """
    s = monthly_revenue_for(stock_id, months=months + 13)  # extra for YoY baseline
    items = [{"date": str(idx), "value": float(v)} for idx, v in s.items()]
    # Add YoY (12 months back)
    for i, item in enumerate(items):
        idx = pd.Timestamp(item["date"])
        prior = idx - pd.DateOffset(months=12)
        if prior in s.index:
            prior_val = float(s.loc[prior])
            if prior_val:
                item["yoy"] = (item["value"] / prior_val - 1) * 100
    return items


def price_history(stock_id: str) -> List[Dict]:
    """Return OHLCV history from FinLab's price:收盤價 etc., in the same
    shape as twse_client / tpex_client (date, open, max, min, close, volume).
    Free tier data is limited to ~2018.
    """
    _ensure_auth()
    try:
        close = _data().get("price:收盤價")
        open_p = _data().get("price:開盤價")
        high = _data().get("price:最高價")
        low = _data().get("price:最低價")
        vol = _data().get("price:成交股數")
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"FinLab price fetch failed: {e}")
    if stock_id not in close.columns:
        return []
    out: List[Dict] = []
    for idx in close.index:
        c = close.at[idx, stock_id]
        if pd.isna(c):
            continue
        try:
            o = float(open_p.at[idx, stock_id]) if stock_id in open_p.columns else float(c)
            h = float(high.at[idx, stock_id]) if stock_id in high.columns else float(c)
            lo = float(low.at[idx, stock_id]) if stock_id in low.columns else float(c)
            v = int(vol.at[idx, stock_id]) if stock_id in vol.columns else 0
        except (KeyError, ValueError, TypeError):
            continue
        out.append({
            "date": pd.Timestamp(idx).strftime("%Y-%m-%d"),
            "stock_id": stock_id,
            "open": o,
            "max": h,
            "min": lo,
            "close": float(c),
            "Trading_Volume": v,
        })
    return out


# ---- broker data (VIP only, will raise on free tier) ----

def broker_transactions_raw():
    """Raw broker transactions (VIP only)."""
    _ensure_auth()
    return _data().get("broker_transactions")


def broker_top15_buy():
    """Top 15 brokers' net buy per stock per day (VIP only)."""
    _ensure_auth()
    return _data().get("etl:broker_transactions:top15_buy")


def broker_top15_sell():
    """Top 15 brokers' net sell per stock per day (VIP only)."""
    _ensure_auth()
    return _data().get("etl:broker_transactions:top15_sell")


def broker_buy_sell_ratio():
    """Buy-sell ratio of top 15 brokers per stock per day (VIP only)."""
    _ensure_auth()
    return _data().get("etl:broker_transactions:buy_sell_ratio")


def broker_balance_index():
    """Balance index = buy / (buy + sell) of top 15 brokers (VIP only)."""
    _ensure_auth()
    return _data().get("etl:broker_transactions:balance_index")


if __name__ == "__main__":
    import sys
    sid = sys.argv[1] if len(sys.argv) > 1 else "2330"
    print(f"[smoke] Fetching ROE for {sid}...")
    s = roe_for(sid)
    print(f"  rows: {len(s)}")
    if not s.empty:
        print(f"  latest: {s.iloc[-1]:.2f} on {s.index[-1]}")
    print()
    print(f"[smoke] Fetching monthly revenue for {sid}...")
    items = monthly_revenue_for_dict(sid, months=6)
    for it in items:
        yoy = it.get("yoy")
        yoy_s = f"  YoY {yoy:+.1f}%" if yoy is not None else ""
        print(f"  {it['date']}: {it['value']:>20,.0f}{yoy_s}")
