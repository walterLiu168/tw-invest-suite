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
import os
import json
import argparse
from pathlib import Path
from datetime import datetime, date
from typing import Dict, List, Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

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

DEFAULT_THRESHOLD = 0  # 不再用 composite 過濾（130% 是唯一硬規則）
DEFAULT_TOP = None  # 預設列全部（user: "i want to see it in the report"）


# ============== SQL ==============
# JOIN with finmind_taiwan_margin_maintenance for REAL margin_maintenance
# (replaces 120d avg close estimate)
SQL_LATEST = """
    WITH ranked AS (
      SELECT
        d.Ticker, d.Date, d.Open, d.High, d.Low, d.Close, d.Volume,
        d.MarginBalance, d.sma_13, d.sma_27, d.sma_54, d.rsi_14, d.atr_14,
        m.margin_maintenance, m.margin_cost AS finmind_margin_cost,
        LAG(Close, 1) OVER (PARTITION BY d.Ticker ORDER BY d.Date) AS prev_close,
        LAG(Low, 1) OVER (PARTITION BY d.Ticker ORDER BY d.Date) AS prev_low,
        LAG(MarginBalance, 1) OVER (PARTITION BY d.Ticker ORDER BY d.Date) AS prev_margin_1d,
        LAG(MarginBalance, 3) OVER (PARTITION BY d.Ticker ORDER BY d.Date) AS prev_margin_3d,
        AVG(Volume) OVER (PARTITION BY d.Ticker ORDER BY d.Date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS vol_avg_20,
        AVG(Close) OVER (PARTITION BY d.Ticker ORDER BY d.Date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma_20,
        STDDEV_POP(Close) OVER (PARTITION BY d.Ticker ORDER BY d.Date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS std_20,
        ROW_NUMBER() OVER (PARTITION BY d.Ticker ORDER BY d.Date DESC) AS rn
      FROM daily_data2_full d
      LEFT JOIN finmind_taiwan_margin_maintenance m
        ON d.Ticker = m.ticker
        AND d.Date = m.trade_date
      WHERE d.Date >= (SELECT MAX(Date) FROM daily_data2_full) - INTERVAL 30 DAY
    )
    SELECT * FROM ranked WHERE rn = 1
"""


# ============== Scoring functions ==============

def score_maint_rate(maint_rate: float) -> float:
    """1. 融資維持率 < 130% → 100 分；>= 150% → 0 分。
    maint_rate: FinMind 官方維持率（真實，非 120d 估算）。"""
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


# ============== AI Synthesis (data → info) ==============

def synthesize_ai_comment(c: Dict) -> str:
    """把 6 個 data 點合成 1 行 actionable info（rule-based）。

    為什麼不是 LLM：daily LLM 還沒接好（LLM_API_KEY 未設），
    這版用規則 + emoji 語意讓使用者一眼看出「該不該進場」。
    升級路徑：scan_ai_comment.py 接 LLM 後取代此函式。
    """
    maint = c.get("maint_rate") or 0
    chg = c.get("margin_chg_1d_pct") or 0
    bias = c.get("bias_pct") or 0
    rsi = c.get("rsi") or 50

    parts = []

    # 1. 維持率語意
    if maint < 100:
        parts.append(f"🔴 套牢 {maint:.0f}%")
    elif maint < 115:
        parts.append(f"🟢 接近追繳 {maint:.0f}%")
    else:  # 115-130
        parts.append(f"🟡 警戒 {maint:.0f}%")

    # 2. 1d 融資變化語意
    if chg < -10:
        parts.append(f"📉 forced selling 強 {chg:+.1f}%")
    elif chg < -3:
        parts.append(f"📉 forced selling {chg:+.1f}%")
    elif chg < 0:
        parts.append(f"📉 輕微減 {chg:+.1f}%")
    else:
        parts.append(f"⚪ 沒動 {chg:+.1f}%")

    # 3. Bias 語意
    if bias < -15:
        parts.append(f"🟢 嚴重負乖離 {bias:+.1f}%")
    elif bias < -5:
        parts.append(f"🟢 負乖離 {bias:+.1f}%")
    elif bias < 0:
        parts.append(f"🟡 輕微 {bias:+.1f}%")
    else:
        parts.append(f"⚪ 正常 {bias:+.1f}%")

    # 4. RSI 語意
    if rsi < 20:
        parts.append(f"🔴 嚴重超賣 {rsi:.0f}")
    elif rsi < 30:
        parts.append(f"🟢 超賣 {rsi:.0f}")
    elif rsi < 50:
        parts.append(f"🟡 中性偏弱 {rsi:.0f}")
    else:
        parts.append(f"⚪ 中性 {rsi:.0f}")

    # 5. Action 綜合
    if maint < 100 and chg < -3 and rsi < 35:
        action = "✅ 短線反彈候選，慎防接刀設停損"
    elif maint < 100 and chg < -3:
        action = "🟢 forced-sell 反彈 setup"
    elif maint < 100:
        action = "🟡 套牢待觀察"
    else:
        action = "⚪ 觀望"

    return " | ".join(parts) + " → " + action


# ============== OpenAI Synthesis (per-card, real LLM) ==============

def llm_synthesize_one(c: Dict) -> str:
    """Use OpenAI Chat Completion to synthesize 1-line info for one card.

    Falls back to rule-based if API call fails.
    Requires env: OPENAI_API_KEY (and optional OPENAI_BASE_URL, OPENAI_MODEL).
    """
    if not HAS_REQUESTS:
        return synthesize_ai_comment(c)

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return synthesize_ai_comment(c)

    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    maint = c.get("maint_rate") or 0
    chg = c.get("margin_chg_1d_pct") or 0
    bias = c.get("bias_pct") or 0
    rsi = c.get("rsi") or 50
    close = c.get("close") or 0
    avg = c.get("avg_cost_120d") or 0

    user_prompt = (
        f"你是台股分析師，給 1 句話（≤60 字）總結這檔的「融資反彈 setup」。\n\n"
        f"數據：收盤 {close:.2f} · 120d 成本 {avg:.2f} · 維持率 {maint:.1f}% "
        f"· 1d 融資 {chg:+.1f}% · Bias {bias:+.1f}% · RSI {rsi:.0f}\n\n"
        f"規則：\n"
        f"1. 繁體中文\n"
        f"2. 一行一訊息（不要分點、不要空行）\n"
        f"3. 開頭 emoji 語意：🔴套牢 / 🟢接近追繳 / 🟡警戒 / ✅短線反彈 / ⚪觀望\n"
        f"4. 結尾給一句行動建議（短線搶反彈/觀望/慎防接刀等）\n"
        f"5. 不要重複數字，用比喻或動作描述（例：「forced selling + 超賣 = 短線反彈 setup」）"
    )

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是台股資深分析師，數據解讀精準、不囉嗦。"},
            {"role": "user", "content": user_prompt}
        ],
        # DeepSeek v4-flash 是 reasoning model：reasoning_tokens 會佔 95%+
        # 給到 4000 確保有 reasoning (~3800) + 實際回答 (~200)
        "max_tokens": 4000,
        "temperature": 0.5,
    }
    try:
        r = requests.post(
            f"{base_url}/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        # Fallback to rule-based
        return synthesize_ai_comment(c)


# ============== Main scan ==============

def scan(threshold: float = DEFAULT_THRESHOLD,
         top: int = DEFAULT_TOP,
         save_json: bool = True) -> List[Dict]:
    """Run the multi-dim margin rebound scan.

    Filter rules (constitution):
      - HARD filter: maint_rate < 130% (FIRST RULE)
      - 其餘 7 維評分是 bonus 資訊，**不再用 composite 過濾**
      - Sort by maint_rate ASC (最 distress 排前面)

    Returns all candidates that pass 130% (or first `top` if specified).
    """
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
            # FinMind real maintenance (may be None if not yet downloaded)
            finmind_maint = r.get("margin_maintenance")
            maint_rate = float(finmind_maint) if finmind_maint is not None else None
        except (TypeError, ValueError):
            continue
        if margin <= 0 or close <= 0 or high <= low:
            continue

        # Bollinger band: 20d ma ± 2 std
        bb_lower = ma_20 - 2 * std_20 if ma_20 > 0 and std_20 > 0 else 0
        bb_upper = ma_20 + 2 * std_20 if ma_20 > 0 and std_20 > 0 else 0

        # Margin change
        margin_chg_1d = (margin - prev_margin_1d) / prev_margin_1d if prev_margin_1d else 0
        margin_chg_3d = (margin - prev_margin_3d) / prev_margin_3d if prev_margin_3d else 0

        # Bias (negative bias is good signal)
        bias = (close - sma27) / sma27 if sma27 else 0

        scores = {
            "maint_rate": score_maint_rate(maint_rate),  # uses real FinMind data
            "margin_change_1d": score_margin_change(margin_chg_1d),
            "margin_change_3d": score_margin_change_3d(margin_chg_3d),
            "bias": score_bias(bias),
            "rsi": score_rsi(rsi),
            "boll": score_boll(close, bb_lower) if bb_lower > 0 else 0,
            "volume_shadow": score_volume_shadow(volume, vol_avg_20, close, high, low),
        }

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
            "maint_rate": maint_rate,  # FinMind real
            "maint_source": "finmind" if maint_rate is not None else "missing",
            "scores": scores,
            "company": info.get(ticker, {}).get("company", ""),
            "industry": info.get(ticker, {}).get("industry", ""),
        })

    # Compute full composite (now includes maint_rate from real data)
    for c in candidates:
        c["composite"] = round(sum(c["scores"][k] * WEIGHTS[k] for k in WEIGHTS) * 100 / 100, 1)

    # 120d 平均成本（純顯示用，不影響 130% 過濾）
    with get_conn() as conn:
        cur = conn.cursor(pymysql.cursors.DictCursor)
        tickers = [c["ticker"] for c in candidates]
        if tickers:
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
        c["avg_cost_120d"] = round(avg_costs.get(c["ticker"], 0), 2) or None

    # FIRST RULE (constitution): 融資維持率 < 130% — 不達就踢掉
    # If maint_rate is None or >= 130, exclude entirely (no composite, no chip, no show)
    candidates = [c for c in candidates if c.get("maint_rate") is not None and c["maint_rate"] < 130]

    # NOTE: 130% 是「唯一硬規則」；7 維評分只是 bonus 資訊，不要用 composite 過濾。
    # 用戶原話: "the only rule is 130%, the rest are extra which is good to included"

    # Multi-key sort: user 原話 "rank and sort by % then rest factors"
    # Primary: 維持率 ASC (最 distress 排前)
    # Secondary: composite DESC (整體評分高優先)
    # Tertiary: 1d 融資 DESC (負越多越 forced selling = 越好)
    candidates.sort(key=lambda c: (
        c.get("maint_rate") or 999,
        -(c.get("composite") or 0),
        -(c.get("margin_chg_1d_pct") or 0),
    ))

    # Per-card AI synthesis (data → info, 1 line per card)
    # Use LLM for top N (configurable, default 30); rule-based for the rest.
    LLM_TOP_N = int(os.environ.get("MARGIN_LLM_TOP_N", "30"))
    for i, c in enumerate(candidates):
        if i < LLM_TOP_N and os.environ.get("OPENAI_API_KEY"):
            try:
                c["ai_comment"] = llm_synthesize_one(c)
            except Exception as e:
                # LLM failed (rate limit, network) — fall back to rule
                c["ai_comment"] = synthesize_ai_comment(c)
        else:
            c["ai_comment"] = synthesize_ai_comment(c)

    # Return all that pass 130% (no composite filter, no top limit)
    if top and top < len(candidates):
        return candidates[:top]
    return candidates


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
