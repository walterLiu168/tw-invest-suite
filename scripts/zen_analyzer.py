"""
Simplified Chanlun (纏論) structural analyzer for daily K-line.

Pipeline (per zen skill rules):
    OHLCV → normalize → fractals → pens → segments → centers → buy/sell candidates

This is a deterministic daily-K detector. For sub-day confirmation (5m/30m),
the user should run the full `zen skill` detector.
"""
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db_client as db  # noqa: E402


@dataclass
class Fractal:
    """A top or bottom turning point on the K-line."""
    index: int           # bar index (0 = oldest)
    date: str
    price: float
    kind: str            # "top" or "bottom"


@dataclass
class Pen:
    """A pen (筆) — connects alternating fractals."""
    start_idx: int
    end_idx: int
    start_date: str
    end_date: str
    start_price: float
    end_price: float
    direction: str       # "up" or "down"
    high: float          # highest high in the pen
    low: float           # lowest low in the pen


@dataclass
class Center:
    """A center (中樞) — consolidation zone from 3 overlapping pens."""
    high: float
    low: float
    start_date: str
    end_date: str
    pen_indices: List[int] = field(default_factory=list)


@dataclass
class ZenRead:
    """Final structural read for one ticker."""
    ticker: str
    as_of_date: str
    n_bars: int
    fractals: List[Fractal] = field(default_factory=list)
    pens: List[Pen] = field(default_factory=list)
    center: Optional[Center] = None
    position: str = ""           # "in_center" / "above_center" / "below_center" / "trending"
    bias: str = ""               # "bullish" / "bearish" / "neutral"
    buy_candidates: List[str] = field(default_factory=list)
    sell_candidates: List[str] = field(default_factory=list)
    invalidation: str = ""
    notes: List[str] = field(default_factory=list)


# ---------- step 1: load OHLCV ----------

def load_ohlcv(ticker: str, days: int = 120) -> List[Dict]:
    """Load last `days` bars of OHLCV. Returns ascending by date."""
    return db.ticker_history(ticker, days=days)


# ---------- step 2: fractals (5-bar pattern) ----------

def find_fractals(bars: List[Dict]) -> List[Fractal]:
    """Find top/bottom fractals using 5-bar pattern.

    Top fractal at index i: bars[i].high is the highest of bars[i-2..i+2].
    Bottom fractal at index i: bars[i].low is the lowest of bars[i-2..i+2].
    Last 2 bars and first 2 bars are excluded (need 2 on each side).
    """
    fractals: List[Fractal] = []
    n = len(bars)
    if n < 5:
        return fractals
    for i in range(2, n - 2):
        cur = bars[i]
        cur_high = float(cur["High"])
        cur_low = float(cur["Low"])
        # Top
        is_top = all(
            cur_high >= float(bars[j]["High"])
            for j in (i - 2, i - 1, i + 1, i + 2)
        )
        # Bottom
        is_bottom = all(
            cur_low <= float(bars[j]["Low"])
            for j in (i - 2, i - 1, i + 1, i + 2)
        )
        if is_top and not is_bottom:
            fractals.append(Fractal(i, str(cur["Date"]), cur_high, "top"))
        elif is_bottom and not is_top:
            fractals.append(Fractal(i, str(cur["Date"]), cur_low, "bottom"))
        # If both (equal highs and equal lows), skip (degenerate)
    return fractals


# ---------- step 3: pens (筆) ----------

def build_pens(fractals: List[Fractal], bars: List[Dict]) -> List[Pen]:
    """Connect alternating top/bottom fractals into pens."""
    pens: List[Pen] = []
    for i in range(len(fractals) - 1):
        a, b = fractals[i], fractals[i + 1]
        if a.kind == b.kind:
            # Same-kind fractals: keep the more extreme (treating: if both top, keep higher; both bottom, keep lower)
            if a.kind == "top":
                if float(bars[b.index]["High"]) > float(bars[a.index]["High"]):
                    fractals[i + 1] = a  # skip b
                    continue
            else:
                if float(bars[b.index]["Low"]) < float(bars[a.index]["Low"]):
                    fractals[i + 1] = a
                    continue
        # Ensure alternating
        if a.kind == b.kind:
            continue
        direction = "up" if b.price > a.price else "down"
        hi = max(a.price, b.price)
        lo = min(a.price, b.price)
        # Take high/low from the bars between
        for j in range(min(a.index, b.index), max(a.index, b.index) + 1):
            hi = max(hi, float(bars[j]["High"]))
            lo = min(lo, float(bars[j]["Low"]))
        pens.append(Pen(
            start_idx=a.index,
            end_idx=b.index,
            start_date=a.date,
            end_date=b.date,
            start_price=a.price,
            end_price=b.price,
            direction=direction,
            high=hi,
            low=lo,
        ))
    return pens


# ---------- step 4: center (中樞) ----------

def find_recent_center(pens: List[Pen]) -> Optional[Center]:
    """A center is formed by 3 consecutive overlapping pens.

    For a center, the high of each pen must overlap the others,
    meaning: max(low1, low2, low3) < min(high1, high2, high3).
    """
    if len(pens) < 3:
        return None
    # Take the most recent 3 pens
    last3 = pens[-3:]
    high = min(p.high for p in last3)
    low = max(p.low for p in last3)
    if low >= high:
        return None  # no overlap
    return Center(
        high=high,
        low=low,
        start_date=last3[0].start_date,
        end_date=last3[-1].end_date,
        pen_indices=[pens.index(p) for p in last3],
    )


# ---------- step 5: position + bias ----------

def classify_position(read: ZenRead, current_price: float) -> str:
    if read.center is None:
        # No center: simple trend
        if len(read.pens) >= 2:
            if read.pens[-1].direction == "up" and read.pens[-2].direction == "up":
                return "上升趨勢（無中樞）"
            if read.pens[-1].direction == "down" and read.pens[-2].direction == "down":
                return "下降趨勢（無中樞）"
        return "盤整／資料不足"
    c = read.center
    if c.low <= current_price <= c.high:
        return f"中樞內震盪 ({c.low:.2f} - {c.high:.2f})"
    if current_price > c.high:
        return f"中樞之上（突破） 距中樞高 {current_price - c.high:.2f}"
    return f"中樞之下（跌破） 距中樞低 {c.low - current_price:.2f}"


def classify_bias(read: ZenRead, current_price: float) -> str:
    """偏多 / 偏空 / 中性 — Traditional Chinese labels for the report."""
    if not read.pens:
        return "中性"
    last = read.pens[-1]
    if read.center:
        if current_price > read.center.high and last.direction == "up":
            return "偏多"
        if current_price < read.center.low and last.direction == "down":
            return "偏空"
    else:
        if last.direction == "up":
            return "偏多"
        if last.direction == "down":
            return "偏空"
    return "中性"


def find_buy_sell_candidates(read: ZenRead, current_price: float) -> None:
    """Identify potential 1st/2nd/3rd buy and sell points.

    1st buy/sell: after a completed pen, the new fractal at the pen's end
    2nd buy/sell: pullback to the center's lower (buy) or upper (sell) edge
    3rd buy/sell: pullback to the prior center's lower/upper after breakout
    """
    if not read.pens or read.center is None:
        return
    c = read.center
    last = read.pens[-1]

    # 2nd-class candidates: at center edges
    if last.direction == "up" and current_price >= c.high:
        # Breakout up — 2nd buy (回測中樞高)
        read.buy_candidates.append(
            f"二買: 拉回至中樞高 {c.high:.2f} 且不破 (現價 {current_price:.2f})"
        )
        read.invalidation = f"若跌破中樞高 {c.high:.2f} 失效"
    elif last.direction == "down" and current_price <= c.low:
        # Breakdown down — 2nd sell
        read.sell_candidates.append(
            f"二賣: 反彈至中樞低 {c.low:.2f} 且不過 (現價 {current_price:.2f})"
        )
        read.invalidation = f"若漲破中樞低 {c.low:.2f} 失效"
    elif c.low <= current_price <= c.high:
        # Inside center — 1st-class candidates based on pen direction
        if last.direction == "up":
            read.buy_candidates.append(
                f"一買: 收盤 > 中樞高 {c.high:.2f} 確認向上突破"
            )
        else:
            read.sell_candidates.append(
                f"一賣: 收盤 < 中樞低 {c.low:.2f} 確認向下突破"
            )
        read.invalidation = f"價格在 {c.low:.2f}-{c.high:.2f} 區間內震盪，方向未明"


# ---------- entry point ----------

def analyze(ticker: str, days: int = 120) -> ZenRead:
    bars = load_ohlcv(ticker, days=days)
    read = ZenRead(
        ticker=ticker,
        as_of_date=str(bars[-1]["Date"]) if bars else "",
        n_bars=len(bars),
    )
    if len(bars) < 30:
        read.notes.append(f"資料不足（{len(bars)} 根 K 線）")
        return read

    fractals = find_fractals(bars)
    read.fractals = fractals
    pens = build_pens(fractals, bars)
    read.pens = pens
    read.center = find_recent_center(pens)

    current = float(bars[-1]["Close"])
    read.position = classify_position(read, current)
    read.bias = classify_bias(read, current)
    find_buy_sell_candidates(read, current)

    # Invalidation
    if read.center is None and len(pens) >= 1:
        last = pens[-1]
        if last.direction == "up":
            read.invalidation = f"若收盤跌破上升筆起點 {last.start_price:.2f} 失效"
        else:
            read.invalidation = f"若收盤漲破下降筆起點 {last.start_price:.2f} 失效"

    if len(fractals) < 4:
        read.notes.append(f"分型數量 {len(fractals)} 偏少，結構待確認")
    return read


# ---------- formatting ----------

def format_read(r: ZenRead) -> str:
    """Format ZenRead as a one-paragraph structural summary."""
    lines = []
    lines.append(f"**級別**：日 K（{r.n_bars} 根）")
    lines.append(f"**資料日**：{r.as_of_date}")
    lines.append(f"**當下位置**：{r.position}")
    lines.append(f"**方向偏多／偏空**：{r.bias or '中性'}")
    if r.center:
        lines.append(f"**最近中樞**：{r.center.low:.2f} - {r.center.high:.2f}（{r.center.start_date} ~ {r.center.end_date}）")
    if r.pens:
        last = r.pens[-1]
        lines.append(f"**最新筆**：{last.direction} {last.start_price:.2f} → {last.end_price:.2f}（{last.start_date} ~ {last.end_date}）")
    if r.buy_candidates:
        lines.append("**買點候選**：" + "; ".join(r.buy_candidates))
    if r.sell_candidates:
        lines.append("**賣點候選**：" + "; ".join(r.sell_candidates))
    if r.invalidation:
        lines.append(f"**失效條件**：{r.invalidation}")
    if r.notes:
        lines.append("**備註**：" + "; ".join(r.notes))
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("ticker", nargs="?", default="2330")
    ap.add_argument("--days", type=int, default=120)
    args = ap.parse_args()
    r = analyze(args.ticker, days=args.days)
    print(f"=== {r.ticker} zen read ({r.as_of_date}) ===")
    print(format_read(r))
    print(f"\n[debug] fractals: {len(r.fractals)}, pens: {len(r.pens)}, center: {r.center is not None}")
