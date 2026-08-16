"""Feature engineering for ML models.

Extracts features from MySQL `daily_data2_full` for any ticker.
Output: pandas DataFrame with features + target.
"""
import sys
from pathlib import Path
from typing import List, Optional

import pymysql
import pandas as pd
import numpy as np


def get_conn():
    return pymysql.connect(host='localhost', user='root', password='1234',
                            database='tw_elec', connect_timeout=10)


def fetch_ohlcv(ticker: str, days: int = 500) -> pd.DataFrame:
    """Fetch OHLCV + technicals + institutional flows for a ticker."""
    with get_conn() as conn:
        cur = conn.cursor(pymysql.cursors.DictCursor)
        cur.execute("""
            SELECT
                Date, Open, High, Low, Close, change_pct, is_gap, Volume,
                ForeignBuy, ForeignSell, ForeignNet,
                InvestmentBuy, InvestmentSell, InvestmentNet,
                DealerBuy, DealerSell, DealerNet, ThreeNet,
                SharesOutstanding_shares, ForeignRatio, ForeignShare,
                MarginBalance, ShortBalance,
                sma_13, sma_27, sma_54, atr_14, rsi_14
            FROM daily_data2_full
            WHERE Ticker = %s
            ORDER BY Date DESC
            LIMIT %s
        """, (ticker, days))
        rows = cur.fetchall()
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df = df.sort_values('Date').reset_index(drop=True)
    df['Date'] = pd.to_datetime(df['Date'])
    # Cast all numeric columns to float (MySQL DECIMAL → Decimal → need conversion)
    numeric_cols = [c for c in df.columns if c != 'Date']
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Build ML features from OHLCV + technicals.

    Features (per row, no future leak):
        - Returns: 1d, 3d, 5d, 10d, 20d
        - Technical: RSI, MA deviation, MACD hist
        - Volume: volume ratio (today / 20d avg)
        - Foreign: 1d/3d/5d net, 20d cumulative
        - Margin: balance change 1d/5d, short balance
        - Volatility: ATR ratio, 20d stddev
    """
    out = df.copy()

    # Returns
    for n in [1, 3, 5, 10, 20]:
        out[f'ret_{n}d'] = out['Close'].pct_change(n)

    # MA deviations
    for n in [13, 27, 54]:
        out[f'ma{n}_dev'] = (out['Close'] - out[f'sma_{n}']) / out[f'sma_{n}']

    # Volume ratio
    out['vol_ratio_20'] = out['Volume'] / out['Volume'].rolling(20).mean()

    # Foreign net (in 1000 shares = 張)
    for n in [1, 3, 5, 20]:
        out[f'foreign_{n}d_k'] = out['ForeignNet'].rolling(n).sum() / 1000.0
    out['foreign_20d_pct'] = out['ForeignNet'].rolling(20).sum() / (out['Volume'].rolling(20).sum() + 1)

    # Three institutional
    out['three_5d_k'] = out['ThreeNet'].rolling(5).sum() / 1000.0

    # Foreign buy/sell ratio
    out['foreign_buy_ratio'] = out['ForeignBuy'] / (out['ForeignBuy'] + out['ForeignSell'] + 1)

    # Margin changes
    out['margin_chg_1d'] = out['MarginBalance'].diff()
    out['margin_chg_5d'] = out['MarginBalance'].diff(5)
    out['short_chg_5d'] = out['ShortBalance'].diff(5)
    out['margin_short_ratio'] = out['ShortBalance'] / (out['MarginBalance'] + 1)

    # Volatility
    out['atr_pct'] = out['atr_14'] / out['Close']
    out['vol_20d'] = out['Close'].pct_change().rolling(20).std()

    # Gap signal (1 if gap up/down, 0 if not)
    out['is_gap'] = out['is_gap'].fillna(0).astype(int)

    return out


def add_target(df: pd.DataFrame, horizon: int = 5) -> pd.DataFrame:
    """Add forward return target (regression) and direction (classification)."""
    df = df.copy()
    df[f'fwd_ret_{horizon}d'] = df['Close'].shift(-horizon) / df['Close'] - 1.0
    df[f'fwd_dir_{horizon}d'] = (df[f'fwd_ret_{horizon}d'] > 0).astype(int)
    return df


def get_feature_columns(df: pd.DataFrame) -> List[str]:
    """Get the list of feature columns (everything except raw OHLCV + target)."""
    exclude = {
        'Date', 'Open', 'High', 'Low', 'Close', 'change_pct', 'Volume',
        'ForeignBuy', 'ForeignSell', 'ForeignNet',
        'InvestmentBuy', 'InvestmentSell', 'InvestmentNet',
        'DealerBuy', 'DealerSell', 'DealerNet', 'ThreeNet',
        'SharesOutstanding_shares', 'ForeignShare',
        'MarginBalance', 'ShortBalance',
        'sma_13', 'sma_27', 'sma_54', 'rsi_14', 'atr_14',
    }
    exclude |= {c for c in df.columns if c.startswith('fwd_')}
    return [c for c in df.columns if c not in exclude]


def build_dataset(ticker: str, days: int = 500, horizon: int = 5,
                  dropna: bool = True) -> Optional[pd.DataFrame]:
    """Build complete dataset for one ticker."""
    df = fetch_ohlcv(ticker, days=days)
    if len(df) < 60:
        return None
    df = build_features(df)
    df = add_target(df, horizon=horizon)
    if dropna:
        df = df.dropna().reset_index(drop=True)
    return df


def build_dataset_multi(tickers: List[str], days: int = 500, horizon: int = 5,
                        min_rows: int = 60) -> pd.DataFrame:
    """Build combined dataset for multiple tickers."""
    frames = []
    for t in tickers:
        d = build_dataset(t, days=days, horizon=horizon)
        if d is not None and len(d) >= min_rows:
            d['ticker'] = t
            frames.append(d)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


# ============== CLI ==============
if __name__ == '__main__':
    # Test with 2330
    print("Building features for 2330 (TSMC)...", file=sys.stderr)
    df = build_dataset('2330', days=500)
    if df is not None:
        feat_cols = get_feature_columns(df)
        print(f"  Rows: {len(df)}, Features: {len(feat_cols)}", file=sys.stderr)
        print(f"  Date range: {df['Date'].min()} to {df['Date'].max()}", file=sys.stderr)
        print(f"  Target distribution:", file=sys.stderr)
        target = f'fwd_dir_5d'
        print(f"    Up: {(df[target] == 1).sum()}, Down: {(df[target] == 0).sum()}", file=sys.stderr)
        print(f"  Sample features:", file=sys.stderr)
        print(df[feat_cols].describe().T[['mean', 'std', 'min', 'max']].round(4).to_string(), file=sys.stderr)
    else:
        print("  Not enough data", file=sys.stderr)
