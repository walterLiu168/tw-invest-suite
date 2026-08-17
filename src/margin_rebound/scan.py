"""潛在反彈候選 — Multi-dimensional daily scan.

7 維度量化（每個 0-100 分，加權成 composite score 0-100）：

  1. 融資維持率 < 130%       (權重 30%) — margin distress 是核心
  2. 融資單日變化 < -3%       (權重 15%) — forced selling 訊號
  3. 融資 3 日變化 < -5%      (權重 10%) — 持續拋售
  4. Bias 負乖離 < -15%       (權重 15%) — 極端定價偏離
  5. RSI < 30                 (權重 10%) — 超賣
  6. 布林通道跌破 lower band  (權重 10%) — 波動通道極限
  7. 爆量 + 長下影線          (權重 10%) — 籌碼吸收

  集保戶數分佈 / 千張大戶持股比例 沒資料（需要 TDCC 申報資料）

使用：
    python scan.py                # 跑 scan + 存 JSON
    python scan.py --top 30       # 顯示 top 30
    python scan.py --threshold 60 # 自訂分數門檻
"""
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, date
from typing import Dict, List, Optional

# 讓 script 可獨立跑
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

import pymysql
import numpy as np

from db_client import get_conn


# ============== Config ==============
WEIGHTS = {
    "maint_rate":     0.30,  # 融資維持率
    "margin_change_1d": 0.15,  # 融資 1d 變化
    "margin_change_3d": 0.10,  # 融資 3d 變化
    "bias":           0.15,  # Bias 負乖離
    "rsi":            0.10,  # RSI 超賣
    "boll":           0.10,  # 布林下軌
    "volume_shadow":  0.10,  # 爆量下影線
}

DEFAULT_THRESHOLD = 50  # 預設分數門檻
DEFAULT_TOP = 30


# ============== SQL ==============
SQL_LATEST = """
    WITH ranked AS (
      SELECT
        Ticker, Date, Open, High, Low, Close, Volume,
        MarginBalance, sma_13, sma_27, sma_54, rsi_14, atr_14,
        LAG(Close, 1) OVER (PARTITION BY Ticker ORDER BY Date) AS prev_close,
        LAG(Low, 1) OVER (PARTITION BY Ticker ORDER BY Date) AS prev_low,
        LAG(MarginBalance, 1) OVER (PARTITION BY Ticker ORDER BY Date) AS prev_margin_1d,
        LAG(MarginBalance, 3) OVER (PARTITION BY Ticker ORDER BY Date) AS prev_margin_3d,
        AVG(Volume) OVER (PARTITION BY Ticker ORDER BY Date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS vol_avg_20,
        AVG(Close) OVER (PARTITION BY Ticker ORDER BY Date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma_20,
        STDDEV_POP(Close) OVER (PARTITION BY Ticker ORDER BY Date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS std_20,
        ROW_NUMBER() OVER (PARTITION BY Ticker ORDER BY Date DESC) AS rn
      FROM daily_data2_full
      WHERE Date >= (SELECT MAX(Date) FROM daily_data2_full) - INTERVAL 30 DAY
    )
    SELECT * FROM ranked WHERE rn = 1
"""


# ============== Scoring functions ==============

def score_maint_rate(maint_rate: float) -> float:
    """1. 融資維持率 < 130% → 100 分；>= 150% → 0 分。
    maint_rate: 120d avg cost-based estimate (lower = more distress)."""
    if maint_rate is None or maint_rate < 0:
        return 0
    # Linear: 100% maint = 100 分, 130% = 30 分, 150% = 0 分
    if maint_rate >= 150:
        return 0
    if maint_rate <= 100:
        return 100
    # 100~150 線性內插
    return round(max(0, 100 - (maint_rate - 100) * (100 / 50)), 1)


def score_margin_change(pct_change: float) -> float:
    """2. 融資單日變化 % change. <-3% = 100 分 (forced sell), >0 = 0 分."""
    if pct_change is None:
        return 0
    if pct_change <= -0.10:  # -10% 爆量減 = 100
        return 100
    if pct_change >= 0:
        return 0
    # -10% to 0% 線性內插
    return round(100 + (pct_change * 100 / -10 * 0) + (pct_change * 100), 1) if False else \
           round(min(100, max(0, -pct_change * 100 / 10 * 100)), 1)


def score_margin_change_3d(pct_change: float) -> float:
    """3. 融資 3 日變化 % change."""
    if pct_change is None:
        return 0
    if pct_change <= -0.15:
        return 100
    if pct_change >= 0:
        return 0
    return round(min(100, max(0, -pct_change * 100 / 15 * 100)), 1)


def score_bias(bias: float) -> float:
    """4. Bias 負乖離 (Close - sma_27) / sma_27 × 100.
    -20% = 100 分, 0% = 0 分."""
    if bias is None:
        return 0
    if bias >= 0:
        return 0
    if bias <= -0.20:
        return 100
    return round(min(100, max(0, -bias * 100 / 20 * 100)), 1)


def score_rsi(rsi: float) -> float:
    """5. RSI < 30 超賣."""
    if rsi is None:
        return 0
    if rsi >= 50:
        return 0
    if rsi <= 20:
        return 100
    return round(min(100, max(0, (50 - rsi) / 30 * 100)), 1)


def score_boll(close: float, bb_lower: float) -> float:
    """6. 布林通道跌破 lower band.
    close / bb_lower < 0.95 = 強跌破 → 100
    close / bb_lower > 1.0 = 未跌破 → 0"""
    if not close or not bb_lower or bb_lower <= 0:
        return 0
    ratio = close / bb_lower
    if ratio >= 1.0:
        return 0
    if ratio <= 0.92:
        return 100
    return round(min(100, max(0, (1.0 - ratio) * 100 / 0.08 * 100)), 1)


def score_volume_shadow(volume: int, vol_avg_20: int, close: float,
                        high: float, low: float) -> float:
    """7. 爆量 + 長下影線.
    volume > 2x avg AND (close - low) / (high - low) > 0.5 → 高分"""
    if not vol_avg_20 or vol_avg_20 <= 0 or not high or high <= low:
        return 0
    vol_ratio = volume / vol_avg_20
    shadow = (close - low) / (high - low) if (high - low) > 0 else 0
    # vol 2x = 50 分, vol 3x = 100 分
    vol_score = min(50, max(0, (vol_ratio - 1) * 50)) if vol_ratio > 1 else 0
    # shadow 0.5 = 25 分, shadow 0.8 = 50 分
    shadow_score = min(50, max(0, (shadow - 0.3) * 100)) if shadow > 0.3 else 0
    return round(vol_score + shadow_score, 1)


# ============== Main scan ==============

def scan(threshold: float = DEFAULT_THRESHOLD,
         top: int = DEFAULT_TOP,
         save_json: bool = True) -> List[Dict]:
    """Run the multi-dim margin rebound scan."""
    candidates = []
    with get_conn() as conn:
        cur = conn.cursor(pymysql.cursors.DictCursor)
        cur.execute(SQL_LATEST)
        rows = cur.fetchall()
        # Get company + industry
        cur.execute("SELECT ticker, company, industry FROM industry_type")
        info = {r["ticker"]: r for r in cur.fetchall()}

    for r in rows:
        try:
            ticker = r["Ticker"]
            close = float(r["Close"])
            open_ = float(r["Open"])
            high = float(r["High"])
            low = float(r["Low"])
            volume = int(r["Volume"])
            margin = int(r["MarginBalance"] or 0)
            sma13 = float(r["sma_13"] or 0)
            sma27 = float(r["sma_27"] or 0)
            sma54 = float(r["sma_54"] or 0)
            rsi = float(r["rsi_14"] or 0)
            atr = float(r["atr_14"] or 0)
            prev_close = float(r["prev_close"] or 0)
            prev_low = float(r["prev_low"] or 0)
            prev_margin_1d = float(r["prev_margin_1d"] or 0)
            prev_margin_3d = float(r["prev_margin_3d"] or 0)
            vol_avg_20 = float(r["vol_avg_20"] or 0)
            ma_20 = float(r["ma_20"] or 0)
            std_20 = float(r["std_20"] or 0)
        except (TypeError, ValueError):
            continue
        if margin <= 0 or close <= 0 or high <= low:
            continue

        # Bollinger band: 20d ma ± 2 std
        bb_lower = ma_20 - 2 * std_20 if ma_20 > 0 and std_20 > 0 else 0
        bb_upper = ma_20 + 2 * std_20 if ma_20 > 0 and std_20 > 0 else 0

        # 120d average cost for maintenance rate
        # 簡化：在 scanner 直接 SQL 一次
        # 但避免額外 query，用 sma_54 近似（54 交易日 = 約 80 天 calendar，可能不準）
        # Better: do another small query
        # 暫時跳過，讓外面傳入（從 avg_cost 函數拿）
        # 簡化：用 1/avg_cost_in_sql
        # 改寫：直接用 1/avg_cost_120 query

        # Margin change
        margin_chg_1d = (margin - prev_margin_1d) / prev_margin_1d if prev_margin_1d else 0
        margin_chg_3d = (margin - prev_margin_3d) / prev_margin_3d if prev_margin_3d else 0

        # Bias (negative bias is good signal)
        bias = (close - sma27) / sma27 if sma27 else 0

        scores = {
            "margin_change_1d": score_margin_change(margin_chg_1d),
            "margin_change_3d": score_margin_change_3d(margin_chg_3d),
            "bias": score_bias(bias),
            "rsi": score_rsi(rsi),
            "boll": score_boll(close, bb_lower) if bb_lower > 0 else 0,
            "volume_shadow": score_volume_shadow(volume, vol_avg_20, close, high, low),
        }
        # Composite (without maint_rate — need separate query)
        composite_partial = sum(scores[k] * WEIGHTS[k] for k in scores) / sum(WEIGHTS[k] for k in scores)
        composite_partial = round(composite_partial * (1 - WEIGHTS["maint_rate"]), 1)

        candidates.append({
            "ticker": ticker,
            "close": close,
            "margin_張": margin,
            "margin_市值_億": round(margin * close * 1000 / 1e8, 2),
            "margin_chg_1d_pct": round(margin_chg_1d * 100, 2),
            "margin_chg_3d_pct": round(margin_chg_3d * 100, 2),
            "bias_pct": round(bias * 100, 2),
            "rsi": rsi,
            "bb_lower": round(bb_lower, 2) if bb_lower > 0 else None,
            "bb_upper": round(bb_upper, 2) if bb_upper > 0 else None,
            "ma_20": round(ma_20, 2),
            "vol_ratio": round(volume / vol_avg_20, 2) if vol_avg_20 > 0 else 0,
            "lower_shadow": round((close - low) / (high - low), 2) if (high - low) > 0 else 0,
            "scores": scores,
            "composite_partial": composite_partial,
            "company": info.get(ticker, {}).get("company", ""),
            "industry": info.get(ticker, {}).get("industry", ""),
        })

    # Now compute maint_rate with separate query
    with get_conn() as conn:
        cur = conn.cursor(pymysql.cursors.DictCursor)
        tickers = [c["ticker"] for c in candidates]
        if not tickers:
            return []
        placeholders = ",".join(["%s"] * len(tickers))
        cur.execute(f"""
            SELECT Ticker, AVG(Close) AS avg_c
            FROM daily_data2_full
            WHERE Ticker IN ({placeholders})
              AND Date >= (SELECT MAX(Date) FROM daily_data2_full) - INTERVAL 120 DAY
            GROUP BY Ticker
        """, tuple(tickers))
        avg_costs = {r["Ticker"]: float(r["avg_c"]) for r in cur.fetchall() if r.get("avg_c")}

    for c in candidates:
        avg_c = avg_costs.get(c["ticker"], 0)
        if avg_c > 0 and c["close"] > 0:
            maint_rate = c["close"] / avg_c * 100
        else:
            maint_rate = None
        c["maint_rate"] = maint_rate
        c["avg_cost_120d"] = round(avg_c, 2) if avg_c > 0 else None
        c["scores"]["maint_rate"] = score_maint_rate(maint_rate) if maint_rate is not None else 0
        # Full composite
        c["composite"] = round(sum(c["scores"][k] * WEIGHTS[k] for k in WEIGHTS) * 100 / 100, 1)

    # FIRST RULE (constitution): 融資維持率 < 130% — 不達就踢掉
    # If maint_rate is None or >= 130, exclude entirely (no composite, no chip, no show)
    candidates = [c for c in candidates if c.get("maint_rate") is not None and c["maint_rate"] < 130]

    # Composite threshold filter + sort
    candidates = [c for c in candidates if c["composite"] >= threshold]
    candidates.sort(key=lambda c: c["composite"], reverse=True)
    return candidates[:top]


# ============== Output ==============

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--top", type=int, default=DEFAULT_TOP)
    parser.add_argument("--out", type=Path, help="Output JSON path")
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()

    print(f"[{datetime.now():%H:%M:%S}] Margin rebound scan (threshold ≥ {args.threshold})...", file=sys.stderr)
    candidates = scan(threshold=args.threshold, top=args.top, save_json=False)
    print(f"  {len(candidates)} candidates (composite ≥ {args.threshold})", file=sys.stderr)

    if not candidates:
        return

    # Save JSON (require --out path; daily batch will pass skill root)
    if not args.no_save:
        if not args.out:
            print("  WARN: no --out given, skipping JSON save", file=sys.stderr)
        else:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_data = {
                "date": date.today().isoformat(),
                "threshold": args.threshold,
                "weights": WEIGHTS,
                "count": len(candidates),
                "candidates": candidates,
            }
            out_path.write_text(json.dumps(out_data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
            print(f"  → {out_path}", file=sys.stderr)

    # Print table
    print()
    print(f"{'Ticker':<6} {'Score':<6} {'Maint':<7} {'Bias':<7} {'RSI':<5} {'1dΔ':<7} {'3dΔ':<7} {'Vol×':<5} {'Shadow':<7} {'名稱'}")
    print("-" * 90)
    for c in candidates:
        maint_s = f"{c['maint_rate']:.1f}%" if c.get("maint_rate") is not None else "—"
        print(
            f"{c['ticker']:<6} "
            f"{c['composite']:<6} "
            f"{maint_s:<7} "
            f"{c['bias_pct']:>+5.1f}% "
            f"{c['rsi']:>4.0f}  "
            f"{c['margin_chg_1d_pct']:>+5.1f}% "
            f"{c['margin_chg_3d_pct']:>+5.1f}% "
            f"{c['vol_ratio']:>4.1f}x "
            f"{c['lower_shadow']:>5.2f}  "
            f"{c.get('company', '')[:20]}"
        )


if __name__ == "__main__":
    main()
