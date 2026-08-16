"""
Market screener — picks 6 candidates per price bucket (3 short-term + 3 long-term).

Price buckets (Taiwan listed + OTC):
    <100        銅板股
    100-300     中價股
    300-1000    中高價股
    >1000       高價股

Selection logic per bucket:
    * Long-term (3 picks): market cap + excess_return_240d
    * Short-term (3 picks): momentum + chip signals + news sentiment

Data source: MySQL `tw_elec` database via db_client.py (no API calls).
Batch queries for speed (1,943 stocks × per-stock lookups = slow).
"""
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db_client as db  # noqa: E402
import zen_analyzer as zen  # noqa: E402

PRICE_BUCKETS = [
    ("<100",        0,    100),
    ("100-300",     100,  300),
    ("300-1000",    300,  1000),
    (">1000",      1000,  float("inf")),
]
PICKS_PER_HORIZON = 3


@dataclass
class Candidate:
    ticker: str
    name: str
    industry: str
    close: float
    change_pct: float
    volume: int
    three_net: int
    foreign_net: int
    margin_balance: int
    short_balance: int
    foreign_ratio: float
    sma13: float
    sma27: float
    sma54: float
    rsi14: float
    atr14: float
    is_gap: int
    chip_score: Optional[float] = None
    volume_burst: Optional[int] = None
    kd_golden_cross: Optional[int] = None
    inv_first_in: Optional[int] = None
    inv_buy_percent: Optional[float] = None
    foreign_buy_ratio_chip: Optional[float] = None
    excess_return_20d: Optional[float] = None
    excess_return_60d: Optional[float] = None
    excess_return_120d: Optional[float] = None
    excess_return_240d: Optional[float] = None
    excess_return_500d: Optional[float] = None
    market_cap: Optional[float] = None
    news_count_5d: int = 0
    news_sentiment_avg: Optional[float] = None
    news_headlines: List[str] = None  # type: ignore
    horizon: str = ""
    # zen (纏論) structural read for short-term picks
    zen_position: str = ""
    zen_bias: str = ""
    zen_center: str = ""
    zen_summary: str = ""


def _f(v) -> float:
    if v is None:
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _i(v) -> int:
    try:
        return int(v) if v is not None else 0
    except (TypeError, ValueError):
        return 0


def build_candidate(row: Dict, industry_map: Dict[str, Dict[str, str]],
                    shares_map: Dict[str, int]) -> Candidate:
    """Build a Candidate from a daily_data2_full snapshot row + industry lookup."""
    close = _f(row.get("Close"))
    shares = row.get("SharesOutstanding_shares") or shares_map.get(row["Ticker"])
    market_cap = close * _f(shares) if shares and close else None
    info = industry_map.get(row["Ticker"], {})
    company = info.get("company", "") or row.get("company") or row["Ticker"]
    industry = info.get("industry", "")
    return Candidate(
        ticker=row["Ticker"],
        name=company,
        industry=industry,
        close=close,
        change_pct=_f(row.get("change_pct")),
        volume=_i(row.get("Volume")),
        three_net=_i(row.get("ThreeNet")),
        foreign_net=_i(row.get("ForeignNet")),
        margin_balance=_i(row.get("MarginBalance")),
        short_balance=_i(row.get("ShortBalance")),
        foreign_ratio=_f(row.get("ForeignRatio")),
        sma13=_f(row.get("sma_13")),
        sma27=_f(row.get("sma_27")),
        sma54=_f(row.get("sma_54")),
        rsi14=_f(row.get("rsi_14")),
        atr14=_f(row.get("atr_14")),
        is_gap=_i(row.get("is_gap")),
        market_cap=market_cap,
        news_headlines=[],
    )


def enrich_from_chip_map(c: Candidate, chip_map: Dict[str, Dict]) -> None:
    chip = chip_map.get(c.ticker)
    if not chip:
        return
    c.chip_score = _f(chip.get("ChipScore"))
    c.volume_burst = _i(chip.get("VolumeBurst"))
    c.kd_golden_cross = _i(chip.get("KD_GoldenCross"))
    c.inv_first_in = _i(chip.get("Inv_FirstIn"))
    c.inv_buy_percent = _f(chip.get("Inv_BuyPercent"))
    c.foreign_buy_ratio_chip = _f(chip.get("ForeignBuyRatio"))


def enrich_from_features_map(c: Candidate, feat_map: Dict[str, Dict]) -> None:
    """Keep 20d excess return from stock_features (60d/240d we recompute ourselves)."""
    f = feat_map.get(c.ticker)
    if not f:
        return
    c.excess_return_20d = _f(f.get("excess_return_20d"))


def enrich_long_term_returns(candidates: List[Candidate], target_date: str) -> None:
    """Compute 60d/120d/240d/500d returns from daily_data2_full in batch."""
    if not candidates:
        return
    tickers = [c.ticker for c in candidates]
    returns = db.long_term_returns_batch(tickers, target_date)
    for c in candidates:
        ret = returns.get(c.ticker, {})
        c.excess_return_60d = ret.get("ret_60d", 0.0) or 0.0
        c.excess_return_120d = ret.get("ret_120d", 0.0) or 0.0
        c.excess_return_240d = ret.get("ret_240d", 0.0) or 0.0
        c.excess_return_500d = ret.get("ret_500d", 0.0) or 0.0


def enrich_news_for_picks(picks: List[Candidate]) -> None:
    """News is per-ticker query — only call for the final 24 picks."""
    if not picks:
        return
    tickers = [c.ticker for c in picks]
    news_map = db.news_for_tickers(tickers, limit_per=5, days=5)
    for c in picks:
        news = news_map.get(c.ticker, [])
        c.news_count_5d = len(news)
        sents = [_f(n.get("sentiment_score")) for n in news if n.get("sentiment_score") is not None]
        if sents:
            c.news_sentiment_avg = sum(sents) / len(sents)
        c.news_headlines = [n.get("title", "") for n in news[:3]]


# ---------- ranking ----------

def pick_long_term(candidates: List[Candidate], n: int) -> List[Candidate]:
    """Long-term: prefer large cap + positive 240d/120d returns."""
    def score(c: Candidate) -> float:
        cap = _f(c.market_cap)
        # sqrt to dampen mega caps
        log_cap = (cap ** 0.5) if cap > 0 else 0
        er240 = _f(c.excess_return_240d)
        er120 = _f(c.excess_return_120d)
        er60 = _f(c.excess_return_60d)
        # Weight: 50% cap, 30% 240d, 20% 120d/60d
        return log_cap * 0.5 + er240 * 200 * 0.3 + (er120 + er60) * 50 * 0.2

    return sorted(candidates, key=score, reverse=True)[:n]


def pick_short_term(candidates: List[Candidate], n: int) -> List[Candidate]:
    def score(c: Candidate) -> float:
        s = 0.0
        if c.sma13 and c.sma27 and c.close > c.sma13 > c.sma27:
            s += 1.0
        elif c.sma13 and c.close > c.sma13:
            s += 0.4
        if 50 <= c.rsi14 <= 65:
            s += 0.8
        elif 40 <= c.rsi14 < 50:
            s += 0.3
        if c.volume_burst == 1:
            s += 0.5
        if c.kd_golden_cross == 1:
            s += 0.4
        if c.foreign_net and c.foreign_net > 0 and c.volume > 0:
            s += min(0.5, c.foreign_net / c.volume * 50)
        if c.news_sentiment_avg is not None and c.news_sentiment_avg > 0:
            s += min(0.5, c.news_sentiment_avg)
        if c.is_gap == 1 and c.change_pct > 0:
            s += 0.3
        if c.volume < 100_000:
            s -= 1.0
        return s

    return sorted(candidates, key=score, reverse=True)[:n]


# ---------- main entry ----------

def screen_market() -> Dict[str, Dict[str, List[Candidate]]]:
    """Returns {bucket_label: {horizon: [Candidate,...]}}."""
    print("[1/4] Loading market snapshot…", flush=True)
    snap = db.market_snapshot()
    print(f"      {len(snap)} tickers", flush=True)

    print("[2/4] Loading industry + shares maps (2 queries)…", flush=True)
    industry_map = db.all_industries()
    shares_map = db.all_shares_outstanding()
    print(f"      industries: {len(industry_map)}, shares: {len(shares_map)}", flush=True)

    print("[3/4] Loading chip + features (2 queries)…", flush=True)
    chip_map = db.all_latest_chipscore()
    feat_map = db.all_latest_features()
    print(f"      chipscore: {len(chip_map)}, features: {len(feat_map)}", flush=True)

    # Build candidates
    candidates: List[Candidate] = []
    for row in snap:
        c = build_candidate(row, industry_map, shares_map)
        enrich_from_chip_map(c, chip_map)
        enrich_from_features_map(c, feat_map)
        candidates.append(c)

    # Bucket
    by_bucket: Dict[str, List[Candidate]] = {label: [] for label, _, _ in PRICE_BUCKETS}
    for c in candidates:
        for label, lo, hi in PRICE_BUCKETS:
            if lo <= c.close < hi:
                by_bucket[label].append(c)
                break

    # Pick
    result: Dict[str, Dict[str, List[Candidate]]] = {}
    final_picks: List[Candidate] = []
    for label, _, _ in PRICE_BUCKETS:
        bucket = by_bucket.get(label, [])
        longs = pick_long_term(bucket, PICKS_PER_HORIZON)
        shorts = pick_short_term(bucket, PICKS_PER_HORIZON)
        for c in longs:
            c.horizon = "long"
        for c in shorts:
            c.horizon = "short"
        result[label] = {"long": longs, "short": shorts}
        final_picks.extend(longs + shorts)

    # Long-term returns from daily_data2_full (compute ourselves since stock_features is null for 60d/240d)
    target_date = db.latest_date("daily_data2_full")
    print(f"[4/4] Computing long-term returns for {len(final_picks)} picks (target={target_date})…", flush=True)
    enrich_long_term_returns(final_picks, target_date)
    enrich_news_for_picks(final_picks)

    # Zen (纏論) for ALL picks (long + short)
    print(f"[5/5] Running zen analyzer on {len(final_picks)} picks (all horizons)…", flush=True)
    for c in final_picks:
        try:
            r = zen.analyze(c.ticker, days=120)
            c.zen_position = r.position
            c.zen_bias = r.bias
            if r.center:
                c.zen_center = f"{r.center.low:.2f}–{r.center.high:.2f}"
            c.zen_summary = zen.format_read(r)
        except Exception as e:  # noqa: BLE001
            c.zen_summary = f"zen 分析失敗: {e}"

    return result


if __name__ == "__main__":
    result = screen_market()
    for label, _, _ in PRICE_BUCKETS:
        if label not in result:
            continue
        longs = result[label]["long"]
        shorts = result[label]["short"]
        print(f"\n=== {label} ===")
        print(f"  Long-term:")
        for c in longs:
            er240 = c.excess_return_240d or 0
            cap = c.market_cap or 0
            print(f"    {c.ticker} {c.name[:14]:14s} 收盤 {c.close:>8.2f}  市值 {cap/1e9:>6.0f}億  240d {er240:+.1%}")
        print(f"  Short-term:")
        for c in shorts:
            print(f"    {c.ticker} {c.name[:14]:14s} 收盤 {c.close:>8.2f}  RSI {c.rsi14:.1f}  chip {c.chip_score or 0:.1f}  新聞 {c.news_count_5d}則")
