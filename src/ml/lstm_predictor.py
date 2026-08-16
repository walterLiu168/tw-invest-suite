"""LSTM sequence predictor — skeleton.

Note: PyTorch is not installed by default. To use this:
    pip install torch --index-url https://download.pytorch.org/whl/cu121

Design:
    - Input: 60-day sequence of features per ticker
    - LSTM(64, 2 layers) → Linear(1) → sigmoid
    - Target: 5-day forward direction (binary)
    - Training: walk-forward per ticker
    - GPU: RTX 3060 Ti 8GB can handle ~5-10 tickers per batch
"""
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import List

import numpy as np
import pandas as pd

from features import build_dataset_multi, get_feature_columns, get_conn


SEQ_LEN = 60         # 60 days input sequence
HORIZON = 5          # predict 5-day forward direction
DEFAULT_BATCH = 32
DEFAULT_EPOCHS = 20


def build_sequences(df: pd.DataFrame, feature_cols: List[str],
                     seq_len: int = SEQ_LEN, horizon: int = HORIZON) -> tuple:
    """Build (X, y) sequences for LSTM.

    X: (n_samples, seq_len, n_features)
    y: (n_samples,) binary direction
    """
    target_col = f'fwd_dir_{horizon}d'
    if target_col not in df.columns:
        return np.array([]), np.array([])

    arr = df[feature_cols].values
    targets = df[target_col].values
    n = len(df)
    if n < seq_len + horizon:
        return np.array([]), np.array([])

    Xs, ys = [], []
    for i in range(seq_len, n - horizon):
        Xs.append(arr[i - seq_len:i])
        ys.append(targets[i])
    return np.array(Xs, dtype=np.float32), np.array(ys, dtype=np.float32)


def build_lstm_model(n_features: int, seq_len: int = SEQ_LEN):
    """Build LSTM model. Requires torch."""
    import torch
    import torch.nn as nn

    class LSTMClassifier(nn.Module):
        def __init__(self, n_features, hidden=64, layers=2, dropout=0.2):
            super().__init__()
            self.lstm = nn.LSTM(n_features, hidden, num_layers=layers,
                                 batch_first=True, dropout=dropout)
            self.fc = nn.Linear(hidden, 1)
            self.sigmoid = nn.Sigmoid()

        def forward(self, x):
            # x: (batch, seq, features)
            out, _ = self.lstm(x)
            out = out[:, -1, :]  # last time step
            out = self.fc(out)
            return self.sigmoid(out).squeeze(-1)

    model = LSTMClassifier(n_features)
    return model


def train_lstm_one_ticker(df: pd.DataFrame, epochs: int = DEFAULT_EPOCHS,
                           lr: float = 1e-3, device: str = 'cuda'):
    """Train LSTM on one ticker (walk-forward last 20% as test)."""
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset

    feature_cols = get_feature_columns(df)
    X, y = build_sequences(df, feature_cols)
    if len(X) == 0:
        return None, None

    n = len(X)
    n_test = int(n * 0.2)
    X_train, y_train = X[:-n_test], y[:-n_test]
    X_test, y_test = X[-n_test:], y[-n_test:]

    # Standardize features
    mean = X_train.mean(axis=(0, 1), keepdims=True)
    std = X_train.std(axis=(0, 1), keepdims=True) + 1e-8
    X_train = (X_train - mean) / std
    X_test = (X_test - mean) / std

    train_ds = TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train))
    train_dl = DataLoader(train_ds, batch_size=DEFAULT_BATCH, shuffle=True)

    model = build_lstm_model(X.shape[2]).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.BCELoss()

    for epoch in range(epochs):
        model.train()
        for xb, yb in train_dl:
            xb, yb = xb.to(device), yb.to(device)
            pred = model(xb)
            loss = criterion(pred, yb)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

    # Eval
    model.eval()
    with torch.no_grad():
        X_t = torch.from_numpy(X_test).to(device)
        proba = model(X_t).cpu().numpy()
    preds = (proba > 0.5).astype(int)

    from sklearn.metrics import accuracy_score, roc_auc_score
    acc = accuracy_score(y_test, preds)
    try:
        auc = roc_auc_score(y_test, proba)
    except ValueError:
        auc = float('nan')
    return acc, auc


# ============== Skeleton (no torch) ==============

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers", nargs='+', help="Specific tickers")
    parser.add_argument("--top", type=int, help="Top N by volume")
    parser.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    parser.add_argument("--device", default='cuda', help="cuda or cpu")
    args = parser.parse_args()

    try:
        import torch
    except ImportError:
        print("ERROR: PyTorch not installed.", file=sys.stderr)
        print("Run: pip install torch --index-url https://download.pytorch.org/whl/cu121",
              file=sys.stderr)
        print("(Or cpu-only: pip install torch)", file=sys.stderr)
        print("\nOnce installed, this script will run LSTM training per ticker.", file=sys.stderr)
        sys.exit(0)

    if not torch.cuda.is_available() and args.device == 'cuda':
        print("CUDA not available, falling back to CPU", file=sys.stderr)
        args.device = 'cpu'

    if args.tickers:
        tickers = args.tickers
    elif args.top:
        # Same as xgb_predictor
        from xgb_predictor import get_top_tickers
        tickers = get_top_tickers(args.top)
    else:
        print("Need --tickers or --top", file=sys.stderr)
        sys.exit(1)

    print(f"[{datetime.now():%H:%M:%S}] LSTM training for {len(tickers)} tickers on {args.device}...",
          file=sys.stderr)
    df = build_dataset_multi(tickers, days=800, horizon=HORIZON)
    if df.empty:
        print("Empty dataset", file=sys.stderr)
        sys.exit(1)

    accs, aucs = [], []
    for ticker, grp in df.groupby('ticker'):
        grp = grp.sort_values('Date').reset_index(drop=True)
        if len(grp) < 200:
            continue
        try:
            acc, auc = train_lstm_one_ticker(grp, epochs=args.epochs, device=args.device)
            if acc is not None:
                print(f"  {ticker}: acc={acc:.3f} auc={auc:.3f}", file=sys.stderr)
                accs.append(acc)
                if not np.isnan(auc):
                    aucs.append(auc)
        except Exception as e:
            print(f"  {ticker}: failed ({e})", file=sys.stderr)

    if accs:
        print(f"\n[{datetime.now():%H:%M:%S}] Aggregate ({len(accs)} tickers):", file=sys.stderr)
        print(f"  Avg accuracy: {np.mean(accs):.3f}", file=sys.stderr)
        if aucs:
            print(f"  Avg AUC:      {np.mean(aucs):.3f}", file=sys.stderr)


if __name__ == '__main__':
    main()
