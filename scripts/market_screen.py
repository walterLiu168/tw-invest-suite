"""
Market screener — picks 6 candidates per price bucket (3 short-term + 3 long-term).

Price buckets (Taiwan listed + OTC):
    <100        銅板股
    100-300     中價股
    300-1000    中高價股
    >1000       高價股

Selection logic per bucket:
    * Long-term (3 picks): market cap + calendar-day raw PRICE returns.
      Existing excess_return_60d/120d/240d/500d names are compatibility fields;
      they are NOT dividend-adjusted total returns or benchmark excess returns.
    * Short-term (3 picks): momentum + chip signals + news sentiment

Data source: MySQL `tw_elec` database via db_client.py (no API calls).
Batch queries for speed (1,943 stocks × per-stock lookups = slow).
"""
import os
import sys
import math
from dataclasses import dataclass, replace, field
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
    score: Optional[float] = None
    score_details: Dict = field(default_factory=dict)
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
    c.volume_burst = _i(chip["VolumeBurst"]) if chip.get("VolumeBurst") is not None else None
    c.kd_golden_cross = _i(chip["KD_GoldenCross"]) if chip.get("KD_GoldenCross") is not None else None
    c.inv_first_in = _i(chip.get("Inv_FirstIn"))
    c.inv_buy_percent = _f(chip.get("Inv_BuyPercent"))
    c.foreign_buy_ratio_chip = _f(chip.get("ForeignBuyRatio"))


def enrich_from_features_map(c: Candidate, feat_map: Dict[str, Dict]) -> None:
    """Consume volume_ratio_20d; 20d excess is descriptive only, not a score."""
    f = feat_map.get(c.ticker)
    if not f:
        return
    c.excess_return_20d = float(f['excess_return_20d']) if f.get('excess_return_20d') is not None else None
    ratio = f.get('volume_ratio_20d')
    c.volume_burst = (int(float(ratio) >= 2.0)
                      if ratio is not None and math.isfinite(float(ratio)) and float(ratio) >= 0 else None)


def enrich_long_term_returns(candidates: List[Candidate], target_date: str) -> None:
    """Compute 60d/120d/240d/500d returns from daily_data2_full in batch."""
    if not candidates:
        return
    tickers = [c.ticker for c in candidates]
    returns = db.long_term_returns_batch(tickers, target_date)
    for c in candidates:
        ret = returns.get(c.ticker, {})
        c.excess_return_60d = ret.get("ret_60d")
        c.excess_return_120d = ret.get("ret_120d")
        c.excess_return_240d = ret.get("ret_240d")
        c.excess_return_500d = ret.get("ret_500d")


def enrich_news_for_picks(picks: List[Candidate], target_date: Optional[str] = None) -> None:
    """One bounded DB query for ALL candidates before scoring; legacy name."""
    if not picks:
        return
    tickers = [c.ticker for c in picks]
    news_map = db.news_for_tickers(tickers, limit_per=5, days=5, target_date=target_date)
    for c in picks:
        news = news_map.get(c.ticker, [])
        c.news_count_5d = len(news)
        sents = [_f(n.get("sentiment_score")) for n in news if n.get("sentiment_score") is not None]
        if sents:
            c.news_sentiment_avg = sum(sents) / len(sents)
        c.news_headlines = [n.get("title", "") for n in news[:3]]


# ---------- ranking ----------

def _percentile_scores(candidates: List[Candidate], field: str) -> Dict[str, float]:
    """Return deterministic 0..100 cross-sectional percentile scores."""
    valid = [(c.ticker, getattr(c, field)) for c in candidates
             if getattr(c, field) is not None]
    valid = [(ticker, float(value)) for ticker, value in valid]
    result = {c.ticker: 0.0 for c in candidates}
    if not valid:
        return result
    ordered = sorted(valid, key=lambda item: (item[1], item[0]))
    n = len(ordered)
    if n == 1:
        result[ordered[0][0]] = 100.0
        return result
    i = 0
    while i < n:
        j = i
        while j + 1 < n and ordered[j + 1][1] == ordered[i][1]:
            j += 1
        percentile = ((i + j) / 2) / (n - 1) * 100.0
        for k in range(i, j + 1):
            result[ordered[k][0]] = percentile
        i = j + 1
    return result


def long_term_score(candidates: List[Candidate]) -> Dict[str, float]:
    """Normalize cap and each return before applying long-term weights."""
    cap = _percentile_scores(candidates, "market_cap")
    er240 = _percentile_scores(candidates, "excess_return_240d")
    er120 = _percentile_scores(candidates, "excess_return_120d")
    er60 = _percentile_scores(candidates, "excess_return_60d")
    return {
        c.ticker: round(
            cap[c.ticker] * 0.50
            + er240[c.ticker] * 0.30
            + er120[c.ticker] * 0.10
            + er60[c.ticker] * 0.10,
            4,
        )
        for c in candidates
    }


def short_term_score(c: Candidate) -> float:
    """Rule-based short-term score retained in its native point scale."""
    parts = dict(trend=0.0, rsi=0.0, volume_burst=0.0, kd_cross=0.0,
                 foreign_flow=0.0, news=0.0, gap=0.0, liquidity=0.0)
    if c.sma13 and c.sma27 and c.close > c.sma13 > c.sma27:
        parts['trend'] = 1.0
    elif c.sma13 and c.close > c.sma13:
        parts['trend'] = 0.4
    if 50 <= c.rsi14 <= 65:
        parts['rsi'] = 0.8
    elif 40 <= c.rsi14 < 50:
        parts['rsi'] = 0.3
    if c.volume_burst == 1:
        parts['volume_burst'] = 0.5
    if c.kd_golden_cross == 1:
        parts['kd_cross'] = 0.4
    if c.foreign_net and c.foreign_net > 0 and c.volume > 0:
        parts['foreign_flow'] = min(0.5, c.foreign_net / c.volume * 50)
    if c.news_sentiment_avg is not None and c.news_sentiment_avg > 0:
        parts['news'] = min(0.5, c.news_sentiment_avg)
    if c.is_gap == 1 and c.change_pct > 0:
        parts['gap'] = 0.3
    if c.volume < 100_000:
        parts['liquidity'] = -1.0
    c.score_details = {'version': 'short_rules_v2', 'contributions': parts,
                       'inputs': {'close': c.close, 'sma13': c.sma13, 'sma27': c.sma27,
                                  'rsi14': c.rsi14, 'volume_burst': c.volume_burst,
                                  'kd_cross': c.kd_golden_cross, 'foreign_net': c.foreign_net,
                                  'volume': c.volume, 'news_sentiment': c.news_sentiment_avg,
                                  'is_gap': c.is_gap, 'change_pct': c.change_pct},
                       'missing_optional': [name for name, value in
                           [('volume_burst', c.volume_burst), ('kd_cross', c.kd_golden_cross),
                            ('news', c.news_sentiment_avg)] if value is None],
                       'zen_role': 'post_selection_description', 'tie_break': 'ticker_ascending'}
    return round(sum(parts.values()), 4)

def pick_long_term(candidates: List[Candidate], n: int) -> List[Candidate]:
    """Long-term: normalize cap and each return, then apply fixed weights."""
    scores = long_term_score(candidates)
    for c in candidates:
        c.score = scores[c.ticker]
        c.score_details = {'version': 'long_percentile_v1', 'return_definition': db.RETURN_DEFINITION,
                           'weights': {'market_cap': 0.5, 'price_return_240d': 0.3,
                                       'price_return_120d': 0.1, 'price_return_60d': 0.1},
                           'inputs': {'market_cap': c.market_cap, 'price_return_240d': c.excess_return_240d,
                                      'price_return_120d': c.excess_return_120d, 'price_return_60d': c.excess_return_60d},
                           'missing_optional': [key for key in ('market_cap', 'excess_return_240d',
                                                 'excess_return_120d', 'excess_return_60d')
                                                if getattr(c, key) is None],
                           'tie_break': 'ticker_ascending'}
    return sorted(candidates, key=lambda c: (-scores[c.ticker], c.ticker))[:n]


def pick_short_term(candidates: List[Candidate], n: int) -> List[Candidate]:
    for c in candidates:
        c.score = short_term_score(c)
    return sorted(candidates, key=lambda c: (-float(c.score or 0), c.ticker))[:n]


def pick_horizons(candidates: List[Candidate], n: int):
    """Long and short lists for one bucket, with no name in both.

    The two rankings are independent over the same bucket, so the same name
    can top both and would then occupy two of the daily slots -- the published
    watchlist would then claim 24 names while showing fewer.  The short list
    therefore skips the names the long list already took and takes the next
    best instead.

    Returns (longs, shorts, reused): `reused` names the slots that had to be
    used twice because the bucket did not hold enough distinct candidates.
    """
    longs = [replace(c, horizon="long") for c in pick_long_term(candidates, n)]
    long_tickers = {c.ticker for c in longs}
    pool = pick_short_term(candidates, len(candidates))
    shorts = [replace(c, horizon="short") for c in pool
              if c.ticker not in long_tickers][:n]
    reused: List[str] = []
    if len(shorts) < n:
        # The bucket does not hold enough distinct names. Give back the lowest
        # ranked long slot rather than breaking the fixed daily slot count.
        by_ticker = {x.ticker: x for x in pool}
        used = {c.ticker for c in shorts}
        for c in reversed(longs):
            if len(shorts) >= n:
                break
            source = by_ticker.get(c.ticker)
            if source is not None and c.ticker not in used:
                shorts.append(replace(source, horizon="short"))
                used.add(c.ticker)
                reused.append(c.ticker)
    return longs, shorts, reused


# ---------- main entry ----------

def screen_market(enforce_features: bool = False) -> Dict[str, Dict[str, List[Candidate]]]:
    """Returns {bucket_label: {horizon: [Candidate,...]}}."""
    print("[1/4] Loading market snapshot…", flush=True)
    snap = db.market_snapshot()
    print(f"      {len(snap)} tickers", flush=True)

    print("[2/4] Loading industry + shares maps (2 queries)…", flush=True)
    industry_map = db.all_industries()
    shares_map = db.all_shares_outstanding()
    print(f"      industries: {len(industry_map)}, shares: {len(shares_map)}", flush=True)

    print("[3/4] Loading chip + features (2 queries)…", flush=True)
    target_date = db.latest_date("daily_data2_full")
    chip_map = db.all_latest_chipscore(target_date)
    feat_map = db.all_latest_features(target_date)
    print(f"      chipscore: {len(chip_map)}, features: {len(feat_map)}", flush=True)
    if enforce_features:
        db.assert_feature_freshness(
            target_date,
            [row["Ticker"] for row in snap],
            min_coverage=0.95,
        )

    # Build candidates
    candidates: List[Candidate] = []
    for row in snap:
        c = build_candidate(row, industry_map, shares_map)
        enrich_from_chip_map(c, chip_map)
        enrich_from_features_map(c, feat_map)
        candidates.append(c)

    if enforce_features:
        # The independent 18:20 screen may precede the legacy sync. Derive
        # missing KD from the same canonical date, not an older chip table.
        if any(c.kd_golden_cross is None for c in candidates):
            signals = db.screen_signal_features(target_date)
            for c in candidates:
                if c.kd_golden_cross is None:
                    c.kd_golden_cross = signals.get(c.ticker, {}).get('KD_GoldenCross')
        valid_kd = sum(c.kd_golden_cross in (0, 1) for c in candidates)
        if candidates and valid_kd == 0:
            raise RuntimeError(f'consumed-field gate failed: KD_GoldenCross={valid_kd}/{len(candidates)} date={target_date}')
        print(f'      KD valid={valid_kd}/{len(candidates)}; individual missing values remain unknown', flush=True)

    # The existing long-term score reads these returns, so populate them before ranking.
    print(f"[4/5] Computing returns for {len(candidates)} candidates (target={target_date})…", flush=True)
    enrich_long_term_returns(candidates, target_date)
    enrich_news_for_picks(candidates, target_date)

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
    reused_slots: List[str] = []
    for label, _, _ in PRICE_BUCKETS:
        bucket = by_bucket.get(label, [])
        longs, shorts, reused = pick_horizons(bucket, PICKS_PER_HORIZON)
        if reused:
            reused_slots.extend(f"{label}:{t}" for t in reused)
        result[label] = {"long": longs, "short": shorts}
        final_picks.extend(longs + shorts)
    if reused_slots:
        print(f"      bucket exhausted, slot reused for {', '.join(reused_slots)}", flush=True)

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
