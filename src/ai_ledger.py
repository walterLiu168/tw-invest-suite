"""The AI's own paper account: what it picks, when it buys and sells, and
whether that has been worth doing.

This is the account Walter mirrors with real money (it funds the service bill),
so the rules are written down, versioned and printed on the page itself.  The
ledger is append-only: a session's record is never rewritten, and every entry
carries the rule version it was traded under.

Rules (v1 - the same text is rendered on the page):

  R1  Decisions are made on a session's close and every fill is that close.
  R2  Entry pool: the published 24 picks of the session, long side only.
      Short picks are recorded as avoided names and never take part in P&L.
  R3  At most 6 positions at a time, equal weight, no adding to a position.
  R4  One trade per stock per session: buy or sell, never both.
  R5  Exit on the first of: dropped out of the published 24, maintenance rate
      below 130%, 20 sessions held, or a 12% stop from the entry price.
  R6  Costs: 0.1425% commission each way (20 TWD minimum), 0.3% securities tax
      on the sell.
  R7  Cash accounting; positions marked to the close every session.
  R8  Benchmark: the equal-weight universe over the same sessions.
  R9  Survive line: over a rolling 20 sessions, net return above zero AND
      excess above zero AND drawdown under 25%.  Three consecutive failures and
      new positions stop until the rules are fixed and pass again.

The first part of the account is a backtest: the rules were written after
looking at that window, so it is labelled 回溯 on purpose.  Everything from the
first live session onwards is the forward record.
"""
from __future__ import annotations

import html
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import pipeline_state as ps

RULES = {
    'version': 'AIV1',
    'max_positions': 6,
    'weight': 1 / 6,
    'hold_sessions': 20,
    'stop_loss': -0.12,
    'commission': 0.001425,
    'commission_min': 20.0,
    'tax_sell': 0.003,
    'maintenance_hard_rule': 130.0,
    'initial_capital': 1_000_000.0,
    'survive_window': 20,
    'max_drawdown': 0.25,
    'kill_switch_periods': 3,
    'lot_size': 1000,
    'rolling_max_drawdown': 0.25,
    'lot_mode': 'odd',
    'fill_model': 'FILL-CLOSE',
}

# ---------------------------------------------------------------------------
# Rule versions.
#
# AIV1 is the frozen record of the backtest and of the live sessions up to
# 2026-11-25.  AIV2 is Walter's 2026-11-26 decision:
#
#   * MDD tolerance on the survive line   25% -> 40%
#   * stop loss                           -12% -> -20%
#   * everything else (kill switch periods, window, exits, costs) unchanged
#
# AIV2 also overturns R1: odd lots (1-999 shares) are traded 9:00-13:30 with
# limit ROD orders only, and an odd-lot trade price is NOT an opening or
# closing auction price.  So "decide at the close, fill at the close" cannot be
# executed in odd lots.  From AIV2 the executable basis is: decide after the
# close, fill at the NEXT session's open.  FILL-CLOSE stays available as a
# reference (whole lots only) and is reported side by side.
#
# The live segment is NOT back-applied: every session is judged by the version
# that was in effect on that session, and the switch date is shown on the page.
# ---------------------------------------------------------------------------

AIV2_START = '2026-11-26'

POLICIES = {
    'AIV1': {
        'version': 'AIV1',
        'stop_loss': -0.12,
        'mdd_tolerance': 0.25,
        'fill_model': 'FILL-CLOSE',
        'lot_mode': 'odd',
        'effective_from': None,
        'note': '原始規則（2026-11-25 live 起用）',
    },
    'AIV2': {
        'version': 'AIV2',
        'stop_loss': -0.20,
        'mdd_tolerance': 0.40,
        'fill_model': 'FILL-NEXT-OPEN',
        'lot_mode': 'odd',
        'effective_from': AIV2_START,
        'note': 'Walter 2026-11-26：MDD 容忍 25%→40%、停損 −12%→−20%、成交改為次日開盤；其餘條款不變',
    },
}
DEFAULT_POLICY = POLICIES['AIV1']


def policy_for(date: str) -> dict:
    """The rule version in effect on `date`."""
    return POLICIES['AIV2'] if date >= AIV2_START else POLICIES['AIV1']

# The benchmark is the equal-weight universe, chained by DAILY RETURN.
# The old one averaged price LEVELS, which is not a return series at all: it
# does not compound, and it let the most expensive stocks dominate the average.
# It is kept only as `benchmark_curve_level_legacy` so the page can show what
# it used to report instead of pretending the numbers never moved.
BENCHMARK_VERSION = 'BENCH-v2'
LEGACY_BENCHMARK_VERSION = 'BENCH-v1'
# Five-bank average one-year time deposit (2026-11-25): 1.70% a year.  This is
# the line the account has to clear to beat doing nothing with the money.
SAVINGS_RATE = 0.017
TRADING_DAYS_PER_YEAR = 252
# Walter's real money: 300萬, odd lots, 6 equal-weight positions.
WALTER_CAPITAL = 3_000_000.0
# The shadow track: the same rules as the live account, but the entry pool is
# narrowed to names that are long-term strong and short-term weak.  It is a
# FORWARD record only - it never trades, and it is not the live account.
SHADOW_VERSION = 'AIV2-H3-shadow'

RULE_TEXT = [
    ('R1', '每個交易日在收盤後做決策，成交於次一交易日開盤（可執行口徑，FILL-NEXT-OPEN）；'
           '整股另可選收盤集合競賣（FILL-CLOSE，僅整股做得到）'),
    ('R2', '進場池＝當日已發佈的 24 檔精選，只做 long；short 僅記為「當日迴避」'),
    ('R3', f'同時最多持有 {RULES["max_positions"]} 檔、等權（每檔 equity/{RULES["max_positions"]}）、不對既有部位加碼'),
    ('R4', '每檔每交易日最多一筆交易（買或賣），當日已賣不當日買回'),
    ('R5', f'出場（先到先算）：跌出 24 檔／維持率破 {RULES["maintenance_hard_rule"]:.0f}%／'
           f'持有滿 {RULES["hold_sessions"]} 個交易日／自成本價停損'
           f'（AIV1 {POLICIES["AIV1"]["stop_loss"]*100:.0f}%、AIV2 {POLICIES["AIV2"]["stop_loss"]*100:.0f}%）；'
           f'**每個交易日都評估**（沒有發佈精選的日子也照跑停損、持有天數與 130% 條款）'),
    ('R6', f'成本：買賣各手續費 {RULES["commission"]*100:.4f}%（最低 {RULES["commission_min"]:.0f} 元）、賣出證交稅 {RULES["tax_sell"]*100:.1f}%'),
    ('R7', '現金會計：部位成本含攤提費用，每日以收盤價重估，權益＝現金＋部位市值'),
    ('R8', f'基準＝同一批交易日的等權全市場（{BENCHMARK_VERSION}：等權日報酬鏈接，母體＝與選股同一個篩選後 universe）'),
    ('R9', f'判定線：滾動 {RULES["survive_window"]} 個交易日，淨報酬 > 0 且超額 > 0 且'
           f'**該窗口內**最大回撤 < {POLICIES["AIV1"]["mdd_tolerance"]*100:.0f}%（AIV1）／'
           f'< {POLICIES["AIV2"]["mdd_tolerance"]*100:.0f}%（AIV2）；'
           f'連續 {RULES["kill_switch_periods"]} 個週期不達線 → 停止新進場'
           f'（**此條尚未實作**：AIV1／AIV2 的 live 段都沒有接上這個保護）'),
    ('R10', '零股（1～999 股）：盤中 9:00–13:30、限價 ROD、僅電子單、'
            '不得融資融券與借券賣出、**零股成交價不作為開盤／收盤價**；'
            '單筆最低手續費 20 元 → 小部位實際費率遠高於 0.1425%'),
]

HISTORY_DIR = 'ai-ledger-history'
SUMMARY_FILE = 'ai-ledger.json'


# ---------------------------------------------------------------- data access

def load_sessions(cur) -> list[dict]:
    """Published runs and their picks, oldest first."""
    cur.execute("SELECT id, run_date, picks_count FROM market_screen_runs ORDER BY run_date")
    runs = [{'id': str(r['id']), 'date': str(r['run_date']), 'picks_count': r['picks_count']}
            for r in cur.fetchall()]
    cur.execute("""SELECT run_id, ticker, name, industry, horizon, bucket, close_at_pick,
                   change_pct, excess_return_60d, excess_return_240d, score, rationale, status
                   FROM market_screen_picks ORDER BY run_id, ticker, id""")
    picks: dict[str, list[dict]] = {}
    for row in cur.fetchall():
        picks.setdefault(str(row['run_id']), []).append({
            'ticker': str(row['ticker']),
            'name': row['name'] or '',
            'industry': row['industry'] or '',
            'horizon': row['horizon'] or '',
            'bucket': row['bucket'] or '',
            'close': float(row['close_at_pick']) if row['close_at_pick'] is not None else None,
            'change_pct': row['change_pct'],
            'e60': row['excess_return_60d'],
            'e240': row['excess_return_240d'],
            'score': row['score'],
            'rationale': row['rationale'] or '',
            'status': row['status'] or '',
        })
    out = []
    for run in runs:
        run['picks'] = picks.get(run['id'], [])
        out.append(run)
    return out


def maintenance_flags(cur, dates: list[str]) -> dict[str, set[str]]:
    """Tier-1 distress (maintenance rate below 130%) reconstructed per session."""
    if not dates:
        return {}
    cur.execute("""SELECT trade_date, ticker FROM finmind_taiwan_margin_maintenance
                   WHERE margin_maintenance < %s""", (RULES['maintenance_hard_rule'],))
    flags: dict[str, set[str]] = {}
    for row in cur.fetchall():
        flags.setdefault(str(row['trade_date']), set()).add(str(row['ticker']))
    return flags


def load_prices(cur, first_date: str) -> tuple[list[str], dict, dict]:
    """Sessions, closes and opens from the screener's universe.

    `Close > 0` is not cosmetic.  daily_data2_full keeps rows with a 0 close
    for names that stopped trading (1,749 rows over 76 dates in the 2026-08
    window, about 20 a day).  An unfiltered equal-weight benchmark turns every
    one of them into a -100% day, which is how the old benchmark ended up
    reporting a market that fell 48% when the same market fell 14%.  Filtering
    also stops a zero close from wiping out a position's value.

    The open is needed by FILL-NEXT-OPEN: odd lots have no closing call
    auction, so the executable fill is the next session's open.
    """
    cur.execute("SELECT DISTINCT Date FROM daily_data2_full WHERE Date >= %s ORDER BY Date", (first_date,))
    sessions = [str(r['Date']) for r in cur.fetchall()]
    cur.execute("""SELECT Ticker, Date, Open, Close FROM daily_data2_full
                   WHERE Date >= %s AND Close > 0""", (first_date,))
    closes, opens = {}, {}
    for row in cur.fetchall():
        ticker, date = str(row['Ticker']), str(row['Date'])
        closes[(ticker, date)] = float(row['Close'])
        if row['Open'] is not None and float(row['Open']) > 0:
            opens[(ticker, date)] = float(row['Open'])
    return sessions, closes, opens


def load_closes(cur, first_date: str) -> tuple[list[str], dict]:
    """Kept for callers that only need the closes."""
    sessions, closes, _ = load_prices(cur, first_date)
    return sessions, closes


# ------------------------------------------------------------------ the engine

def _commission(amount: float) -> float:
    return max(amount * RULES['commission'], RULES['commission_min'])


def simulate(sessions, runs_by_date, flags, closes, opens=None, *,
             policy_for_date=None, entry_filter=None, capital=None,
             max_positions=None, weight=None,
             published_days_only=False) -> dict:
    """Run the rules over the sessions and return the trades and the equity curve.

    The rule calendar is EVERY TRADING DAY, not every published day.  A session
    without a published picks list still marks positions to market and still
    evaluates the exits that do not need a list: the 130% maintenance rule, the
    stop loss and the 20-session hold cap.  "Dropped out of the published 24"
    does need a list, so it stays a published-day exit.

    The old engine skipped unpublished sessions entirely, which did three
    things wrong at once: the stop loss did not fire on 13 of the 70 trading
    days of the sample, positions were not revalued on those days, and the
    equity curve was missing them - so the drawdown was measured on 57 points
    instead of 70.  The faithful reading of R5 is the trading-day calendar,
    because in live operation the account is checked every day.
    (`published_days_only=True` restores the old behaviour; it is kept so the
    page can show what the account used to report.)

    `entry_filter` narrows the ENTRY pool only (the shadow track uses it).
    A pick that fails it stays published, so the "dropped out of the 24" exit
    test still sees it - filtering must not quietly change the exit rules.

    The fill model comes from the policy in effect on that session:
    FILL-CLOSE fills at the session's close, FILL-NEXT-OPEN fills at the next
    session's open.  A position sized for a next-open fill uses the equity
    that was known at the previous close, never a price that only exists later.
    """
    capital = capital if capital is not None else RULES['initial_capital']
    policy_for_date = policy_for_date or policy_for
    opens = opens or {}
    cash = capital
    positions: dict[str, dict] = {}
    trades: list[dict] = []
    equity: list[dict] = []
    pending_sells: list[dict] = []
    pending_buys: list[dict] = []
    known_equity = capital
    weight = weight if weight is not None else RULES['weight']
    max_positions = max_positions if max_positions is not None else RULES['max_positions']
    state = {'cash': cash}

    def sell(ticker, date, price, reason, policy):
        position = positions.pop(ticker)
        amount = position['shares'] * price
        fee = _commission(amount)
        tax = amount * RULES['tax_sell']
        state['cash'] += amount - fee - tax
        net = amount - fee - tax - position['cost']
        trades.append({
            'date': date, 'ticker': ticker, 'name': position['name'], 'action': 'sell',
            'price': price, 'shares': position['shares'], 'fee': fee, 'tax': tax,
            'reason': reason, 'reason_text': EXIT_TEXT.get(reason, reason),
            'pnl': net, 'pnl_pct': net / position['cost'] if position['cost'] else 0.0,
            'held_sessions': position['sessions_held'], 'entry_date': position['entry_date'],
            'entry_price': position['entry_price'], 'rule_version': policy['version'],
            'effective_rate': (fee + tax) / amount if amount else 0.0,
            'rationale': position['rationale'],
        })

    def buy(pick, date, price, policy):
        """Buy one pick.  Returns True when the trade actually happened.

        A buy that fails (no affordable lot, not enough cash) is not a trade:
        R4 counts trades, not attempts, so the ticker stays available.
        """
        if policy['fill_model'] == 'FILL-CLOSE':
            # the decision is made after this close, so today's equity is known
            base = state['cash'] + sum(p['shares'] * (closes.get((t, date)) or p['entry_price'])
                                       for t, p in positions.items())
        else:
            # a next-open fill must be sized on what was known at the previous
            # close - never on a price that only exists later
            base = known_equity
        budget = base * weight
        lot = RULES['lot_size'] if policy.get('lot_mode') == 'whole' else 0
        if lot:
            budget = (int(budget / (price * lot)) * price * lot)
        shares = int(budget / price)
        if shares < 1:
            return False
        amount = shares * price
        fee = _commission(amount)
        if amount + fee > state['cash']:
            return False
        state['cash'] -= amount + fee
        positions[pick['ticker']] = {
            'entry_date': date, 'entry_price': price, 'shares': shares,
            'cost': amount + fee, 'name': pick['name'], 'industry': pick['industry'],
            'bucket': pick['bucket'], 'sessions_held': 0, 'rationale': pick['rationale'],
            'e60': pick['e60'], 'e240': pick['e240'], 'score': pick['score'],
        }
        trades.append({
            'date': date, 'ticker': pick['ticker'], 'name': pick['name'], 'action': 'buy',
            'price': price, 'shares': shares, 'fee': fee, 'tax': 0.0, 'reason': 'published_pick',
            'reason_text': '當日已發佈的 24 檔精選（long）', 'pnl': 0.0, 'pnl_pct': 0.0,
            'held_sessions': 0, 'entry_date': date, 'entry_price': price,
            'rule_version': policy['version'],
            'effective_rate': fee / amount if amount else 0.0,
            'rationale': pick['rationale'],
        })
        return True

    for date in sessions:
        run = runs_by_date.get(date)
        if published_days_only and not run:
            continue
        policy = policy_for_date(date)
        picks = run['picks'] if run else []
        published = {p['ticker'] for p in picks}
        danger = flags.get(date, set())
        traded_today: set[str] = set()
        next_open = policy['fill_model'] == 'FILL-NEXT-OPEN'

        # ---- 1. execute what the previous session decided (at this open)
        for order in pending_sells:
            ticker = order['ticker']
            if ticker not in positions:
                continue
            price = opens.get((ticker, date))
            if price is None:
                continue
            sell(ticker, date, price, order['reason'], policy)
            traded_today.add(ticker)
        for order in pending_buys:
            ticker = order['ticker']
            if ticker in positions or ticker in traded_today or len(positions) >= max_positions:
                continue
            price = opens.get((ticker, date))
            if not price:
                continue
            if buy(order['pick'], date, price, policy):
                traded_today.add(ticker)
        pending_sells, pending_buys = [], []

        # ---- 2. exits first: a stock that is sold today cannot be bought today
        for ticker in list(positions):
            position = positions[ticker]
            reason = None
            price = closes.get((ticker, date))
            if price is None:
                continue
            if ticker in danger:
                reason = 'danger_maintenance'
            elif (policy['stop_loss'] is not None and position['cost'] > 0
                  and price / position['entry_price'] - 1 <= policy['stop_loss']):
                reason = 'stop_loss'
            elif position['sessions_held'] >= RULES['hold_sessions']:
                reason = 'hold_cap'
            elif run and ticker not in published:
                reason = 'dropped_out'
            if not reason:
                continue
            if next_open:
                pending_sells.append({'ticker': ticker, 'reason': reason})
            else:
                sell(ticker, date, price, reason, policy)
                traded_today.add(ticker)

        # ---- 3. entries: the published long picks, in published order
        for pick in picks:
            if len(positions) >= max_positions:
                break
            ticker = pick['ticker']
            if pick['horizon'] != 'long' or ticker in positions or ticker in traded_today:
                continue
            if entry_filter is not None and not entry_filter(pick):
                continue
            price = pick['close'] or closes.get((ticker, date))
            if not price:
                continue
            if next_open:
                pending_buys.append({'ticker': ticker, 'pick': pick})
            else:
                if buy(pick, date, price, policy):
                    traded_today.add(ticker)

        # ---- 4. mark to market
        for position in positions.values():
            position['sessions_held'] += 1
        value = state['cash'] + sum(p['shares'] * (closes.get((t, date)) or p['entry_price'])
                                    for t, p in positions.items())
        equity.append({'date': date, 'equity': value, 'cash': state['cash'],
                       'positions': len(positions),
                       'trades': len([t for t in trades if t['date'] == date]),
                       'rule_version': policy['version']})
        known_equity = value

    return {'trades': trades, 'equity': equity, 'cash': state['cash'], 'positions': positions}


EXIT_TEXT = {
    'danger_maintenance': '融資維持率破 130%（危險名單 tier 1）',
    'stop_loss': '自成本價停損',
    'hold_cap': '持有滿 20 個交易日',
    'dropped_out': '跌出當日已發佈的 24 檔',
    'published_pick': '當日已發佈的 24 檔精選（long）',
}


def equity_value(cash: float, positions: dict, closes: dict, date: str) -> float:
    value = cash
    for ticker, position in positions.items():
        price = closes.get((ticker, date)) or position['entry_price']
        value += position['shares'] * price
    return value


def benchmark_curve(sessions, closes) -> list[dict]:
    """Equal-weight universe, chained by daily return (BENCH-v2).

    Each session the benchmark is the equal-weight average of the daily return
    of every ticker that has both a previous close and this close; the series
    is that average compounded day by day.  A session with no usable data is
    reported as unknown (level None) - never as 0, because 0 would silently
    claim the market did not move.
    """
    by_date: dict[str, dict[str, float]] = {}
    for (ticker, date), close in closes.items():
        by_date.setdefault(date, {})[ticker] = close
    curve = []
    previous: dict[str, float] = {}
    level = 1.0
    for date in sessions:
        prices = by_date.get(date) or {}
        if not prices:
            curve.append({'date': date, 'level': None, 'daily_return': None, 'constituents': 0})
            continue
        returns = [prices[t] / previous[t] - 1.0 for t in prices
                   if t in previous and previous[t] > 0]
        if not returns:
            # No previous close to compare with: the market's move that day is
            # unknown, so the level is unknown too.  The chain resumes from the
            # last known level on the next session.
            curve.append({'date': date, 'level': None, 'daily_return': None,
                          'constituents': len(prices)})
            previous = prices
            continue
        daily = sum(returns) / len(returns)
        level *= (1 + daily)
        curve.append({'date': date, 'level': level, 'daily_return': daily,
                      'constituents': len(returns)})
        previous = prices
    return curve


def benchmark_curve_level_legacy(sessions, closes) -> list[dict]:
    """The old benchmark: average price LEVEL, normalised.  Kept for the
    old/new comparison on the page; it is not a return series."""
    by_date: dict[str, list[float]] = {}
    for (ticker, date), close in closes.items():
        by_date.setdefault(date, []).append(close)
    curve = []
    base = None
    for date in sessions:
        values = by_date.get(date)
        if not values:
            continue
        level = sum(values) / len(values)
        if base is None:
            base = level
        curve.append({'date': date, 'level': level / base})
    return curve


def benchmark_level_before(benchmark, date) -> float | None:
    """The benchmark level of the last session before `date` (1.0 if none)."""
    level = None
    for point in benchmark:
        if point['date'] < date:
            level = point['level']
        else:
            break
    return level


def savings_period_return(sessions: int) -> float:
    """What the deposit would have paid over the SAME span as the account.

    1.7% a year is a yearly rate; comparing it with a 57-session return
    without annualising would make the account look worse than it is.  Both
    sides are put on the same clock: sessions / 252 trading days a year.
    """
    if sessions <= 0:
        return 0.0
    return (1 + SAVINGS_RATE) ** (sessions / TRADING_DAYS_PER_YEAR) - 1


def annualise(net_return: float, sessions: int) -> float | None:
    """The same return expressed as a yearly rate (None if it cannot be)."""
    if sessions <= 0 or net_return <= -1:
        return None
    return (1 + net_return) ** (TRADING_DAYS_PER_YEAR / sessions) - 1


def metrics(equity: list[dict], benchmark: list[dict], capital: float | None = None) -> dict:
    if not equity:
        return {}
    start = capital if capital is not None else RULES['initial_capital']
    end = equity[-1]['equity']
    net = end / start - 1
    bench_level = None
    for point in benchmark:
        if point.get('level') is not None:
            bench_level = point['level']
    bench = (bench_level - 1) if bench_level is not None else None
    peak = start
    drawdown = 0.0
    for point in equity:
        peak = max(peak, point['equity'])
        drawdown = min(drawdown, point['equity'] / peak - 1)
    excess = (net - bench) if bench is not None else None
    sessions = len(equity)
    savings = savings_period_return(sessions)
    yearly = annualise(net, sessions)
    return {
        'sessions': sessions,
        'start_date': equity[0]['date'],
        'end_date': equity[-1]['date'],
        'net_return': net,
        'benchmark_return': bench,
        'excess': excess,
        'savings_period_return': savings,
        'excess_vs_savings': net - savings,
        'annualised_net_return': yearly,
        'annualised_excess_vs_savings': (yearly - SAVINGS_RATE) if yearly is not None else None,
        'max_drawdown': drawdown,
        'final_equity': end,
        'cash': equity[-1]['cash'],
        'positions': equity[-1]['positions'],
    }


def rolling(equity: list[dict], benchmark: list[dict], window: int,
            capital: float | None = None,
            policy_for_date=None) -> dict:
    """The survive line over a rolling window of sessions.

    Both sides of the comparison are measured over the SAME window: the
    account's return from the session before the window to its last session,
    and the market's return over the same span.  (The old code compared a
    20-session window against the market's return since inception, which made
    the gate far stricter than R9 describes.)  The drawdown clause R9 prints
    is enforced here too.  An unknown benchmark is never read as 0.

    The MDD tolerance is the one in force on the window's LAST session, so a
    window that spans the AIV1/AIV2 switch is judged by the version that was
    already in effect when the window closed.
    """
    if len(equity) < window:
        return {}
    base_capital = capital if capital is not None else RULES['initial_capital']
    bench_by_date = {b['date']: b.get('level') for b in benchmark}
    results = []
    for i in range(window - 1, len(equity)):
        chunk = equity[i - window + 1: i + 1]
        start = equity[i - window]['equity'] if i - window >= 0 else base_capital
        net = chunk[-1]['equity'] / start - 1
        end_level = bench_by_date.get(chunk[-1]['date'])
        if i - window >= 0:
            base_level = bench_by_date.get(equity[i - window]['date'])
        else:
            base_level = benchmark_level_before(benchmark, chunk[0]['date'])
        if end_level is None or not base_level:
            bench = None
        else:
            bench = end_level / base_level - 1
        peak = start
        drawdown = 0.0
        for point in chunk:
            peak = max(peak, point['equity'])
            drawdown = min(drawdown, point['equity'] / peak - 1)
        excess = (net - bench) if bench is not None else None
        policy = (policy_for_date(chunk[-1]['date']) if policy_for_date else POLICIES['AIV1'])
        tolerance = policy['mdd_tolerance']
        passed = (excess is not None and net > 0 and excess > 0
                  and abs(drawdown) < tolerance)
        results.append({'end': chunk[-1]['date'], 'net': net, 'excess': excess,
                        'bench': bench, 'max_drawdown': drawdown, 'passed': passed,
                        'mdd_tolerance': tolerance})
    if not results:
        return {}
    passed = sum(1 for r in results if r['passed'])
    latest = results[-1]
    return {
        'window': window,
        'periods': len(results),
        'passed': passed,
        'pass_rate': passed / len(results),
        'latest_net': latest['net'],
        'latest_excess': latest['excess'],
        'latest_bench': latest['bench'],
        'latest_max_drawdown': latest['max_drawdown'],
        'latest_mdd_tolerance': latest['mdd_tolerance'],
        'ok': latest['passed'],
    }


def verdict_line(metrics_row: dict, rolling_row: dict) -> tuple[str, str]:
    if not metrics_row:
        return 'unknown', '尚無足夠的交易紀錄'
    if rolling_row and not rolling_row.get('ok'):
        return 'no_edge', (f'最近 {rolling_row["window"]} 個交易日：淨報酬 {rolling_row["latest_net"]*100:+.2f}%、'
                           f'超額 {rolling_row["latest_excess"]*100:+.2f}pp → 未通過')
    if metrics_row.get('excess') is None:
        return 'unknown', '基準未知，這一期的超額無法計算'
    if metrics_row['excess'] <= 0:
        return 'no_edge', (f'累計超額 {metrics_row["excess"]*100:+.2f}pp → 沒有超額')
    return 'has_edge', (f'累計超額 {metrics_row["excess"]*100:+.2f}pp、'
                        f'最大回撤 {metrics_row["max_drawdown"]*100:.1f}%')


LIVE_START = '2026-11-25'   # the first session traded under the frozen rules


def mean_reversion(pick) -> bool:
    """The shadow rule: long-term strong (e240 > 0) and short-term weak (e60 < 0)."""
    e60, e240 = pick.get('e60'), pick.get('e240')
    return e60 is not None and e240 is not None and e240 > 0 and e60 < 0


def segment_metrics(equity: list[dict], benchmark: list[dict], live: list[dict]) -> dict:
    """metrics() for a slice of the equity curve (the live or shadow segment).

    The market is measured from the last session before the segment started,
    so the segment inherits the backtest's base instead of re-normalising.
    """
    if not live:
        return {}
    live_bench = [b for b in benchmark if b['date'] >= live[0]['date']]
    if not live_bench:
        return {}
    index = equity.index(live[0])
    start_equity = equity[index - 1]['equity'] if index else RULES['initial_capital']
    bench_base = benchmark_level_before(benchmark, live[0]['date'])
    live_net = live[-1]['equity'] / start_equity - 1
    live_level = live_bench[-1].get('level')
    if live_level is None or not bench_base:
        live_bench_return = None
    else:
        live_bench_return = live_level / bench_base - 1
    live_excess = (live_net - live_bench_return) if live_bench_return is not None else None
    sessions = len(live)
    savings = savings_period_return(sessions)
    yearly = annualise(live_net, sessions)
    peak = start_equity
    drawdown = 0.0
    for i, point in enumerate(live):
        peak = max(peak, point['equity'])
        drawdown = min(drawdown, point['equity'] / peak - 1)
    return {
        'sessions': sessions,
        'start_date': live[0]['date'],
        'end_date': live[-1]['date'],
        'net_return': live_net,
        'benchmark_return': live_bench_return,
        'excess': live_excess,
        'savings_period_return': savings,
        'excess_vs_savings': live_net - savings,
        'annualised_net_return': yearly,
        'annualised_excess_vs_savings': (yearly - SAVINGS_RATE) if yearly is not None else None,
        'max_drawdown': drawdown,
        'final_equity': live[-1]['equity'],
        'cash': live[-1]['cash'],
        'positions': live[-1]['positions'],
        'annualisation_reliable': sessions >= TRADING_DAYS_PER_YEAR,
    }


def market_at_exposure(benchmark: list[dict], x: float, dates=None) -> float:
    """The equal-weight market held at a constant exposure x.

    A rule that keeps cash half the time looks good against a falling market
    without any picking skill.  Comparing it with the market at the SAME
    exposure is the only honest way to read "it made money".
    """
    level = 1.0
    for point in benchmark:
        if point.get('daily_return') is None:
            continue
        if dates is not None and point['date'] not in dates:
            continue
        level *= (1 + x * point['daily_return'])
    return level - 1


def build(date: str) -> dict:
    import db_client as db
    with db.get_cursor() as cur:
        runs = load_sessions(cur)
        published_dates = [r['date'] for r in runs]
        flags = maintenance_flags(cur, published_dates)
        first = published_dates[0] if published_dates else date
        sessions, closes, opens = load_prices(cur, first)
    runs_by_date = {r['date']: r for r in runs}
    benchmark = benchmark_curve(sessions, closes)
    legacy_benchmark = benchmark_curve_level_legacy(sessions, closes)

    def fixed(policy):
        return lambda _date, p=policy: p

    def run_sim(policy, capital=None, entry_filter=None, published_days_only=False):
        return simulate(sessions, runs_by_date, flags, closes, opens,
                        policy_for_date=fixed(policy), capital=capital,
                        entry_filter=entry_filter,
                        published_days_only=published_days_only)

    def summarise(sim_result, capital=None):
        base = capital if capital is not None else RULES['initial_capital']
        eq = sim_result['equity']
        exposure = [1.0 - p['cash'] / p['equity'] for p in eq if p['equity']]
        avg_exposure = (sum(exposure) / len(exposure)) if exposure else 0.0
        fees = sum(t.get('fee', 0) + t.get('tax', 0) for t in sim_result['trades'])
        buys = [t for t in sim_result['trades'] if t['action'] == 'buy']
        rates = [t['effective_rate'] for t in sim_result['trades'] if t.get('effective_rate')]
        paired = market_at_exposure(benchmark, avg_exposure)
        m = metrics(eq, benchmark, capital)
        return {
            'metrics': m,
            'rolling': rolling(eq, benchmark, RULES['survive_window'], capital),
            'trades': len(sim_result['trades']),
            'buys': len(buys),
            'avg_exposure': avg_exposure,
            'idle_cash_pct': 100 * (1 - avg_exposure),
            'fees': fees,
            'fees_pct_of_capital': fees / base,
            'avg_effective_rate': (sum(rates) / len(rates)) if rates else None,
            'max_effective_rate': max(rates) if rates else None,
            'distinct_names': len({t['ticker'] for t in buys}),
            'market_at_same_exposure': paired,
            'excess_vs_exposure_paired': (m.get('net_return') - paired) if m.get('net_return') is not None else None,
            'exits': dict(Counter(t['reason'] for t in sim_result['trades'] if t['action'] == 'sell')),
        }

    # ---- canonical: every session judged by the version in force that day
    result = simulate(sessions, runs_by_date, flags, closes, opens)
    equity = result['equity']
    total = metrics(equity, benchmark)
    legacy_total = metrics(equity, legacy_benchmark)
    rolling_row = rolling(equity, benchmark, RULES['survive_window'])

    live = [p for p in equity if p['date'] >= LIVE_START]
    live_total = segment_metrics(equity, benchmark, live)
    live_versions = []
    for point in equity:
        if point['date'] < LIVE_START:
            continue
        version = point.get('rule_version', POLICIES['AIV1']['version'])
        if not live_versions or live_versions[-1]['version'] != version:
            live_versions.append({'from': point['date'], 'version': version})
    live_version_note = ('live 段跨越 ' + '／'.join(v['version'] for v in live_versions)
                          if len({v['version'] for v in live_versions}) > 1 else '')

    # ---- the old rule calendar (exits evaluated only on published days)
    old_result = simulate(sessions, runs_by_date, flags, closes,
                          published_days_only=True)
    old_total = metrics(old_result['equity'], benchmark)
    old_rolling = rolling(old_result['equity'], benchmark, RULES['survive_window'])
    old_live = [p for p in old_result['equity'] if p['date'] >= LIVE_START]
    old_live_total = segment_metrics(old_result['equity'], benchmark, old_live)

    # ---- rule version x fill model, same sample, same benchmark
    aiv1_close = summarise(run_sim(POLICIES['AIV1']))
    aiv1_open = summarise(run_sim({**POLICIES['AIV1'], 'fill_model': 'FILL-NEXT-OPEN'}))
    aiv2_close = summarise(run_sim({**POLICIES['AIV2'], 'fill_model': 'FILL-CLOSE'}))
    aiv2_open = summarise(run_sim(POLICIES['AIV2']))

    # ---- Walter's real account: 300萬, odd lots, next-open fills, 6 positions
    walter_result = run_sim(POLICIES['AIV2'], capital=WALTER_CAPITAL)
    walter = summarise(walter_result, WALTER_CAPITAL)
    # the same rule with whole lots only (the constraint Walter lifted)
    walter_whole = summarise(
        run_sim({**POLICIES['AIV2'], 'lot_mode': 'whole'}, capital=WALTER_CAPITAL),
        WALTER_CAPITAL)

    # ---- the shadow track: same rules, narrower entry pool, never traded
    shadow_result = simulate(sessions, runs_by_date, flags, closes, opens,
                             entry_filter=mean_reversion)
    shadow_equity = shadow_result['equity']
    shadow_total = metrics(shadow_equity, benchmark)
    shadow_live = [p for p in shadow_equity if p['date'] >= LIVE_START]
    shadow_live_total = segment_metrics(shadow_equity, benchmark, shadow_live)
    shadow_rolling = rolling(shadow_equity, benchmark, RULES['survive_window'])
    shadow_summary = summarise(shadow_result)
    shadow_whole = summarise(
        simulate(sessions, runs_by_date, flags, closes, opens,
                 policy_for_date=fixed({**POLICIES['AIV2'], 'lot_mode': 'whole'}),
                 entry_filter=mean_reversion,
                 capital=WALTER_CAPITAL),
        WALTER_CAPITAL)

    kind, note = verdict_line(total, rolling_row)
    live_kind, live_note = verdict_line(live_total, {})
    return {
        'date': date,
        'nightly_id': (ps.read_json(ps.STATE).get('nightly_id') if ps.STATE.is_file() else ''),
        'rule_version': policy_for(date)['version'],
        'rule_versions': POLICIES,
        'policy_switch_date': AIV2_START,
        'live_rule_versions': live_versions,
        'live_version_note': live_version_note,
        'benchmark_version': BENCHMARK_VERSION,
        'savings_rate': SAVINGS_RATE,
        'live_start': LIVE_START,
        'rules': RULES,
        'rule_text': [{'id': rid, 'text': text} for rid, text in RULE_TEXT],
        'metrics': total,
        'metrics_legacy': legacy_total,
        'metrics_published_days_only': old_total,
        'rolling_published_days_only': old_rolling,
        'live_metrics_published_days_only': old_live_total,
        'live_metrics': live_total,
        'rolling': rolling_row,
        'verdict': kind,
        'verdict_note': note,
        'live_verdict': live_kind,
        'live_verdict_note': live_note,
        'rule_comparison': {
            'AIV1_FILL-CLOSE': aiv1_close,
            'AIV1_FILL-NEXT-OPEN': aiv1_open,
            'AIV2_FILL-CLOSE': aiv2_close,
            'AIV2_FILL-NEXT-OPEN': aiv2_open,
            'note': ('同一段母體、同一個基準（BENCH-v2）。AIV1→AIV2 只改 MDD 容許 25%→40% 與停損 −12%→−20%；'
                     'FILL-CLOSE→FILL-NEXT-OPEN 只改成交價（可執行口徑）。'
                     'FILL-CLOSE 只有整股做得到（收盤集合競賣），零股做得到的是 FILL-NEXT-OPEN。'),
        },
        'walter_account': {
            'capital': WALTER_CAPITAL,
            'positions': RULES['max_positions'],
            'lot_mode': 'odd',
            'fill_model': POLICIES['AIV2']['fill_model'],
            'rule_version': POLICIES['AIV2']['version'],
            'odd_lots': walter,
            'whole_lots': walter_whole,
            'note': ('Walter 的實際帳戶口徑：300 萬、只做零股、每檔 equity/6、次日開盤成交。'
                     '「整股」那一列是同一條規則在「只能整股」限制下的樣子，對照用。'),
        },
        'shadow_track': {
            'version': SHADOW_VERSION,
            'rule': '進場池＝24 檔精選中「e240 > 0 且 e60 < 0」的 long（均值回歸）',
            'status': '影子帳：不交易、不進 live，只記錄',
            'metrics': shadow_total,
            'live_metrics': shadow_live_total,
            'rolling': shadow_rolling,
            'summary': shadow_summary,
            'whole_lot_300w': shadow_whole,
            'trades': len(shadow_result['trades']),
            'positions': shadow_result['positions'],
            'cash': shadow_result['cash'],
            'equity': shadow_equity,
            'disclosures': [
                f'未驗證：這條規則是 14 個變體裡在同一段資料上挑出來的最大值（in-sample）。',
                f'只有 {shadow_summary["buys"]} 筆買進、{shadow_summary["distinct_names"]} 檔標的、'
                f'平均曝險 {shadow_summary["avg_exposure"]*100:.1f}%。',
                f'零股解除了「買不起」的限制（同一條規則在「只能整股」的 300 萬口徑下平均曝險只有 '
                f'{shadow_whole["avg_exposure"]*100:.1f}%），所以「H3 與執行約束互斥」這條結論已經不成立。',
                '但樣本只有 2026-08～11 一段 70 個交易日（其中 8、9 月其實是上漲的），跨 regime 未驗證；'
                '而且成交假設會左右正負號（FILL-CLOSE 與 FILL-NEXT-OPEN 的結果不同）——'
                '21 筆已平倉交易、前 3 筆貢獻 159% 的實現損益，這是噪音不是 edge。',
            ],
        },
        'equity': equity,
        'benchmark': benchmark,
        'trades': result['trades'],
        'positions': result['positions'],
        'cash': result['cash'],
        'sessions_available': len(published_dates),
    }


def write(date: str, public: Path) -> dict:
    payload = build(date)
    data_dir = public / 'data'
    data_dir.mkdir(parents=True, exist_ok=True)
    history_dir = data_dir / HISTORY_DIR
    history_dir.mkdir(parents=True, exist_ok=True)
    # The live part is append-only: a session's record is written once, and only
    # for sessions traded under the frozen rules.
    path = history_dir / f'{date}.json'
    if not path.is_file() and date >= LIVE_START:
        ps.atomic_json(path, {
            'date': date,
            # the version in force on THAT session - the live segment is not
            # back-applied, so this changes on 2026-11-26
            'rule_version': policy_for(date)['version'],
            'nightly_id': (ps.read_json(ps.STATE).get('nightly_id') if ps.STATE.is_file() else ''),
            'trades': [t for t in payload['trades'] if t['date'] == date],
            'equity': [p for p in payload['equity'] if p['date'] == date],
        })
    ps.atomic_json(data_dir / SUMMARY_FILE, payload)
    (public / 'ai-ledger.html').write_text(render_html(payload), encoding='utf-8')
    return payload


def _money(value) -> str:
    return f'{value:,.0f}' if value is not None else '—'


def _pct(value, digits=2, dash='—') -> str:
    if value is None:
        return dash
    return f'{value * 100:.{digits}f}%'


def _pp(value, digits=2, dash='—') -> str:
    if value is None:
        return dash
    return f'{value * 100:+.{digits}f}pp'


def _dir(value) -> str:
    if value is None:
        return ''
    return 'up' if value > 0 else ('down' if value < 0 else '')


def render_html(payload: dict) -> str:
    total = payload.get('metrics') or {}
    live = payload.get('live_metrics') or {}
    positions = payload.get('positions') or {}
    trades = payload.get('trades') or []
    date = payload['date']
    verdict = payload.get('verdict', 'unknown')
    mark = {'has_edge': '✅', 'weak_edge': '⚠️', 'no_edge': '❌', 'unknown': '⚪'}.get(verdict, '⚪')
    last_price = {}
    for trade in trades:
        last_price[trade['ticker']] = trade['price']

    rules_rows = ''.join(
        f'<tr><th class="rowhead">{html.escape(r["id"])}</th><td>{html.escape(r["text"])}</td></tr>'
        for r in payload.get('rule_text') or [])

    position_rows = []
    for ticker, position in sorted(positions.items()):
        price = last_price.get(ticker, position['entry_price'])
        pnl = position['shares'] * price - position['cost']
        pnl_pct = pnl / position['cost'] if position['cost'] else 0.0
        position_rows.append(
            '<tr>'
            f'<td class="ticker"><a href="analyze.html?t={ticker}">{ticker}</a>'
            f'<span class="co">{html.escape(position["name"])}</span></td>'
            f'<td class="ind">{html.escape(position["bucket"])}</td>'
            f'<td class="num">{position["entry_date"]}</td>'
            f'<td class="num">{_money(position["entry_price"])}</td>'
            f'<td class="num">{_money(price)}</td>'
            f'<td class="num {_dir(pnl_pct)}">{pnl_pct*100:+.2f}%</td>'
            f'<td class="num {_dir(pnl)}">{_money(pnl)}</td>'
            f'<td class="num">{position["sessions_held"]}</td>'
            f'<td class="reason" title="{html.escape(str(position.get("rationale") or ""))}">'
            f'{html.escape(str(position.get("rationale") or "")[:36])}</td>'
            '</tr>')

    trade_rows = []
    for trade in trades[-40:][::-1]:
        trade_rows.append(
            '<tr>'
            f'<td>{trade["date"]}</td>'
            f'<td class="ticker">{trade["ticker"]}<span class="co">{html.escape(trade["name"])}</span></td>'
            f'<td class="act {"up" if trade["action"] == "buy" else "down"}">{"買" if trade["action"] == "buy" else "賣"}</td>'
            f'<td class="num">{_money(trade["price"])}</td>'
            f'<td class="num">{trade["shares"]:,}</td>'
            f'<td class="num">{_money(trade["fee"] + trade["tax"])}</td>'
            f'<td class="num {_dir(trade["pnl_pct"])}">{trade["pnl_pct"]*100:+.2f}%</td>'
            f'<td class="reason">{html.escape(trade["reason_text"])}</td>'
            '</tr>')

    curve = payload.get('equity') or []
    bench_by_date = {b['date']: b.get('level') for b in payload.get('benchmark') or []}
    polyline = ''
    benchmark_line = ''
    if len(curve) > 1:
        width, height = 960, 180
        first_equity = curve[0]['equity']
        base = bench_by_date.get(curve[0]['date']) or 1.0
        equity_points, bench_points = [], []
        for index, point in enumerate(curve):
            x = 10 + index * (width - 20) / (len(curve) - 1)
            equity_points.append((x, point['equity'] / first_equity))
            level = bench_by_date.get(point['date'])
            if level is not None and base:
                bench_points.append((x, level / base))
        all_values = [v for _, v in equity_points] + [v for _, v in bench_points]
        low, high = min(all_values), max(all_values)
        span = (high - low) or 1.0

        def to_xy(points):
            out = []
            for x, value in points:
                y = height - 10 - (value - low) / span * (height - 20)
                out.append(f'{x:.1f},{y:.1f}')
            return ' '.join(out)
        polyline = to_xy(equity_points)
        benchmark_line = to_xy(bench_points)

    # ---- the old benchmark, side by side, so the change is visible
    legacy = payload.get('metrics_legacy') or {}
    legacy_row = ''
    if legacy:
        legacy_row = (
            '<tr><th class="rowhead">舊口徑（價格水位平均）</th>'
            f'<td class="num">{_pct(legacy.get("benchmark_return"))}</td>'
            f'<td class="num {_dir(legacy.get("excess"))}">{_pp(legacy.get("excess"))}</td>'
            f'<td class="num">{_pct(total.get("savings_period_return"))}</td>'
            f'<td class="num {_dir(total.get("excess_vs_savings"))}">{_pp(total.get("excess_vs_savings"))}</td>'
            f'<td class="num {_dir(total.get("annualised_net_return"))}">{_pct(total.get("annualised_net_return"))}</td>'
            f'<td class="num {_dir(total.get("annualised_excess_vs_savings"))}">{_pp(total.get("annualised_excess_vs_savings"))}</td>'
            '<td class="num muted">基準已被取代</td></tr>')

    # ---- the shadow track, with the disclosures it has to carry
    shadow = payload.get('shadow_track') or {}
    shadow_block = ''
    if shadow:
        m = shadow.get('metrics') or {}
        sm = shadow.get('live_metrics') or {}
        items = ''.join(f'<li>{html.escape(str(text))}</li>'
                        for text in (shadow.get('disclosures') or []))
        shadow_block = f"""
<section>
  <h2>影子帳 {html.escape(str(shadow.get("version") or ""))}</h2>
  <p class="muted">規則：{html.escape(str(shadow.get("rule") or ""))}　狀態：{html.escape(str(shadow.get("status") or ""))}</p>
  <table>
    <thead><tr><th class="rowhead">區段</th><th>淨報酬</th><th>市場</th><th>超額</th>
    <th>同期存款</th><th>超額 vs 同期存款</th><th>年化</th><th>最大回撤</th><th>交易</th></tr></thead>
    <tbody>
      <tr><th class="rowhead">回溯（含事後偏差）</th>
        <td class="num {_dir(m.get("net_return"))}">{_pct(m.get("net_return"))}</td>
        <td class="num {_dir(m.get("benchmark_return"))}">{_pct(m.get("benchmark_return"))}</td>
        <td class="num {_dir(m.get("excess"))}">{_pp(m.get("excess"))}</td>
        <td class="num">{_pct(m.get("savings_period_return"))}</td>
        <td class="num {_dir(m.get("excess_vs_savings"))}">{_pp(m.get("excess_vs_savings"))}</td>
        <td class="num {_dir(m.get("annualised_net_return"))}">{_pct(m.get("annualised_net_return"))}</td>
        <td class="num">{_pct(m.get("max_drawdown"))}</td>
        <td class="num">{shadow.get("trades", 0)}</td></tr>
      <tr><th class="rowhead">live（自 {html.escape(str(shadow.get("live_start") or payload["live_start"]))}）</th>
        <td class="num {_dir(sm.get("net_return"))}">{_pct(sm.get("net_return"))}</td>
        <td class="num {_dir(sm.get("benchmark_return"))}">{_pct(sm.get("benchmark_return"))}</td>
        <td class="num {_dir(sm.get("excess"))}">{_pp(sm.get("excess"))}</td>
        <td class="num">{_pct(sm.get("savings_period_return"))}</td>
        <td class="num {_dir(sm.get("excess_vs_savings"))}">{_pp(sm.get("excess_vs_savings"))}</td>
        <td class="num {_dir(sm.get("annualised_net_return"))}">{_pct(sm.get("annualised_net_return"))}</td>
        <td class="num">{_pct(sm.get("max_drawdown"))}</td>
        <td class="num">{sm.get("sessions", 0)} 日</td></tr>
    </tbody>
  </table>
  <p class="caveat">⚠️ 這條規則<strong>未驗證</strong>，而且它<strong>不交易</strong>——live 段維持 AIV1。
  以下每一條都是必須一起看的揭露：</p>
  <ul class="caveat">{items}</ul>
</section>
"""
    benchmark_note = (
        f'基準口徑已於 {html.escape(payload.get("benchmark_version") or BENCHMARK_VERSION)}  更換：'
        '舊口徑是「每日收盤價格水位平均」（不是報酬），且把 <code>Close = 0</code> 的停牌列算成 −100%，'
        '讓市場看起來跌了 48%；新口徑是「等權日報酬鏈接」，母體與選股相同。')

    disclosures = (
        '<section><h2>必須知道的事（揭露，不是辯護）</h2>'
        '<table><tbody>'
        '<tr><th class="rowhead">1</th><td>帳本寫「同時最多 6 檔、等權」，但實務上大部分交易日只有 5 檔，'
        '而且 10–16% 的資金是常駐現金（買不起下一檔或被規則擋住）。</td></tr>'
        '<tr><th class="rowhead">2</th><td>進場順序＝已發佈清單的「代號升序」，不是依分數、'
        'e240 或 e60 排序 → 選股依據其實是代號順序。</td></tr>'
        '<tr><th class="rowhead">3</th><td><strong>規則日曆已修正</strong>：過去的引擎只在「有發佈精選」的日子'
        '評估出場規則，樣本裡 70 個交易日有 13 天完全沒評估（停損不會觸發、部位不重估、'
        '回撤曲線少 13 個點）。修正後的數字與舊口徑在上表並列，舊口徑不可再引用。</td></tr>'
        '<tr><th class="rowhead">4</th><td><strong>零股有限制</strong>：零股 1～999 股、盤中 9:00–13:30、'
        '限價 ROD、僅電子單、不得融資融券與借券賣出、'
        '<strong>零股成交價不作為開盤／收盤價</strong> → 「收盤決策、收盤成交」在零股下做不到，'
        '所以 live 段改用「收盤後決策、次一交易日開盤成交」。</td></tr>'
        '<tr><th class="rowhead">5</th><td><strong>kill switch 尚未實作</strong>：R9 寫「連續 3 個週期不達線 → '
        '停止新進場」，但引擎沒有實作這條，AIV1 與 AIV2 的 live 段都沒有這個保護。</td></tr>'
        '<tr><th class="rowhead">6</th><td><strong>130% 出場規則無法在長樣本驗證</strong>：'
        '維持率資料只從 2026-08-07 起，比帳本的回溯期短；'
        '在這段樣本裡這條規則實際只觸發過 1～4 筆交易。</td></tr>'
        '</tbody></table></section>')

    live_block = ''
    if live:
        live_reliable = live.get('annualisation_reliable')
        version_note = payload.get('live_version_note') or ''
        switch_note = ''
        if version_note:
            switch_note = (f'<p class="caveat">⚠️ {html.escape(version_note)}：'
                           f'live 段每一天用「當日生效的規則版本」判定，沒有回溯套用。'
                           f'切換日 {html.escape(str(payload.get("policy_switch_date") or ""))}。'
                           f'（AIV1：停損 −12%、MDD 容許 25%、收盤成交；'
                           f'AIV2：停損 −20%、MDD 容許 40%、次日開盤成交）</p>')
        old_live = payload.get('live_metrics_published_days_only') or {}
        old_live_row = ''
        if old_live:
            old_live_row = (
                f'<tr><th class="rowhead">舊口徑（對照）</th>'
                f'<td class="num {_dir(old_live.get("net_return"))}">{_pct(old_live.get("net_return"))}</td>'
                f'<td class="num {_dir(old_live.get("benchmark_return"))}">{_pct(old_live.get("benchmark_return"))}</td>'
                f'<td class="num {_dir(old_live.get("excess"))}">{_pp(old_live.get("excess"))}</td>'
                f'<td class="num">{_pct(old_live.get("savings_period_return"))}</td>'
                f'<td class="num {_dir(old_live.get("excess_vs_savings"))}">{_pp(old_live.get("excess_vs_savings"))}</td>'
                f'<td class="num {_dir(old_live.get("annualised_net_return"))}">{_pct(old_live.get("annualised_net_return"))}</td>'
                f'<td class="num {_dir(old_live.get("max_drawdown"))}">{_pct(old_live.get("max_drawdown"))}</td></tr>')
        live_block = (
            f'<h3>live 記錄（自 {html.escape(payload["live_start"])} 起，{live.get("sessions", 0)} 個交易日）</h3>'
            '<table><tr><th class="rowhead"></th><th>淨報酬</th><th>基準</th><th>超額</th>'
            '<th>同期存款</th><th>超額 vs 同期存款</th><th>年化</th><th>最大回撤</th></tr>'
            f'<tr><th class="rowhead">帳戶</th><td class="num {_dir(live.get("net_return"))}">{_pct(live.get("net_return"))}</td>'
            f'<td class="num {_dir(live.get("benchmark_return"))}">{_pct(live.get("benchmark_return"))}</td>'
            f'<td class="num {_dir(live.get("excess"))}">{_pp(live.get("excess"))}</td>'
            f'<td class="num">{_pct(live.get("savings_period_return"))}</td>'
            f'<td class="num {_dir(live.get("excess_vs_savings"))}">{_pp(live.get("excess_vs_savings"))}</td>'
            f'<td class="num {_dir(live.get("annualised_net_return"))}">{_pct(live.get("annualised_net_return"))}</td>'
            f'<td class="num {_dir(live.get("max_drawdown"))}">{_pct(live.get("max_drawdown"))}</td></tr>'
            + old_live_row + '</table>'
            + switch_note
            + ('' if live_reliable else
               '<p class="caveat">⚠️ 樣本不足：live 段只有 '
               f'{live.get("sessions", 0)} 個交易日，年化數字僅供參考，不可與 1.7% 直接比較。</p>'))


    # ---- the old rule calendar, side by side: the numbers the account used
    # to report (exits were only evaluated on days with a published list).
    old_calendar = payload.get('metrics_published_days_only') or {}
    old_live = payload.get('live_metrics_published_days_only') or {}
    old_calendar_row = ''
    if old_calendar:
        old_calendar_row = (
            '<tr><th class="rowhead">舊口徑（規則只在「有發佈精選」的日子評估）</th>'
            f'<td class="num">{_pct(old_calendar.get("benchmark_return"))}</td>'
            f'<td class="num {_dir(old_calendar.get("excess"))}">{_pp(old_calendar.get("excess"))}</td>'
            f'<td class="num">{_pct(old_calendar.get("savings_period_return"))}</td>'
            f'<td class="num {_dir(old_calendar.get("excess_vs_savings"))}">{_pp(old_calendar.get("excess_vs_savings"))}</td>'
            f'<td class="num {_dir(old_calendar.get("annualised_net_return"))}">{_pct(old_calendar.get("annualised_net_return"))}</td>'
            f'<td class="num {_dir(old_calendar.get("annualised_excess_vs_savings"))}">{_pp(old_calendar.get("annualised_excess_vs_savings"))}</td>'
            '<td class="num muted">已修正，僅供對照</td></tr>')

    # ---- rule version x fill model, same sample, same benchmark
    comparison = payload.get('rule_comparison') or {}
    comparison_rows = ''
    for key in ('AIV1_FILL-CLOSE', 'AIV1_FILL-NEXT-OPEN',
                'AIV2_FILL-CLOSE', 'AIV2_FILL-NEXT-OPEN'):
        block = comparison.get(key) or {}
        m = block.get('metrics') or {}
        if not m:
            continue
        version, fill = key.split('_', 1)
        executable = '可執行' if fill == 'FILL-NEXT-OPEN' else '僅整股'
        comparison_rows += (
            f'<tr><th class="rowhead">{html.escape(version)} · {html.escape(fill)}</th>'
            f'<td class="num {_dir(m.get("net_return"))}">{_pct(m.get("net_return"))}</td>'
            f'<td class="num {_dir(m.get("benchmark_return"))}">{_pct(m.get("benchmark_return"))}</td>'
            f'<td class="num {_dir(m.get("excess"))}">{_pp(m.get("excess"))}</td>'
            f'<td class="num">{_pct(block.get("avg_exposure"))}</td>'
            f'<td class="num {_dir(block.get("excess_vs_exposure_paired"))}">{_pp(block.get("excess_vs_exposure_paired"))}</td>'
            f'<td class="num {_dir(m.get("max_drawdown"))}">{_pct(m.get("max_drawdown"))}</td>'
            f'<td class="num">{block.get("buys", 0)}</td>'
            f'<td class="num muted">{html.escape(executable)}</td></tr>')

    # ---- Walter's own account: 300萬, odd lots
    walter = payload.get('walter_account') or {}
    walter_rows = ''
    for label, key in (('零股（可執行口徑）', 'odd_lots'), ('整股（已解除的限制，對照）', 'whole_lots')):
        block = walter.get(key) or {}
        m = block.get('metrics') or {}
        if not m:
            continue
        walter_rows += (
            f'<tr><th class="rowhead">{html.escape(label)}</th>'
            f'<td class="num {_dir(m.get("net_return"))}">{_pct(m.get("net_return"))}</td>'
            f'<td class="num {_dir(m.get("excess"))}">{_pp(m.get("excess"))}</td>'
            f'<td class="num {_dir(m.get("excess_vs_savings"))}">{_pp(m.get("excess_vs_savings"))}</td>'
            f'<td class="num">{_pct(block.get("avg_exposure"))}</td>'
            f'<td class="num {_dir(block.get("excess_vs_exposure_paired"))}">{_pp(block.get("excess_vs_exposure_paired"))}</td>'
            f'<td class="num {_dir(m.get("max_drawdown"))}">{_pct(m.get("max_drawdown"))}</td>'
            f'<td class="num">{block.get("buys", 0)}</td>'
            f'<td class="num">{block.get("distinct_names", 0)}</td>'
            f'<td class="num">{_pct(block.get("avg_effective_rate"), 3)}</td>'
            f'<td class="num">{_pct(block.get("max_effective_rate"), 3)}</td></tr>')

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🧾 AI 帳 — {date}</title>
<style>
:root {{ --bg:#0a0e1a; --panel:#131b2e; --ink:#e6ecf5; --muted:#8aa0c0; --acc:#5fb1ff;
  --border:#1f2942; --red:#ec7063; --green:#58d68d; --amber:#f5b041; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink);
  font-family:-apple-system,"Microsoft JhengHei","Noto Sans TC",system-ui,sans-serif; line-height:1.5; }}
a {{ color:inherit; text-decoration:none; }}
.module-tabs {{ max-width:1500px; margin:0 auto; padding:24px 24px 0; display:flex; flex-wrap:wrap; gap:6px; }}
.mod-tab {{ padding:7px 14px; border:1px solid var(--border); border-radius:8px; color:var(--muted); font-size:.85rem; }}
.mod-tab:hover {{ background:var(--panel); color:var(--ink); }}
.mod-tab.active {{ background:var(--acc); color:#000; border-color:var(--acc); font-weight:600; }}
.hdr {{ max-width:1500px; margin:0 auto; padding:20px 24px 10px; }}
.hdr h1 {{ margin:0 0 6px; font-size:1.6rem; }}
.hdr .sub {{ color:var(--muted); font-size:.92rem; margin:0 0 10px; }}
.hdr .meta {{ display:flex; flex-wrap:wrap; gap:8px; font-size:.82rem; }}
.hdr .pill {{ background:var(--panel); border:1px solid var(--border); border-radius:14px; padding:4px 12px; color:var(--muted); }}
.hdr .pill b {{ color:var(--ink); }}
main {{ max-width:1500px; margin:0 auto; padding:10px 24px 60px; }}
section {{ background:var(--panel); border:1px solid var(--border); border-radius:12px; padding:14px 16px; margin:0 0 16px; }}
section h2 {{ margin:0 0 8px; font-size:1.02rem; }}
section h3 {{ margin:14px 0 4px; font-size:.9rem; }}
table {{ width:100%; border-collapse:collapse; font-size:.83rem; }}
th {{ text-align:left; padding:7px 10px; color:var(--muted); border-bottom:1px solid var(--border); font-weight:600; white-space:nowrap; }}
td {{ padding:6px 10px; border-bottom:1px solid rgba(31,41,66,.6); vertical-align:top; }}
td.num {{ text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }}
td.ticker {{ white-space:nowrap; }}
td.ticker a {{ color:var(--acc); font-weight:600; }}
td.ticker .co {{ display:block; color:var(--muted); font-size:.74rem; max-width:9rem; overflow:hidden; text-overflow:ellipsis; }}
td.ind {{ color:var(--muted); max-width:6rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
td.act {{ font-weight:600; }}
td.reason {{ color:var(--muted); max-width:15rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
th.rowhead {{ color:var(--muted); font-weight:500; }}
.up {{ color:var(--red); }}
.down {{ color:var(--green); }}
.muted {{ color:var(--muted); }}
.verdict {{ font-size:.92rem; }}
.verdict.has_edge {{ color:var(--green); }}
.verdict.no_edge {{ color:var(--red); }}
.verdict.unknown {{ color:var(--muted); }}
.caveat {{ color:var(--amber); font-size:.82rem; margin:4px 0 0; }}
.chart {{ width:100%; height:180px; }}
.chart .eq {{ fill:none; stroke:var(--acc); stroke-width:2; }}
.chart .bm {{ fill:none; stroke:var(--muted); stroke-width:1.5; stroke-dasharray:4 4; }}
.legend {{ display:flex; gap:16px; font-size:.78rem; color:var(--muted); margin:6px 0 0; }}
.sw {{ display:inline-block; width:18px; height:3px; vertical-align:middle; margin-right:5px; }}
.sw.eq {{ background:var(--acc); }}
.sw.bm {{ background:var(--muted); }}
</style>
</head>
<body>
<nav class="module-tabs">
  <a class="mod-tab" href="readme.html">🏠 首頁</a>
  <a class="mod-tab" href="danger.html">⚠️ 危險名單</a>
  <a class="mod-tab active" href="ai-ledger.html">🧾 AI 帳</a>
  <a class="mod-tab" href="watchlist.html">📊 24 檔精選</a>
  <a class="mod-tab" href="watchlist-history.html">📜 精選歷史</a>
  <a class="mod-tab" href="sectors.html">🌊 板塊輪動</a>
  <a class="mod-tab" href="chips.html">💎 籌碼排行</a>
  <a class="mod-tab" href="concepts.html">🔥 概念股</a>
  <a class="mod-tab" href="chips-advanced.html">📡 籌碼進階</a>
  <a class="mod-tab" href="chips-history.html">🕐 歷史回看</a>
  <a class="mod-tab" href="monitor.html">📲 籌碼監控</a>
</nav>
<div class="hdr">
  <h1>🧾 AI 帳</h1>
  <p class="sub">AI 自己挑、自己買賣的模擬帳戶 — 規則固定、帳本 append-only、績效對同一批交易日的等權全市場</p>
  <div class="meta">
    <div class="pill">📅 資料日 <b>{date}</b></div>
    <div class="pill">💰 權益 <b>{_money(total.get("final_equity"))}</b></div>
    <div class="pill">💵 現金 <b>{_money(total.get("cash"))}</b></div>
    <div class="pill">📦 部位 <b>{total.get("positions", 0)}</b></div>
    <div class="pill">📈 淨報酬 <b class="{_dir(total.get("net_return"))}">{_pct(total.get("net_return"))}</b></div>
    <div class="pill">⚖️ 超額 <b class="{_dir(total.get("excess"))}">{_pp(total.get("excess"))}</b></div>
    <div class="pill">🏦 超額 vs 存款 <b class="{_dir(total.get("excess_vs_savings"))}">{_pp(total.get("excess_vs_savings"))}</b></div>
    <div class="pill">🔻 最大回撤 <b>{_pct(total.get("max_drawdown"))}</b></div>
    <div class="pill">🧭 規則版本 <b>{html.escape(payload["rule_version"])}</b></div>
    <div class="pill">📏 基準口徑 <b>{html.escape(payload.get("benchmark_version") or BENCHMARK_VERSION)}</b></div>
  </div>
</div>
<main>
<section>
  <h2>判定</h2>
  <p class="verdict {verdict}">{mark} <b>{html.escape(payload.get("verdict_note") or "")}</b></p>
  <p class="caveat">⚠️ 這一頁是帳本的自我審計，不是績效保證。規則是在看過資料之後定的，
  所以 {html.escape(payload["live_start"])} 之前那段是回溯（含事後偏差），之後才是乾淨的前瞻紀錄。
  進場規則至今沒有被證明有效——帳本只是把市場的漲跌用同一套規則重演一遍。</p>
  <table>
    <thead><tr><th class="rowhead">口徑</th><th>市場基準</th><th>超額</th>
    <th>同期存款 {payload.get("savings_rate", SAVINGS_RATE)*100:.1f}%/年</th>
    <th>超額 vs 同期存款</th><th>年化</th><th>年化 vs {payload.get("savings_rate", SAVINGS_RATE)*100:.1f}%</th></tr></thead>
    <tbody>
      <tr><th class="rowhead">{html.escape(payload.get("benchmark_version") or BENCHMARK_VERSION)}（現行）</th>
      <td class="num {_dir(total.get("benchmark_return"))}">{_pct(total.get("benchmark_return"))}</td>
      <td class="num {_dir(total.get("excess"))}">{_pp(total.get("excess"))}</td>
      <td class="num">{_pct(total.get("savings_period_return"))}</td>
      <td class="num {_dir(total.get("excess_vs_savings"))}">{_pp(total.get("excess_vs_savings"))}</td>
      <td class="num {_dir(total.get("annualised_net_return"))}">{_pct(total.get("annualised_net_return"))}</td>
      <td class="num {_dir(total.get("annualised_excess_vs_savings"))}">{_pp(total.get("annualised_excess_vs_savings"))}</td></tr>
      {legacy_row}
      {old_calendar_row}
    </tbody>
  </table>
  <p class="caveat">{benchmark_note}</p>
  {live_block}
</section>
{disclosures}
<section>
  <h2>規則版本 × 成交模型（同一段母體、同一個基準）</h2>
  <p class="muted">{html.escape(str((payload.get('rule_comparison') or {}).get('note') or ''))}</p>
  <table>
    <thead><tr><th class="rowhead">組合</th><th>淨報酬</th><th>市場</th><th>超額</th>
    <th>平均曝險</th><th>vs 曝險配對市場</th><th>最大回撤</th><th>買進</th><th>可執行性</th></tr></thead>
    <tbody>{comparison_rows}</tbody>
  </table>
  <p class="caveat">⚠️ 曝險配對對照組＝同一段期間、同一個曝險率的等權市場（{html.escape(payload.get("benchmark_version") or BENCHMARK_VERSION)}）。
  一條規則如果只是「少做、留現金」，在下跌段看起來會贏；只有跟同曝險的市場比，才能分出有沒有選股能力。</p>
</section>
<section>
  <h2>Walter 的帳戶口徑（300 萬）</h2>
  <p class="muted">{html.escape(str(walter.get('note') or ''))}</p>
  <table>
    <thead><tr><th class="rowhead">執行方式</th><th>淨報酬</th><th>超額</th><th>超額 vs 同期存款</th>
    <th>平均曝險</th><th>vs 曝險配對市場</th><th>最大回撤</th><th>買進</th><th>檔數</th>
    <th>平均實際費率</th><th>最高實際費率</th></tr></thead>
    <tbody>{walter_rows}</tbody>
  </table>
  <p class="caveat">⚠️ 「實際費率」＝(手續費＋證交稅)／成交金額。零股仍受單筆最低手續費 20 元限制，
  所以小部位的有效費率遠高於名目 0.1425%＋0.3%。</p>
</section>
{shadow_block}
<section>
  <h2>規則（帳本每筆都記錄這個版本）</h2>
  <table><tbody>{rules_rows}</tbody></table>
</section>
<section>
  <h2>目前部位</h2>
  <table>
    <thead><tr><th>標的</th><th>價位帶</th><th>進場日</th><th>進場價</th><th>現價</th>
    <th>未實現%</th><th>未實現金額</th><th>持有日</th><th>進場理由</th></tr></thead>
    <tbody>{''.join(position_rows) or '<tr><td class="muted" colspan="9">目前沒有部位</td></tr>'}</tbody>
  </table>
</section>
<section>
  <h2>權益曲線</h2>
  <svg class="chart" viewBox="0 0 960 180" preserveAspectRatio="none">
    <polyline class="bm" points="{benchmark_line}"/>
    <polyline class="eq" points="{polyline}"/>
  </svg>
  <div class="legend"><span><span class="sw eq"></span>帳戶權益</span><span><span class="sw bm"></span>等權全市場</span></div>
</section>
<section>
  <h2>交易帳本（最近 40 筆）</h2>
  <table>
    <thead><tr><th>日期</th><th>標的</th><th>動作</th><th>成交價</th><th>股數</th>
    <th>費用</th><th>損益</th><th>依據</th></tr></thead>
    <tbody>{''.join(trade_rows) or '<tr><td class="muted" colspan="8">尚無交易</td></tr>'}</tbody>
  </table>
</section>
</main>
</body>
</html>
"""


def main() -> int:
    from report_inputs import report_date
    date = report_date()
    payload = write(date, ps.PUBLIC)
    total = payload.get('metrics') or {}
    print(f"ai_ledger: date={date} equity={total.get('final_equity', 0):,.0f} "
          f"net={total.get('net_return', 0)*100:+.2f}% excess={total.get('excess', 0)*100:+.2f}pp "
          f"positions={total.get('positions', 0)} trades={len(payload.get('trades') or [])}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
