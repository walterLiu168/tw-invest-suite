"""XGBoost direction predictor with walk-forward backtest.

Trains a binary classifier to predict 5-day forward direction (up/down).
Uses rolling walk-forward validation (no future leak).

Usage:
    python -m xgb_predictor --tickers 2330 2317 2454     # specific
    python -m xgb_predictor --top 100                    # top 100 by volume
    python -m xgb_predictor --tickers 2330 --horizon 5 --train-window 252
"""
import sys
import argparse
import json
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
from sklearn.metrics import roc_auc_score

from features import build_dataset_multi, get_feature_columns, get_conn


# ============== Config ==============
DEFAULT_HORIZON = 5           # 5-day forward return
DEFAULT_TRAIN_WINDOW = 252    # ~1 year of training data
DEFAULT_TEST_WINDOW = 60      # ~3 months of test data
DEFAULT_STEP = 30             # walk forward 30 days at a time


# ============== Single-ticker backtest ==============

def walk_forward_one(df: pd.DataFrame, horizon: int = DEFAULT_HORIZON,
                      train_window: int = DEFAULT_TRAIN_WINDOW,
                      test_window: int = DEFAULT_TEST_WINDOW,
                      step: int = DEFAULT_STEP,
                      target_col: str = None) -> dict:
    """Walk-forward validation for one ticker. Returns metrics dict."""
    if target_col is None:
        target_col = f'fwd_dir_{horizon}d'
    feature_cols = get_feature_columns(df)
    if df.empty or len(df) < train_window + test_window:
        return {'skipped': True, 'reason': 'insufficient data'}

    dates = df['Date'].values
    X = df[feature_cols].values
    y = df[target_col].values

    all_preds = []
    all_truth = []
    all_proba = []
    fold_metrics = []

    n = len(df)
    start = train_window
    while start + test_window <= n:
        train_idx = range(max(0, start - train_window), start)
        test_idx = range(start, start + test_window)

        X_train, y_train = X[train_idx], y[train_idx]
        X_test, y_test = X[test_idx], y[test_idx]

        # Skip if train has only one class
        if len(np.unique(y_train)) < 2:
            start += step
            continue

        # XGBoost (CPU, n_jobs=-1)
        model = XGBClassifier(
            n_estimators=200,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            n_jobs=-1,
            tree_method='hist',
            eval_metric='logloss',
            verbosity=0,
        )
        model.fit(X_train, y_train, verbose=False)

        preds = model.predict(X_test)
        proba = model.predict_proba(X_test)[:, 1]

        all_preds.extend(preds.tolist())
        all_truth.extend(y_test.tolist())
        all_proba.extend(proba.tolist())

        # Fold metrics
        try:
            auc = roc_auc_score(y_test, proba)
        except ValueError:
            auc = float('nan')
        fold_metrics.append({
            'start_date': str(dates[start])[:10],
            'end_date': str(dates[min(start + test_window, n) - 1])[:10],
            'accuracy': float(accuracy_score(y_test, preds)),
            'auc': float(auc),
            'n_test': int(len(y_test)),
        })
        start += step

    if not all_preds:
        return {'skipped': True, 'reason': 'no folds'}

    overall_acc = accuracy_score(all_truth, all_preds)
    overall_prec = precision_score(all_truth, all_preds, zero_division=0)
    overall_rec = recall_score(all_truth, all_preds, zero_division=0)
    overall_f1 = f1_score(all_truth, all_preds, zero_division=0)
    try:
        overall_auc = roc_auc_score(all_truth, all_proba)
    except ValueError:
        overall_auc = float('nan')

    return {
        'n_folds': len(fold_metrics),
        'total_samples': len(all_preds),
        'overall': {
            'accuracy': float(overall_acc),
            'precision': float(overall_prec),
            'recall': float(overall_rec),
            'f1': float(overall_f1),
            'auc': float(overall_auc),
        },
        'folds': fold_metrics,
    }


# ============== Feature importance ==============

def get_feature_importance(df: pd.DataFrame, target_col: str = 'fwd_dir_5d') -> pd.DataFrame:
    """Train on all data, return feature importance."""
    feature_cols = get_feature_columns(df)
    X = df[feature_cols].values
    y = df[target_col].values

    model = XGBClassifier(
        n_estimators=200, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, random_state=42, n_jobs=-1,
        tree_method='hist', verbosity=0,
    )
    model.fit(X, y, verbose=False)
    imp = pd.DataFrame({
        'feature': feature_cols,
        'importance': model.feature_importances_,
    }).sort_values('importance', ascending=False)
    return imp


# ============== Top tickers by volume ==============

def get_top_tickers(n: int = 100) -> list:
    """Get top N tickers by 20-day average volume."""
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT Ticker, AVG(Volume) AS avg_vol
            FROM daily_data2_full
            WHERE Date >= (SELECT MAX(Date) FROM daily_data2_full) - INTERVAL 60 DAY
            GROUP BY Ticker
            ORDER BY avg_vol DESC
            LIMIT %s
        """, (n,))
        return [r[0] for r in cur.fetchall()]


# ============== Main ==============

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs='+', help="Specific tickers")
    parser.add_argument("--top", type=int, help="Top N by volume")
    parser.add_argument("--horizon", type=int, default=DEFAULT_HORIZON)
    parser.add_argument("--train-window", type=int, default=DEFAULT_TRAIN_WINDOW)
    parser.add_argument("--test-window", type=int, default=DEFAULT_TEST_WINDOW)
    parser.add_argument("--step", type=int, default=DEFAULT_STEP)
    parser.add_argument("--out", type=Path, help="Output JSON path")
    parser.add_argument("--feat-imp", action="store_true", help="Also output feature importance")
    args = parser.parse_args()

    if args.tickers:
        tickers = args.tickers
    elif args.top:
        tickers = get_top_tickers(args.top)
        print(f"[{datetime.now():%H:%M:%S}] Using top {args.top} tickers by volume", file=sys.stderr)
    else:
        print("Need --tickers or --top", file=sys.stderr)
        sys.exit(1)

    print(f"[{datetime.now():%H:%M:%S}] Building dataset for {len(tickers)} tickers...", file=sys.stderr)
    df = build_dataset_multi(tickers, days=800, horizon=args.horizon)
    if df.empty:
        print("Empty dataset", file=sys.stderr)
        sys.exit(1)
    print(f"  Total rows: {len(df)}, tickers: {df['ticker'].nunique()}", file=sys.stderr)

    results = {}
    feat_imps = []
    for ticker, grp in df.groupby('ticker'):
        grp = grp.sort_values('Date').reset_index(drop=True)
        if len(grp) < args.train_window + args.test_window:
            results[ticker] = {'skipped': True, 'reason': 'insufficient data'}
            continue
        res = walk_forward_one(grp, horizon=args.horizon,
                                train_window=args.train_window,
                                test_window=args.test_window,
                                step=args.step)
        results[ticker] = res
        if args.feat_imp and len(grp) > 60:
            try:
                imp = get_feature_importance(grp)
                imp['ticker'] = ticker
                feat_imps.append(imp)
            except Exception as e:
                print(f"  feat_imp failed for {ticker}: {e}", file=sys.stderr)

        # Quick progress
        if 'overall' in res:
            o = res['overall']
            print(f"  {ticker}: acc={o['accuracy']:.3f} auc={o['auc']:.3f} f1={o['f1']:.3f} ({res['n_folds']} folds)", file=sys.stderr)

    # Aggregate
    valid = [r for r in results.values() if 'overall' in r]
    if valid:
        avg_acc = np.mean([r['overall']['accuracy'] for r in valid])
        avg_auc = np.mean([r['overall']['auc'] for r in valid if not np.isnan(r['overall']['auc'])])
        avg_f1 = np.mean([r['overall']['f1'] for r in valid])
        print(f"\n[{datetime.now():%H:%M:%S}] Aggregate ({len(valid)} tickers):", file=sys.stderr)
        print(f"  Avg accuracy: {avg_acc:.3f}", file=sys.stderr)
        print(f"  Avg AUC:      {avg_auc:.3f}", file=sys.stderr)
        print(f"  Avg F1:       {avg_f1:.3f}", file=sys.stderr)
    else:
        print("No valid results", file=sys.stderr)

    # Save
    out_path = args.out or Path("outputs/ml/xgb_backtest.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    out_data = {
        'config': {
            'tickers': tickers,
            'horizon': args.horizon,
            'train_window': args.train_window,
            'test_window': args.test_window,
            'step': args.step,
        },
        'aggregate': {
            'n_tickers': len(valid),
            'avg_accuracy': float(avg_acc) if valid else None,
            'avg_auc': float(avg_auc) if valid and not np.isnan(avg_auc) else None,
            'avg_f1': float(avg_f1) if valid else None,
        },
        'per_ticker': results,
    }
    if feat_imps:
        all_imp = pd.concat(feat_imps, ignore_index=True)
        avg_imp = all_imp.groupby('feature')['importance'].mean().sort_values(ascending=False)
        out_data['feature_importance'] = avg_imp.to_dict()
        print(f"\nTop 10 features (avg importance across tickers):", file=sys.stderr)
        for feat, imp in avg_imp.head(10).items():
            print(f"  {feat}: {imp:.4f}", file=sys.stderr)

    out_path.write_text(json.dumps(out_data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\n[{datetime.now():%H:%M:%S}] Saved to {out_path}", file=sys.stderr)


if __name__ == '__main__':
    main()
