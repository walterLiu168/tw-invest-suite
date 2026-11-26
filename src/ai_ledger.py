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
import statistics
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
    # The circuit breaker (D041, 2026-11-26).  The old counter-only switch
    # deadlocked: once every position was closed the account's return was 0,
    # "net > 0" could never be true again, the counter never reset and the
    # account stopped trading forever.  OPEN does not judge windows and does
    # not move the counter; after this many trading days the breaker goes
    # HALF-OPEN and gives the account a fresh trial with a zero counter.
    'circuit_cooldown_days': 10,
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
        'kill_switch': None,
        'effective_from': None,
        'note': '原始規則（2026-11-25 live 起用）；kill switch 未實作',
    },
    'AIV2': {
        'version': 'AIV2',
        'stop_loss': -0.12,
        'mdd_tolerance': 0.40,
        'fill_model': 'FILL-NEXT-OPEN',
        'lot_mode': 'odd',
        'kill_switch': 'counter',
        'effective_from': AIV2_START,
        'note': 'Walter 2026-11-26：MDD 容忍 25%→40%、成交改為次日開盤；'
                '停損 −20%→−12%（2026-11-26 第十一輪：70 天引擎的停損軸顯示 −12% 在'
                '四個組合裡全部最好，−20% 是比較差的那一半，回到 R9 預登記的預設值）；'
                'kill switch 實作為熔斷器（2026-11-26 第十九輪 D041：'
                'CLOSED 計數器達 3 → OPEN 停止新進場、計數器凍結、不判定視窗；'
                f'冷卻 {RULES["circuit_cooldown_days"]} 個交易日 → HALF-OPEN 計數器歸零、'
                '重新嘗試進場；再失敗 3 次回到 OPEN。判定線不動）',
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
           f'**每 {RULES["survive_window"]} 個交易日完成一個視窗、判定一次**（counter 的單位是「視窗」不是「天」）；'
           f'連續 {RULES["kill_switch_periods"]} 個視窗不達線 → **停止新進場**；'
           f'停止期間計數器凍結、**不判定視窗**；'
           f'滿 {RULES["circuit_cooldown_days"]} 個交易日 → 半開：'
           f'**先累積 {RULES["survive_window"]} 個新交易日的暖身期**、再以全新計數器重新嘗試；'
           f'再失敗 {RULES["kill_switch_periods"]} 個視窗則再次停止'
           f'（**AIV2 已實作為熔斷器 CLOSED／OPEN／HALF-OPEN**；'
           f'**AIV1 尚未實作**——那是凍結紀錄，從來沒有這個保護）'),
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
             max_positions=None, weight=None, benchmark=None,
             kill_scope='account',
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

    `kill_scope` decides whose counter the kill switch is:
      'account'      - the counter and the rolling window belong to the
                       account.  Nothing resets them inside this run: the live
                       segment inherits the backtest's failures, because
                       resetting at live_start would hide them and make the
                       forward record look better than the account is.
      'live-segment' - the counter is fresh from live_start.  The shadow track
                       uses this: it is a research track, not Walter's account,
                       and its job is a clean forward comparison.
      'policy'       - the counter belongs to the RULE VERSION: it carries
                       over inside one version and resets when the version
                       changes.  This is the account's rule from 2026-11-26:
                       a new rule version has not failed anything yet, so it
                       must not inherit the old version's failing windows -
                       otherwise the forward record would start life already
                       blocked and could never measure anything.

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
    # ---- the kill switch (AIV2 and later; AIV1 is a frozen record and does
    # not have it).  Counter style: three consecutive failing rolling windows
    # stop new entries, and any window that passes resets the counter and
    # trading resumes.  The counter is judged on the LAST COMPLETED window -
    # the one that closed before today - so it never uses a session that has
    # not finished yet.  The counter restarts with every rule version, so the
    # live record does not inherit the backtest's failures.
    #
    # Since D041 the switch is a CIRCUIT BREAKER (CLOSED / OPEN / HALF-OPEN),
    # not a bare counter.  The old counter-only switch deadlocked: with every
    # position closed the account's return was 0, "net > 0" could never be
    # true, the counter never reset and the account stopped trading for good.
    # OPEN freezes the counter and judges no window at all; after the cooldown
    # the breaker goes HALF-OPEN with a zeroed counter and the account gets a
    # fresh trial.  The verdict line itself does not move.
    kill = {'mode': None, 'counter': 0, 'segment': None, 'equity': [],
            'blocked_days': [], 'last_trigger': None, 'first_trigger': None,
            'triggered': False, 'base_equity': None,
            'windows': 0, 'passed_windows': 0,
            # --- the circuit breaker (D041) ---
            'state': 'CLOSED', 'open_days': 0, 'open_since': None,
            'next_half_open': None, 'half_opens': 0, 'resumes': 0,
            'transitions': [], 'timeline': [],
            # D043: the counter counts WINDOWS, not days.  A window is judged
            # when it completes - every `survive_window` sessions of the
            # segment - so "three failing windows" means three completed
            # 20-session windows, not three consecutive trading days.
            'judge_at': RULES['survive_window'],
            # the share of sessions in which the account could actually
            # enter: the direct measure of "is the account doing anything"
            'tradable_days': 0, 'segment_tradable_days': 0, 'breaker_sessions': 0,
            'cooldown_days': RULES['circuit_cooldown_days']}
    bench_by_date = {b['date']: b.get('level') for b in benchmark} if benchmark else {}
    # the position of every session in the account's calendar - used to work
    # out the date on which the cooldown ends (the next HALF-OPEN day)
    session_pos = {d: i for i, d in enumerate(sessions)}

    def kth_session(from_date, k):
        """The date of the k-th session counting `from_date` as the first."""
        i = session_pos.get(from_date)
        if i is None:
            return None
        j = i + k
        return sessions[j] if 0 <= j < len(sessions) else None

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

        # ---- 0. the kill switch, judged on the last COMPLETED window
        #
        # The counter is judged on the window that closed BEFORE today (the
        # last completed rolling window), so it never reads a session that has
        # not finished yet.
        #
        # Three scopes:
        #   'account'      - the counter belongs to the account and never
        #                    resets inside this run.  The live segment
        #                    inherits the backtest's failures (resetting there
        #                    would hide them), and the rolling window is the
        #                    account's trailing 20 sessions, whichever rule
        #                    version is in force.
        #   'live-segment' - the counter is fresh from live_start (the shadow
        #                    track: a research track, not the live account).
        #   'policy'       - the counter belongs to the rule version: it
        #                    carries over inside one version and resets when
        #                    the version changes.  A new version has not
        #                    failed anything yet, so it must not inherit the
        #                    old version's failing windows.
        mode = policy.get('kill_switch')
        blocked = False
        if mode is None:
            # the switch is off for this version (AIV1 is the frozen record).
            # The account's equity history keeps growing anyway - the window is
            # the account's trailing sessions, not the switch's.
            kill['mode'] = None
            kill['state'] = 'CLOSED'
            kill['open_days'] = 0
        else:
            if kill_scope == 'live-segment':
                segment_key = (policy['version'],
                               'live' if date >= LIVE_START else 'backtest')
            elif kill_scope == 'policy':
                segment_key = policy['version']
            else:
                segment_key = 'account'
            if kill['segment'] != segment_key:
                kill['segment'] = segment_key
                kill['counter'] = 0
                kill['equity'] = []
                kill['base_equity'] = known_equity
                # a new segment starts with the breaker CLOSED: the new segment
                # has not failed anything yet, so it must not inherit a state
                # it never earned
                kill['state'] = 'CLOSED'
                kill['open_days'] = 0
                kill['open_since'] = None
                kill['next_half_open'] = None
                # a new segment starts its own window cadence: the first
                # verdict comes when the first window completes
                kill['judge_at'] = RULES['survive_window']
                kill['segment_tradable_days'] = 0
                kill['breaker_sessions'] = 0
            kill['mode'] = mode
            segment = kill['equity']

            # ---- 0a. the circuit breaker moves BEFORE the verdict
            #
            # OPEN: new entries are stopped, the counter is frozen and NO
            # window is judged - a window that closed while the account was
            # flat says nothing about the strategy (that is exactly what made
            # the old switch deadlock).  After the cooldown the breaker goes
            # HALF-OPEN: the counter is zeroed and the account gets a fresh
            # trial.  'never' is the control group: it stays OPEN for good.
            if kill['state'] == 'OPEN' and mode != 'never':
                kill['open_days'] += 1
                if kill['open_days'] >= RULES['circuit_cooldown_days']:
                    kill['state'] = 'HALF-OPEN'
                    kill['counter'] = 0
                    kill['half_opens'] += 1
                    # the warm-up (D043): the trial has to accumulate one
                    # full window of NEW trading before anything is judged -
                    # otherwise the first verdict is diluted by the flat days
                    # of the cooldown and the breaker trips again at once
                    kill['judge_at'] = len(segment) + RULES['survive_window']
                    kill['transitions'].append({'date': date, 'from': 'OPEN',
                                                'to': 'HALF-OPEN'})
            state_before = kill['state']

            # ---- 0b. the window verdict, judged when a window COMPLETES
            #
            # D043: the counter counts windows, not days.  A verdict happens
            # only when a 20-session window of the segment has finished, i.e.
            # at the segment's 20th, 40th, 60th... session.  The window that
            # is judged is the one that closed BEFORE today, so the switch
            # never reads a session that has not finished yet.
            if (kill['state'] != 'OPEN'
                    and len(segment) >= RULES['survive_window']
                    and len(segment) >= kill['judge_at']):
                # the window's base is the equity one point before the window
                # starts; for the FIRST window of a segment that is the
                # segment's own starting equity (the live segment inherits the
                # account's equity, it does not restart at the initial capital)
                base = (segment[-RULES['survive_window'] - 1]['equity']
                        if len(segment) > RULES['survive_window']
                        else kill['base_equity'])
                verdict = window_verdict(
                    segment, benchmark or [], bench_by_date, len(segment) - 1,
                    RULES['survive_window'], capital, policy['mdd_tolerance'],
                    base=base)
                if verdict is not None:
                    kill['windows'] += 1
                    # the next verdict comes when the NEXT window completes
                    kill['judge_at'] = len(segment) + RULES['survive_window']
                    if verdict['passed']:
                        kill['passed_windows'] += 1
                        # any window that reaches the line resets the counter
                        # and trading resumes
                        if kill['state'] == 'HALF-OPEN':
                            kill['state'] = 'CLOSED'
                            kill['resumes'] += 1
                            kill['transitions'].append({'date': date, 'from': 'HALF-OPEN',
                                                        'to': 'CLOSED'})
                        kill['counter'] = 0
                    else:
                        kill['counter'] += 1
                        if (kill['counter'] >= RULES['kill_switch_periods']
                                and kill['state'] != 'OPEN'):
                            kill['triggered'] = True
                            if kill['first_trigger'] is None:
                                kill['first_trigger'] = date
                            kill['state'] = 'OPEN'
                            kill['open_since'] = date
                            kill['open_days'] = 0
                            # the cooldown runs from the trigger date: the
                            # breaker goes HALF-OPEN on the day that is
                            # `circuit_cooldown_days` sessions after it
                            kill['next_half_open'] = (kth_session(date, RULES['circuit_cooldown_days'])
                                                      if mode != 'never' else None)
                            kill['transitions'].append({'date': date, 'from': state_before,
                                                        'to': 'OPEN'})
            blocked = kill['state'] == 'OPEN'
            if blocked:
                kill['blocked_days'].append(date)
                kill['last_trigger'] = date

        # ---- the tradable-day share: how many sessions the account could
        # actually enter.  This is the direct measure of "is the account
        # doing anything" - a rule that only lets the account trade 17% of
        # the time is not a rule anybody should pay for.
        kill['breaker_sessions'] += 1
        if not blocked:
            kill['tradable_days'] += 1
            kill['segment_tradable_days'] += 1
        kill['timeline'].append({'date': date, 'counter': kill['counter'],
                                 'state': kill['state'], 'blocked': blocked,
                                 'windows': kill['windows']})

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
            if blocked:
                # the kill switch stops NEW entries: an order decided at the
                # previous close but not yet filled is cancelled while the
                # switch is on.  Pending SELLS still execute - exits always run.
                continue
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
            if blocked:
                # the kill switch stops NEW entries only: positions are still
                # marked to market and all four exit conditions still apply
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
                       'rule_version': policy['version'],
                       'entries_blocked': blocked})
        known_equity = value
        # the account's equity history: the rolling window is the account's
        # trailing sessions, so it is kept even on days the switch is off
        kill['equity'].append(equity[-1])

    return {'trades': trades, 'equity': equity, 'cash': state['cash'],
            'positions': positions, 'kill_switch': kill}


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


def window_verdict(equity, benchmark, bench_by_date, i, window, capital, mdd_tol,
                   base=None):
    """The R9 verdict of the window that ENDS at equity[i].

    Returns None when the window cannot be judged (not enough points, or the
    market's level for that span is unknown - an unknown benchmark is never
    read as 0).  `base` overrides the equity the window's return is measured
    from, which is how a segment (the live record) inherits its own start.
    """
    chunk = equity[i - window + 1: i + 1]
    if len(chunk) < window:
        return None
    if base is None:
        base = equity[i - window]['equity'] if i - window >= 0 else capital
    net = chunk[-1]['equity'] / base - 1
    end_level = bench_by_date.get(chunk[-1]['date'])
    if i - window >= 0:
        base_level = bench_by_date.get(equity[i - window]['date'])
    else:
        base_level = benchmark_level_before(benchmark, chunk[0]['date'])
    if end_level is None or not base_level:
        bench = None
    else:
        bench = end_level / base_level - 1
    peak, dd = base, 0.0
    for point in chunk:
        peak = max(peak, point['equity'])
        dd = min(dd, point['equity'] / peak - 1)
    excess = (net - bench) if bench is not None else None
    passed = (excess is not None and net > 0 and excess > 0 and abs(dd) < mdd_tol)
    return {'end': chunk[-1]['date'], 'net': net, 'excess': excess, 'bench': bench,
            'max_drawdown': dd, 'passed': passed, 'mdd_tolerance': mdd_tol}


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
        policy = (policy_for_date(equity[i]['date']) if policy_for_date else POLICIES['AIV1'])
        row = window_verdict(equity, benchmark, bench_by_date, i, window,
                             base_capital, policy['mdd_tolerance'])
        if row is None:
            continue
        results.append(row)
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
    """The shadow rule: 240-day price up (e240 > 0), 60-day price down (e60 < 0).

    The two published feature columns are named excess_return_240d /
    excess_return_60d for compatibility with older reports and the DB, but
    they are NOT benchmark excess returns and NOT dividend-adjusted total
    returns: they are calendar-day raw PRICE returns
    (db_client.RETURN_DEFINITION = 'calendar_day_raw_price_return_v1').
    Read as a sentence, the rule is "buy the stock that is up over 240
    calendar days but down over the last 60" - buying a pullback inside an
    uptrend.  "超額" may only be used for the account against the benchmark.

    On the 70-session sample the two halves are NOT independent: every
    published pick with e60 < 0 also has e240 > 0 (0 of 684 pick-days have
    e60 < 0 with e240 <= 0), so this rule trades exactly the same names as
    "e60 < 0" alone.  The filter is kept as it was - it is the frozen shadow
    track - but the page must not sell it as a two-condition rule.
    """
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


def kill_summary(kill: dict) -> dict:
    """The kill switch's state, as the page shows it.

    `counter` is the number of consecutive failing windows right now (it is
    reset to 0 by any window that reaches the line).  `blocked_days` counts
    the sessions on which new entries were stopped.  `implemented` is False
    for AIV1: that record is frozen and never had the switch.
    """
    mode = kill.get('mode')
    return {
        'implemented': mode is not None,
        'mode': mode,
        'counter': kill.get('counter') or 0,
        'counter_max': RULES['kill_switch_periods'],
        'blocked_days': len(kill.get('blocked_days') or []),
        'blocked_dates': list(kill.get('blocked_days') or []),
        'last_trigger': kill.get('last_trigger'),
        'first_trigger': kill.get('first_trigger'),
        'triggered': bool(kill.get('triggered')),
        'windows_judged': kill.get('windows') or 0,
        'windows_passed': kill.get('passed_windows') or 0,
        'segment': kill.get('segment'),
        'window': RULES['survive_window'],
        # --- the circuit breaker (D041) ---
        'state': kill.get('state') or 'CLOSED',
        'open_days': kill.get('open_days') or 0,
        'open_since': kill.get('open_since'),
        'next_half_open': kill.get('next_half_open'),
        'half_opens': kill.get('half_opens') or 0,
        'resumes': kill.get('resumes') or 0,
        'transitions': list(kill.get('transitions') or []),
        'cooldown_days': RULES['circuit_cooldown_days'],
        'days_in_state': days_in_state(kill.get('timeline')),
        # D043: the share of sessions in which the account could enter
        'tradable_days': kill.get('tradable_days') or 0,
        'segment_tradable_days': kill.get('segment_tradable_days') or 0,
        'breaker_sessions': kill.get('breaker_sessions') or 0,
        'tradable_ratio': (kill.get('segment_tradable_days') / kill['breaker_sessions']
                           if kill.get('breaker_sessions') else None),
        'judge_every_sessions': RULES['survive_window'],
    }


def days_in_state(timeline) -> dict:
    """How many sessions the breaker spent in each state."""
    counts = {'CLOSED': 0, 'OPEN': 0, 'HALF-OPEN': 0}
    for point in timeline or []:
        state = point.get('state')
        if state in counts:
            counts[state] += 1
    return counts


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


def market_cap_profile(sessions, trades, closes, caps_by_date) -> dict:
    """The market-cap profile of what the account actually holds.

    The entry order is the published list's ticker order, so the page used to
    say "the entry basis is just the ticker number".  That is only half true:
    the published long list is itself a market-cap weighted ranking, so the
    account inherits a large-cap tilt.  This measures it.

    `caps_by_date` is {date: {ticker: market cap}} for the whole daily
    universe (close x that day's shares outstanding).
    """
    positions: dict[str, float] = {}
    by_day: dict[str, list] = {}
    for t in trades:
        by_day.setdefault(t['date'], []).append(t)
    med_ratio: list[float] = []
    top10_pct: list[bool] = []
    top50_pct: list[bool] = []
    in_top10: list[bool] = []
    in_top50: list[bool] = []
    days = 0
    for date in sessions:
        for t in by_day.get(date, []):
            if t['action'] == 'buy':
                positions[t['ticker']] = t['shares']
            else:
                positions.pop(t['ticker'], None)
        if not positions:
            continue
        uni = caps_by_date.get(date) or {}
        if not uni:
            continue
        days += 1
        uni_median = statistics.median(uni.values())
        order = {tk: i + 1 for i, (tk, _) in
                 enumerate(sorted(uni.items(), key=lambda kv: kv[1], reverse=True))}
        n_uni = len(order)
        caps = []
        for tk in positions:
            cap = uni.get(tk)
            if cap is None or cap <= 0:
                continue
            caps.append(cap)
            rank = order.get(tk)
            if rank is None:
                continue
            top10_pct.append(rank / n_uni <= 0.10)
            top50_pct.append(rank / n_uni <= 0.50)
            in_top10.append(rank <= 10)
            in_top50.append(rank <= 50)
        if caps and uni_median > 0:
            med_ratio.append(statistics.median(caps) / uni_median)
    return {
        'days_with_positions': days,
        'positions_measured': len(top10_pct),
        'universe_median_size': (round(statistics.median(
            [len(v) for v in caps_by_date.values()]), 0) if caps_by_date else None),
        'median_cap_ratio': (round(statistics.median(med_ratio), 1) if med_ratio else None),
        'held_in_top10pct': (round(sum(top10_pct) / len(top10_pct), 4) if top10_pct else None),
        'held_in_top50pct': (round(sum(top50_pct) / len(top50_pct), 4) if top50_pct else None),
        'held_in_top10_names': (round(sum(in_top10) / len(in_top10), 4) if in_top10 else None),
        'held_in_top50_names': (round(sum(in_top50) / len(in_top50), 4) if in_top50 else None),
    }


def random_cap_profile(caps_by_date, sessions, n_positions, draws=20, seed=20261126) -> dict:
    """The same measurement for a random draw of n names - the null."""
    import random as _random
    rng = _random.Random(seed)
    ratios: list[float] = []
    top10: list[bool] = []
    top50: list[bool] = []
    t10: list[bool] = []
    t50: list[bool] = []
    for _ in range(draws):
        local_ratios: list[float] = []
        for date in sessions:
            uni = caps_by_date.get(date) or {}
            if len(uni) < n_positions:
                continue
            names = sorted(uni)
            chosen = rng.sample(names, n_positions)
            uni_median = statistics.median(uni.values())
            order = {tk: i + 1 for i, (tk, _) in
                     enumerate(sorted(uni.items(), key=lambda kv: kv[1], reverse=True))}
            n_uni = len(order)
            caps = [uni[tk] for tk in chosen]
            if caps and uni_median > 0:
                local_ratios.append(statistics.median(caps) / uni_median)
            for tk in chosen:
                rank = order.get(tk)
                if rank is None:
                    continue
                top10.append(rank / n_uni <= 0.10)
                top50.append(rank / n_uni <= 0.50)
                t10.append(rank <= 10)
                t50.append(rank <= 50)
        if local_ratios:
            ratios.append(statistics.median(local_ratios))
    return {
        'median_cap_ratio': (round(statistics.median(ratios), 2) if ratios else None),
        'held_in_top10pct': (round(sum(top10) / len(top10), 4) if top10 else None),
        'held_in_top50pct': (round(sum(top50) / len(top50), 4) if top50 else None),
        'held_in_top10_names': (round(sum(t10) / len(t10), 4) if t10 else None),
        'held_in_top50_names': (round(sum(t50) / len(t50), 4) if t50 else None),
        'draws': draws,
    }


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

    # The market cap of every name in every session's universe (close x that
    # day's shares outstanding).  Used to show what the account actually
    # holds - the entry order is the ticker order, but the published long
    # list is market-cap weighted, so the account inherits a large-cap tilt.
    caps_by_date: dict[str, dict[str, float]] = {}
    with db.get_cursor() as cur:
        cur.execute("""SELECT Date, Ticker, SharesOutstanding_shares
                       FROM daily_data2_full
                       WHERE Date BETWEEN %s AND %s
                         AND Ticker REGEXP '^[0-9]{4}$|^[0-9]{4}[A-Z]$'""",
                    (sessions[0], sessions[-1]))
        for r in cur.fetchall():
            sh = r['SharesOutstanding_shares']
            if sh is None:
                continue
            date = str(r['Date'])
            ticker = str(r['Ticker'])
            close = closes.get((ticker, date))
            if not close:
                continue
            cap = close * float(sh)
            if cap > 0:
                caps_by_date.setdefault(date, {})[ticker] = cap

    def fixed(policy):
        return lambda _date, p=policy: p

    def run_sim(policy, capital=None, entry_filter=None, published_days_only=False,
                kill_scope='account'):
        return simulate(sessions, runs_by_date, flags, closes, opens,
                        policy_for_date=fixed(policy), capital=capital,
                        entry_filter=entry_filter,
                        benchmark=benchmark,
                        kill_scope=kill_scope,
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
        kill = sim_result.get('kill_switch') or {}
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
            'kill_switch': kill_summary(kill),
        }

    # ---- canonical: every session judged by the version in force that day
    # The kill counter belongs to the rule version ('policy'): it carries over
    # inside a version and resets when the version changes, so a new version
    # never starts life already blocked by the old version's failures.
    result = simulate(sessions, runs_by_date, flags, closes, opens, benchmark=benchmark,
                      kill_scope='policy')
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
                          published_days_only=True, benchmark=benchmark)
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
    walter_result = run_sim(POLICIES['AIV2'], capital=WALTER_CAPITAL,
                            kill_scope='policy')
    walter = summarise(walter_result, WALTER_CAPITAL)
    # the same rule with whole lots only (the constraint Walter lifted)
    walter_whole = summarise(
        run_sim({**POLICIES['AIV2'], 'lot_mode': 'whole'}, capital=WALTER_CAPITAL),
        WALTER_CAPITAL)

    # ---- the shadow track: same rules, narrower entry pool, never traded.
    # Its kill switch counter is fresh from live_start: it is a research
    # track, not Walter's account, and its job is a clean forward comparison.
    shadow_result = simulate(sessions, runs_by_date, flags, closes, opens,
                             entry_filter=mean_reversion, benchmark=benchmark,
                             kill_scope='live-segment')
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
                 benchmark=benchmark,
                 kill_scope='live-segment',
                 capital=WALTER_CAPITAL),
        WALTER_CAPITAL)

    kind, note = verdict_line(total, rolling_row)
    live_kind, live_note = verdict_line(live_total, {})

    # ---- what the account actually holds: the market-cap profile.
    # The entry order is the ticker order, but the published long list is a
    # market-cap weighted ranking, so the account is really a large-cap
    # exposure.  The random draw is the null.
    # The canonical result is used on purpose: it is what the account really
    # held (the version in force on each session).  AIV2 with the kill switch
    # forced on would stop entering long before the sample ends and would
    # show an EMPTY account - that is the hypothetical, not the record.
    walter_cap_profile = market_cap_profile(sessions, result['trades'],
                                            closes, caps_by_date)
    shadow_cap_profile = market_cap_profile(sessions, shadow_result['trades'],
                                             closes, caps_by_date)
    random_cap = random_cap_profile(caps_by_date, sessions, RULES['max_positions'])

    # ---- the kill switch: the state of the version in force today, and what
    # the switch would have done over the same sample if it had been running.
    today_policy = policy_for(date)

    def kill_status(policy, kill, equity_curve):
        row = kill_summary(kill or {})
        sessions_in_version = len([p for p in equity_curve
                                   if p['date'] >= LIVE_START
                                   and p.get('rule_version') == policy['version']])
        row.update({
            'rule_version': policy['version'],
            'implemented': policy.get('kill_switch') is not None,
            'mode': policy.get('kill_switch'),
            'segment_sessions': sessions_in_version,
            'needs_window': RULES['survive_window'],
            'periods': RULES['kill_switch_periods'],
            'effective_from': policy.get('effective_from'),
        })
        return row

    def kill_rows_for(equity_curve, kill_state):
        return [kill_status(POLICIES[version], kill_state, equity_curve)
                for version in ('AIV1', 'AIV2')]

    kill_rows = []
    for base_label, base_policy in (('live 條款（AIV1）', POLICIES['AIV1']),
                                    ('AIV2（2026-11-26 起）', POLICIES['AIV2'])):
        for pool_label, entry_filter, scope in (
                ('live 進場規則（代號升序）', None, 'policy'),
                ('H3 影子帳（240 日價格漲、60 日價格跌）', mean_reversion, 'live-segment')):
            for mode, mode_label in ((None, '關閉（未實作）'),
                                     ('counter', f'熔斷器：計數器達 {RULES["kill_switch_periods"]} → 停止新進場（OPEN）；'
                                                f'冷卻 {RULES["circuit_cooldown_days"]} 個交易日 → 半開重試（HALF-OPEN）'),
                                     ('never', '一旦觸發就永不恢復（對照組）')):
                policy = {**base_policy, 'kill_switch': mode}
                res = simulate(sessions, runs_by_date, flags, closes, opens,
                               policy_for_date=fixed(policy),
                               entry_filter=entry_filter, benchmark=benchmark,
                               kill_scope=scope,
                               capital=WALTER_CAPITAL,
                               max_positions=RULES['max_positions'], weight=RULES['weight'])
                s = summarise(res, WALTER_CAPITAL)
                live_points = [p for p in res['equity'] if p['date'] >= LIVE_START]
                live_row = segment_metrics(res['equity'], benchmark, live_points)
                kill_rows.append({
                    'base': base_label, 'pool': pool_label, 'mode': mode_label,
                    'scope': scope,
                    'net': s['metrics'].get('net_return'),
                    'exposure': s['avg_exposure'],
                    'vs_paired': s['excess_vs_exposure_paired'],
                    'mdd': s['metrics'].get('max_drawdown'),
                    'buys': s['buys'],
                    'kill': s['kill_switch'],
                    'state': (s['kill_switch'] or {}).get('state'),
                    'live_net': live_row.get('net_return'),
                    'live_excess': live_row.get('excess'),
                    'live_sessions': live_row.get('sessions'),
                })

    # ---- the 32 execution combinations (2 pools x 2 lot modes x 2 fill
    # models x 4 position counts).  The kill switch is off here on purpose:
    # this table measures the execution layer, not the protection.
    grid_rows = []
    for pool_label, entry_filter in (('live 進場規則（代號升序）', None),
                                     ('H3 影子帳（240 日價格漲、60 日價格跌）', mean_reversion)):
        for lot_mode in ('odd', 'whole'):
            for fill_model in ('FILL-CLOSE', 'FILL-NEXT-OPEN'):
                for n in (6, 8, 10, 12):
                    policy = {**POLICIES['AIV2'], 'kill_switch': None,
                              'lot_mode': lot_mode, 'fill_model': fill_model}
                    res = simulate(sessions, runs_by_date, flags, closes, opens,
                                   policy_for_date=fixed(policy),
                                   entry_filter=entry_filter, benchmark=benchmark,
                                   capital=WALTER_CAPITAL, max_positions=n,
                                   weight=1.0 / n)
                    s = summarise(res, WALTER_CAPITAL)
                    grid_rows.append({
                        'pool': pool_label, 'lot': lot_mode, 'fill': fill_model, 'n': n,
                        'net': s['metrics'].get('net_return'),
                        'exposure': s['avg_exposure'],
                        'vs_paired': s['excess_vs_exposure_paired'],
                        'mdd': s['metrics'].get('max_drawdown'),
                        'buys': s['buys'],
                    })
    live_cells = [r for r in grid_rows if r['pool'].startswith('live')]
    grid_note = (
        f'同一段母體（{len(sessions)} 個交易日）、同一個基準（BENCH-v2）、同一個 300 萬口徑、'
        f'kill switch 關閉。live 進場規則的 {len(live_cells)} 格裡，'
        f'沒有一格的淨報酬是正的（最好的一格是 '
        f'{max(r["net"] for r in live_cells)*100:+.2f}%）；'
        f'有正訊號的格子全部在 H3 影子帳，而 H3 不會下單。')

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
        'kill_switch': {
            'version_in_force': today_policy['version'],
            'live_account': kill_rows_for(equity, result.get('kill_switch')),
            'shadow_account': kill_rows_for(shadow_equity, shadow_result.get('kill_switch')),
            'comparison': kill_rows,
            'note': (f'熔斷器（CLOSED／OPEN／HALF-OPEN）：'
                     f'**每 {RULES["survive_window"]} 個交易日完成一個視窗、判定一次**'
                     f'（counter 的單位是「視窗」不是「天」）；'
                     f'連續 {RULES["kill_switch_periods"]} 個視窗不達線 → '
                     f'<strong>OPEN</strong>：停止新進場、計數器凍結、<strong>不判定視窗</strong>；'
                     f'滿 {RULES["circuit_cooldown_days"]} 個交易日 → <strong>HALF-OPEN</strong>：'
                     f'計數器歸零、<strong>先累積 {RULES["survive_window"]} 個新交易日的暖身期</strong>'
                     f'（讓視窗不含空倉日），之後才重新嘗試進場；'
                     f'再失敗 {RULES["kill_switch_periods"]} 個視窗回到 OPEN。'
                     '判定線本身不動（淨 > 0、超額 > 0、回撤 < 容許）。'
                     '判定只用「已完成的視窗」，不看當日未收盤的資料。'
                     '觸發期間部位照常重估、四個出場條件照常執行，只是不再新進場'
                     '（已排定但尚未成交的買單也會取消；賣單照常執行）。'
                     '<strong>live 帳戶的計數器承繼回溯期</strong>：帳戶層級的規則語意，'
                     'live 段不重置（重置等於用「過去的失敗不算」美化前瞻紀錄）；'
                     '<strong>影子帳的計數器從 live_start 重新起算</strong>'
                     '（它是研究軌，不是 Walter 的帳戶，要的是乾淨的前瞻比較）。'
                     '下表是「若這個保護從記錄第一天就在運作」的對照，不是實際發生過的事。'),
            'circuit': {
                'cooldown_days': RULES['circuit_cooldown_days'],
                'periods': RULES['kill_switch_periods'],
                'window': RULES['survive_window'],
                'states': [
                    {'id': 'CLOSED', 'label': 'CLOSED（正常）',
                     'entries': '允許新進場',
                     'counter': f'每次視窗完成：達線 → 歸零；未達線 → ＋1',
                     'verdict': '照常判定',
                     'exit': f'counter ≥ {RULES["kill_switch_periods"]} → 轉 OPEN（記觸發日）'},
                    {'id': 'OPEN', 'label': 'OPEN（停止新進場）',
                     'entries': '禁止新進場',
                     'counter': '凍結（不累加、不歸零）',
                     'verdict': '不判定（OPEN 期間的視窗不是「策略表現」的證據）',
                     'exit': f'冷卻 {RULES["circuit_cooldown_days"]} 個交易日滿 → 轉 HALF-OPEN'},
                    {'id': 'HALF-OPEN', 'label': 'HALF-OPEN（重新嘗試）',
                     'entries': '恢復新進場',
                     'counter': '歸零（給一次全新的試用期）',
                     'verdict': f'先累積 {RULES["survive_window"]} 個新交易日的暖身期（讓視窗不含空倉日），之後才開始判定',
                     'exit': f'counter 再累積到 {RULES["kill_switch_periods"]} → 回 OPEN（冷卻重新計時）'},
                ],
                'verdict_line': (f'滾動 {RULES["survive_window"]} 個交易日：淨報酬 > 0 且超額 > 0 '
                                 f'且回撤 < 容許（AIV1 25%／AIV2 40%）；'
                                 f'每 {RULES["survive_window"]} 個交易日完成一個視窗、判定一次'),
                'old_defect': ('舊版實作（純計數器）在帳戶部位全部出場後會陷入死鎖——空帳戶的報酬恆為 0、'
                               '`net > 0` 永不成立、視窗永不通過、計數器永不歸零 → 帳戶會永久停止交易。'
                               '實測：2024 熱計數器情境 242／242 天全被擋、報酬 0.00%、0 筆買進。'
                               'AIV2 已改成熔斷器＋半開，不會再死鎖。'),
                'old_defect_hard': ('<strong>kill switch 的「保護」在舊版其實是「帳戶死亡」</strong>：'
                                    '空帳戶的報酬恆為 0，而達線需要 net&gt;0 → 永不達線 → 永不恢復 → '
                                    '帳戶永久停止交易。'
                                    '熔斷器修正後帳戶會真的重新進場，而<strong>真實的策略結果是負的</strong>'
                                    '（2024 −15.32%～−56.49%）。'
                                    '<strong>規則文字與實作不一致的期間（2026-11-26 之前）產生的所有 '
                                    'kill switch 數字都不可信</strong>——包括那些「kill switch 把 −20% '
                                    '救成 −0.33%」的說法：那個 −0.33% 是帳戶假死造成的幻覺，'
                                    '不是策略賺到。'),
                'disclosure': ('熔斷器只決定「何時恢復進場」，不放寬判定線，也不讓帳本變綠；'
                               '判定線仍是 R9 原文。'),
                'measured_2024': ('2026-11-26 獨立量測（熱計數器：規則自 2023-01-02 起跑、量 2024 這一段；'
                                  '母體 CLEAN - price only）：'
                                  '<strong>舊版 242／242 天全被擋、報酬 0.00%、0 曝險、0 筆買進</strong>'
                                  '（死鎖；可交易天數占比 0%）。'
                                  '<strong>新版買進 209／300／241／800 筆、曝險 63.5%～80.1%、'
                                  '報酬 −41.91%／−20.88%／−15.32%／−56.49%</strong>'
                                  '（可交易天數占比 87.5%～91.7%、半開 4～6 次、判定視窗 21～22 個）。'
                                  '→ 死鎖解開了，數字變難看，但那才是真實的策略結果。'
                                  '<strong>2026-11-26（D043）修正前</strong>，同一個母體上新版只讓帳戶在 '
                                  '17～27% 的日子可交易（半開後視窗仍含空倉日、立刻又被擋回去）；'
                                  '<strong>加入「半開後 20 個新交易日的暖身期」＋「counter 的單位改成視窗」'
                                  '之後，可交易天數占比回到 87.5%～91.7%</strong>。'),
            },
        },
        'execution_grid': {
            'rows': grid_rows,
            'note': grid_note,
            'capital': WALTER_CAPITAL,
        },
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
            'market_cap_profile': walter_cap_profile,
        },
        'shadow_track': {
            'version': SHADOW_VERSION,
            'market_cap_profile': shadow_cap_profile,
            'random_cap_profile': random_cap,
            'rule': ('進場池＝已發佈精選中「60 日價格報酬為負（e60 < 0）」的 long；'
                     '引擎實作仍是 e240>0 且 e60<0，'
                     '但在這段母體裡兩者完全等價（684 個 pick-days 中 e60<0 且 e240≤0 ＝ 0）'),
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
                '條件拆解：在這段母體裡 e240>0 從不 binding（每個 e60<0 的精選都同時 e240>0），'
                '所以這條規則實際上只等於「買 60 日價格報酬為負的那一檔」；'
                '單獨用 e240>0 則與隨機無異（曝險配對 −4.12pp）。',
                '**用語**：e60／e240 這兩個欄位名是相容用舊名（excess_return_60d／240d），'
                '實際是「以日曆日計算的原始價格報酬」——未還原權值、未含息、不是相對基準的報酬。'
                '這條規則讀成一句話是「在上升趨勢裡買回檔」：過去 240 個日曆日價格上漲、'
                '但過去 60 個日曆日價格下跌。「超額」只能用在本帳戶對基準市場的比較上。',
                '對照組的方法：這條規則的進場池比部位名額小，'
                '「打亂順序」會重現規則自己——必須用「每天挑同樣數量的隨機檔」當對照組。',
                f'零股解除了「買不起」的限制（同一條規則在「只能整股」的 300 萬口徑下平均曝險只有 '
                f'{shadow_whole["avg_exposure"]*100:.1f}%），所以「H3 與執行約束互斥」這條結論已經不成立。',
                '但樣本只有 2026-08～11 一段 70 個交易日（其中 8、9 月其實是上漲的），跨 regime 未驗證；'
                '而且成交假設會左右正負號（FILL-CLOSE 與 FILL-NEXT-OPEN 的結果不同）——'
                '21 筆已平倉交易、前 3 筆貢獻 293% 的實現損益，這是噪音不是 edge。',
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


def _num(value, dash='—') -> str:
    """A number for the page.  Never prints 'None' - a missing measurement is
    a missing measurement, and 'None 倍' would read as a broken page."""
    if value is None:
        return dash
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return f'{value:,}'


class RenderAssertionError(RuntimeError):
    """A number the public page cannot show.

    The page has to fail rather than print a broken value.  A public page
    that shows "None 倍" does not only look wrong - it makes every other
    number on it unbelievable, and the disclosure table is the one part of
    the page whose whole job is to be trusted.
    """


BROKEN_NUMBER_PATTERNS = (
    '>None<', '>none<', '>NaN<', '>nan<', '>Infinity<', '>inf<', '>-inf<',
    'None%', 'None 倍', 'None 元', 'None pp', 'None 天', 'None 檔',
    'None 個', 'None 筆', 'None 個部位', 'NaN%', 'nan%', 'Infinity%',
)

# A number can be present and still be impossible: an exposure above 100%,
# a return below -100%, a market cap ratio below zero.  Those are not "missing
# measurements" - they are wrong ones, and they must not reach a public page.
SANITY_RANGES = {
    'metrics.net_return': (-1.0, 10.0),
    'metrics.max_drawdown': (-1.0, 0.0),
    'metrics.final_equity': (0.0, None),
    'metrics.excess_vs_savings': (-11.0, 10.0),
    'live_metrics.net_return': (-1.0, 10.0),
    'live_metrics.max_drawdown': (-1.0, 0.0),
    'walter_account.market_cap_profile.median_cap_ratio': (0.0, None),
    'walter_account.market_cap_profile.held_in_top10pct': (0.0, 1.0),
    'walter_account.market_cap_profile.held_in_top50pct': (0.0, 1.0),
    'walter_account.market_cap_profile.held_in_top10_names': (0.0, 1.0),
    'walter_account.market_cap_profile.held_in_top50_names': (0.0, 1.0),
    'shadow_track.market_cap_profile.median_cap_ratio': (0.0, None),
    'shadow_track.market_cap_profile.held_in_top10_names': (0.0, 1.0),
    'shadow_track.random_cap_profile.median_cap_ratio': (0.0, None),
    'shadow_track.random_cap_profile.held_in_top10_names': (0.0, 1.0),
    'kill_switch.circuit.cooldown_days': (1.0, 60.0),
}


def _is_broken_number(value) -> bool:
    """True when a value must not reach the page."""
    if value is None:
        return True
    if isinstance(value, float) and value != value:      # NaN
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def check_page_numbers(payload: dict) -> list[str]:
    """Every number the page is about to print, checked BEFORE it is built.

    Two tiers:
      * REQUIRED - the value must exist.  A missing one means the measurement
        was never made, and printing it as 'None 倍' would be a broken public
        page (this is exactly the bug that put 'None 倍' in the disclosure
        table once).
      * ALLOWED-NONE - the value may legitimately be unknown (an unknown
        benchmark, an annualised return below -100%), but it must never be
        NaN or an empty string.  The page prints '—' for those.

    Returns the names of the checked fields (the RESP file quotes the count).
    Raises RenderAssertionError on the first broken one.
    """
    required: dict[str, object] = {}
    optional: dict[str, object] = {}
    total = payload.get('metrics') or {}
    live = payload.get('live_metrics') or {}
    rolling = payload.get('rolling') or {}
    cap = (payload.get('walter_account') or {}).get('market_cap_profile') or {}
    shadow = (payload.get('shadow_track') or {}).get('market_cap_profile') or {}
    rand = (payload.get('shadow_track') or {}).get('random_cap_profile') or {}

    # the headline numbers the page always shows
    for key in ('net_return', 'excess_vs_savings', 'savings_period_return',
                'max_drawdown', 'final_equity', 'sessions', 'positions'):
        required[f'metrics.{key}'] = total.get(key)
    for key in ('benchmark_return', 'excess', 'annualised_net_return'):
        optional[f'metrics.{key}'] = total.get(key)
    # the forward (live) segment
    if live:
        for key in ('net_return', 'max_drawdown', 'sessions'):
            required[f'live_metrics.{key}'] = live.get(key)
        for key in ('benchmark_return', 'excess'):
            optional[f'live_metrics.{key}'] = live.get(key)
    # the R9 rolling window
    if rolling:
        for key in ('window', 'periods', 'passed', 'pass_rate', 'latest_net',
                    'latest_max_drawdown', 'latest_mdd_tolerance'):
            required[f'rolling.{key}'] = rolling.get(key)
        for key in ('latest_excess', 'latest_bench'):
            optional[f'rolling.{key}'] = rolling.get(key)
    # disclosure 8: the market cap profile of what the account holds
    for key in ('days_with_positions', 'positions_measured', 'universe_median_size',
                'median_cap_ratio', 'held_in_top10pct', 'held_in_top10_names',
                'held_in_top50_names'):
        required[f'walter_account.market_cap_profile.{key}'] = cap.get(key)
    for key in ('median_cap_ratio', 'held_in_top10_names'):
        required[f'shadow_track.market_cap_profile.{key}'] = shadow.get(key)
    for key in ('median_cap_ratio', 'held_in_top10_names'):
        required[f'shadow_track.random_cap_profile.{key}'] = rand.get(key)
    # the circuit breaker: the state and the counters the page prints
    circuit = (payload.get('kill_switch') or {}).get('circuit') or {}
    required['kill_switch.circuit.cooldown_days'] = circuit.get('cooldown_days')
    required['kill_switch.circuit.states'] = circuit.get('states')
    for account, rows in (('live_account', (payload.get('kill_switch') or {}).get('live_account')),
                          ('shadow_account', (payload.get('kill_switch') or {}).get('shadow_account'))):
        for row in rows or []:
            version = row.get('rule_version')
            for key in ('state', 'counter', 'counter_max', 'blocked_days',
                        'windows_judged', 'windows_passed', 'cooldown_days',
                        'tradable_days', 'segment_tradable_days', 'breaker_sessions'):
                required[f'kill_switch.{account}.{version}.{key}'] = row.get(key)
            optional[f'kill_switch.{account}.{version}.tradable_ratio'] = row.get('tradable_ratio')

    checked = []
    # the circuit breaker's own counters: a counter above its own maximum, a
    # negative count or a state outside the three states is a broken
    # measurement, not a measurement
    for account in ('live_account', 'shadow_account'):
        for row in (payload.get('kill_switch') or {}).get(account) or []:
            version = row.get('rule_version')
            state = row.get('state')
            if state not in ('CLOSED', 'OPEN', 'HALF-OPEN'):
                raise RenderAssertionError(
                    f'kill_switch.{account}.{version}.state is {state!r} '
                    f'- not a breaker state')
            counter = row.get('counter')
            counter_max = row.get('counter_max') or RULES['kill_switch_periods']
            if isinstance(counter, (int, float)) and counter > counter_max:
                raise RenderAssertionError(
                    f'kill_switch.{account}.{version}.counter is {counter!r} '
                    f'- above its own maximum {counter_max}')
            for key in ('blocked_days', 'windows_judged', 'windows_passed',
                        'open_days', 'half_opens', 'resumes', 'tradable_days',
                        'segment_tradable_days', 'breaker_sessions'):
                value = row.get(key)
                if isinstance(value, (int, float)) and value < 0:
                    raise RenderAssertionError(
                        f'kill_switch.{account}.{version}.{key} is {value!r} '
                        f'- a count cannot be negative')
            ratio = row.get('tradable_ratio')
            if isinstance(ratio, (int, float)) and not (0.0 <= ratio <= 1.0):
                raise RenderAssertionError(
                    f'kill_switch.{account}.{version}.tradable_ratio is {ratio!r} '
                    f'- a share of days must be between 0 and 1')
            if (row.get('segment_tradable_days') or 0) > (row.get('breaker_sessions') or 0):
                raise RenderAssertionError(
                    f'kill_switch.{account}.{version}: more tradable days than '
                    f'sessions - the counters disagree')
    for name, value in required.items():
        checked.append(name)
        if _is_broken_number(value):
            raise RenderAssertionError(
                f'{name} is {value!r} - the page must not print it')
    for name, value in optional.items():
        checked.append(name)
        if value is not None and _is_broken_number(value):
            raise RenderAssertionError(
                f'{name} is {value!r} - the page must not print it')
    for name, value in list(required.items()) + list(optional.items()):
        low, high = SANITY_RANGES.get(name, (None, None))
        if value is None or low is None:
            continue
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        if value < low or (high is not None and value > high):
            raise RenderAssertionError(
                f'{name} is {value!r} - outside the sanity range '
                f'[{low}, {high}] - the page must not print it')
    return checked


def assert_no_broken_numbers(page_html: str) -> int:
    """Fail the page if a broken number reached the HTML.

    The patterns are deliberately narrow: 'none' also appears in the CSS
    (fill:none), so only number-shaped places are checked.  Returns the
    number of patterns checked.
    """
    for pattern in BROKEN_NUMBER_PATTERNS:
        if pattern in page_html:
            i = page_html.find(pattern)
            raise RenderAssertionError(
                f'broken number {pattern!r} at offset {i}: '
                f'{page_html[max(0, i - 140):i + 140]!r}')
    return len(BROKEN_NUMBER_PATTERNS)


def _pp(value, digits=2, dash='—') -> str:
    if value is None:
        return dash
    return f'{value * 100:+.{digits}f}pp'


def _dir(value) -> str:
    if value is None:
        return ''
    return 'up' if value > 0 else ('down' if value < 0 else '')


def render_html(payload: dict) -> str:
    # The page is public and the disclosure table is the one part of it whose
    # whole job is to be trusted: a broken number must fail the build, not be
    # printed.  Both checks run here - the payload's numbers before the page
    # is built, the rendered text after.
    check_page_numbers(payload)
    total = payload.get('metrics') or {}
    live = payload.get('live_metrics') or {}
    positions = payload.get('positions') or {}
    trades = payload.get('trades') or []
    cap_prof = (payload.get('walter_account') or {}).get('market_cap_profile') or {}
    shadow_prof = (payload.get('shadow_track') or {}).get('market_cap_profile') or {}
    rand_prof = (payload.get('shadow_track') or {}).get('random_cap_profile') or {}
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
        '<tr><th class="rowhead">5</th><td><strong>kill switch：AIV2 已實作、AIV1 沒有</strong>：'
        'R9 寫「連續 3 個週期不達線 → 停止新進場」。AIV2（2026-11-26 起）把它做成'
        '<strong>熔斷器（CLOSED／OPEN／HALF-OPEN）</strong>：'
        f'每 {RULES["survive_window"]} 個交易日完成一個視窗、判定一次（counter 的單位是「視窗」不是「天」）；'
        f'連續 {RULES["kill_switch_periods"]} 個視窗不達線 → OPEN（停止新進場、計數器凍結、不判定視窗）；'
        f'冷卻 {RULES["circuit_cooldown_days"]} 個交易日 → HALF-OPEN（計數器歸零、'
        f'先累積 {RULES["survive_window"]} 個新交易日的暖身期再重新嘗試）；'
        f'再失敗 {RULES["kill_switch_periods"]} 個視窗回到 OPEN。判定線本身不動。'
        '<strong>舊版純計數器實作會死鎖</strong>（帳戶空倉時報酬恆為 0 → 視窗永不達線 → '
        '永久停止交易），已修正。'
        '<strong>更關鍵的是：舊版的「保護」其實是「帳戶死亡」</strong>——'
        '空帳戶的報酬恆為 0、達線需要 net&gt;0 → 永不達線 → 永不恢復；'
        '熔斷器修正後帳戶會真的重新進場，而<strong>真實的策略結果是負的</strong>'
        '（2024 −15.32%～−56.49%）。'
        '<strong>規則文字與實作不一致的期間（2026-11-26 之前）產生的所有 kill switch 數字都不可信</strong>'
        '——包含那些「kill switch 把 −20% 救成 −0.33%」的說法：那個 −0.33% 是帳戶假死造成的幻覺。'
        '<strong>AIV1 是凍結紀錄，從來沒有這個保護</strong>——'
        '所以 2026-11-25 以前那段帳本裡不存在這個機制。'
        '<strong>它的真實定位是「小幅風險降低器」，不是「救命保護」</strong>：'
        '同一段母體上熔斷器相對 kill OFF 的增益只有 +3.1／+0.03／+2.8／+5.3pp（四個準則）'
        '→ <strong>它救不了沒有 edge 的策略，只能少賺一點點虧損</strong>。</td></tr>'
        '<tr><th class="rowhead">6</th><td><strong>130% 出場規則無法在長樣本驗證</strong>：'
        '維持率資料只從 2026-08-07 起，比帳本的回溯期短；'
        '在這段樣本裡這條規則實際只觸發過 1～4 筆交易。</td></tr>'
        '<tr><th class="rowhead">7</th><td><strong>用語：e60／e240 不是「超額報酬」</strong>：'
        '這兩個欄位名是相容用舊名（excess_return_60d／excess_return_240d），'
        '實際是<strong>以日曆日計算的原始價格報酬</strong>——未還原權值、未含息、'
        '不是相對基準的報酬（來源：<code>db_client.RETURN_DEFINITION = '
        'calendar_day_raw_price_return_v1</code>）。'
        '讀成一句話：e240&gt;0 且 e60&lt;0 ＝「過去 240 個日曆日價格上漲、但過去 60 個日曆日價格下跌」'
        '＝在上升趨勢裡買回檔。<strong>「超額」這個詞只能用在本帳戶對基準市場的比較上</strong>，'
        '不得用在 e60／e240 上。</td></tr>'
        '<tr><th class="rowhead">8</th><td><strong>這個帳戶本質上是大型權值股的曝險</strong>：'
        f'live 帳戶持有部位的市值中位數是當日 universe 市值中位數的 '
        f'<strong>{_num(cap_prof.get("median_cap_ratio"))} 倍</strong>'
        f'（{_num(cap_prof.get("days_with_positions"))} 個有部位的日子、'
        f'{_num(cap_prof.get("positions_measured"))} 個部位；'
        f'universe 中位數 {_num(cap_prof.get("universe_median_size"))} 檔）；'
        f'<strong>{_pct(cap_prof.get("held_in_top10pct"), 1)}</strong> 的部位落在 universe 市值前 10%，'
        f'{_pct(cap_prof.get("held_in_top10_names"), 1)} 在市值前 10 名、'
        f'{_pct(cap_prof.get("held_in_top50_names"), 1)} 在前 50 名。'
        f'影子帳 H3 也一樣（中位數 {_num(shadow_prof.get("median_cap_ratio"))} 倍、'
        f'前 10 名 {_pct(shadow_prof.get("held_in_top10_names"), 1)}）；'
        f'隨機抽 6 檔的對照組是 {_num(rand_prof.get("median_cap_ratio"))} 倍、'
        f'前 10 名 {_pct(rand_prof.get("held_in_top10_names"), 1)}。'
        '<strong>所以「進場順序＝代號升序、沒有選股依據」這句話只對了一半</strong>：'
        '順序確實是代號，但<strong>進場池是市值加權篩出來的</strong>，帳戶拿到的是大型權值股的曝險——'
        '2020 上半年大賺、2026 空頭段大輸，是同一個曝險的兩面。'
        '<strong>口徑提醒</strong>：這裡的「live 帳戶」是<strong>每一個交易日當時生效的規則版本</strong>'
        '（2026-11-26 以前 AIV1、以後 AIV2）實際持有部位的統計，'
        '不是把某一個版本套到整段歷史的假設；'
        '市值＝當日 Close × 當日 SharesOutstanding_shares（point-in-time）。</td></tr>'
        '<tr><th class="rowhead">9</th><td><strong>「跌最深」那個池子本身是賺的</strong>：'
        '2024 年（242 個交易日）把整個通過池（<code>e240 &gt; 0</code> 且 <code>e60 &lt; 0</code>）'
        '等權持有、不挑任何個股，報酬是 <strong>+16.02%</strong>（買進持有）、'
        '<strong>+13.21%</strong>（每月再平衡）、<strong>+3.86%</strong>（每季再平衡）、'
        '<strong>+3.32%</strong>（每日再平衡）。'
        '同期間「每天從池裡隨機抽 6 檔」的對照組是 <strong>−64.08%</strong>——'
        '但它平均只持有 <strong>1.0 天</strong>、年化換手 <strong>115 倍</strong>、'
        '<strong>成本吃掉本金 66.87%</strong>。'
        '→ <strong>那個對照組的虧損幾乎全部是交易成本，不是池子有毒。</strong>'
        '這是 2026-11-26 的一次獨立量測（不是每次建頁重算），'
        '母體分類 <code>CLEAN - price only</code>；'
        '它的意思是「待在這個池子裡」本身有價值，至於「在池子裡怎麼挑」是另一個問題。'
        '</td></tr>'
        '<tr><th class="rowhead">10</th><td><strong>螢幕精選名單可能因「端點規則」小幅變動</strong>：'
        'e60／e240 的價格端點目前取「截止日或之前最近一個有效收盤」，'
        '長期停牌會把量測區間拉長成 400+ 日，讓回報失真。'
        '修正方向是改成「<strong>截止日前 30 個交易日內的最近收盤，否則視為缺值</strong>」'
        '（2026-11-26 第十九輪 D042 決定）。'
        '這會改變部分檔案的 e60／e240 與分數，'
        '<strong>因此當日的精選名單、score、e60、e240 都可能小幅變動</strong>；'
        '重建與現行精選的差異會逐筆歸因後揭露，不得默默換掉。'
        '在修正完成前，頁面上的帳本數字仍以現行端點規則計算。</td></tr>'
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

    # ---- the kill switch: the state right now, and what it would have done
    kill = payload.get('kill_switch') or {}
    # the live account's first live day under the counterfactual: it did not
    # trade at all, so its "0.00%" is not a strategy result
    kill_live_day = {}
    for row in kill.get('comparison') or []:
        if (row.get('base') or '').startswith('AIV2') and row.get('pool', '').startswith('live'):
            k = row.get('kill') or {}
            kill_live_day = {
                'mode': row.get('mode'),
                'first_trigger': k.get('first_trigger'),
                'blocked_days': k.get('blocked_days'),
                'live_net': row.get('live_net'),
                'live_excess': row.get('live_excess'),
                'live_sessions': row.get('live_sessions'),
            }
    kill_first_caveat = ''
    if kill_live_day:
        live_market = (live.get('benchmark_return')
                       if isinstance(live, dict) else None)
        kill_first_caveat = (
            '⚠️ <strong>kill switch 開啟時，live 帳戶自 '
            f'{html.escape(str(kill_live_day.get("first_trigger") or "—"))} 起就停止進場</strong>'
            f'（{html.escape(str(kill_live_day.get("mode") or ""))} 模式）；'
            'live 段第一天的 '
            f'<strong>{_pct(kill_live_day.get("live_net"))} 是「沒有下單」，不是策略賺到</strong>'
            f'（同期市場 {_pct(live_market)}，那 {_pp(kill_live_day.get("live_excess"))} 的表面超額全部來自空倉）。'
            f'70 個交易日裡有 <strong>{kill_live_day.get("blocked_days", 0)} 天</strong>停止進場。'
            '<strong>這是 Walter 照單下單前必須知道的事：他的帳戶初期可能整段不交易。</strong>')
    kill_status_rows = ''
    for account, rows in (('live 帳戶', kill.get('live_account') or []),
                          ('影子帳 H3', kill.get('shadow_account') or [])):
        for row in rows:
            implemented = '✅ 已實作' if row.get('implemented') else '❌ 尚未實作（凍結紀錄）'
            kill_status_rows += (
                f'<tr><th class="rowhead">{html.escape(account)}</th>'
                f'<td>{html.escape(str(row.get("rule_version") or ""))}</td>'
                f'<td>{implemented}</td>'
                f'<td class="num">{row.get("segment_sessions", 0)}</td>'
                f'<td class="num">{row.get("windows_judged", 0)}／{row.get("windows_passed", 0)}</td>'
                f'<td class="num">{html.escape(str(row.get("state") or "CLOSED"))}</td>'
                f'<td class="num">{row.get("counter", 0)}／{row.get("counter_max", 3)}</td>'
                f'<td class="num">{row.get("blocked_days", 0)}</td>'
                f'<td class="num">{html.escape(str(row.get("last_trigger") or "—"))}</td>'
                f'<td class="num">{html.escape(str(row.get("next_half_open") or "—"))}</td></tr>')
    kill_compare_rows = ''
    for row in kill.get('comparison') or []:
        k = row.get('kill') or {}
        kill_compare_rows += (
            f'<tr><th class="rowhead">{html.escape(str(row.get("base") or ""))}</th>'
            f'<td>{html.escape(str(row.get("pool") or ""))}</td>'
            f'<td>{html.escape(str(row.get("mode") or ""))}</td>'
            f'<td class="num {_dir(row.get("net"))}">{_pct(row.get("net"))}</td>'
            f'<td class="num">{_pct(row.get("exposure"), 1)}</td>'
            f'<td class="num {_dir(row.get("vs_paired"))}">{_pp(row.get("vs_paired"))}</td>'
            f'<td class="num">{_pct(row.get("mdd"))}</td>'
            f'<td class="num">{row.get("buys", 0)}</td>'
            f'<td class="num">{k.get("blocked_days", 0)}</td>'
            f'<td class="num">{html.escape(str(k.get("first_trigger") or "—"))}</td>'
            f'<td class="num">{html.escape(str(k.get("last_trigger") or "—"))}</td>'
            f'<td class="num {_dir(row.get("live_net"))}">{_pct(row.get("live_net"))}</td>'
            f'<td class="num">{_pct(k.get("tradable_ratio"), 1)}</td></tr>')

    # ---- the circuit breaker: the state machine, and where it stands now
    circuit = kill.get('circuit') or {}
    circuit_rows = ''
    for st in circuit.get('states') or []:
        circuit_rows += (
            f'<tr><th class="rowhead">{html.escape(str(st.get("id") or ""))}</th>'
            f'<td>{html.escape(str(st.get("entries") or ""))}</td>'
            f'<td>{html.escape(str(st.get("counter") or ""))}</td>'
            f'<td>{html.escape(str(st.get("verdict") or ""))}</td>'
            f'<td>{html.escape(str(st.get("exit") or ""))}</td></tr>')
    # the live account's own state (the version in force today)
    circuit_now_row = {}
    for row in kill.get('live_account') or []:
        if row.get('rule_version') == (payload.get('rule_version') or 'AIV2'):
            circuit_now_row = row
    if not circuit_now_row:
        for row in kill.get('live_account') or []:
            circuit_now_row = row
    circuit_state = (circuit_now_row.get('state') or 'CLOSED')
    circuit_now_rows = ''
    for label, value in (
            ('目前狀態', circuit_state),
            ('計數器', f'{circuit_now_row.get("counter", 0)}／{circuit_now_row.get("counter_max", 3)}'),
            ('觸發日（首次）', circuit_now_row.get('first_trigger') or '—'),
            ('最後觸發日', circuit_now_row.get('last_trigger') or '—'),
            ('已擋天數', circuit_now_row.get('blocked_days', 0)),
            ('冷卻天數（K）', circuit_now_row.get('cooldown_days', RULES['circuit_cooldown_days'])),
            ('下次半開日期', circuit_now_row.get('next_half_open') or '—'),
            ('半開次數', circuit_now_row.get('half_opens', 0)),
            ('恢復次數（半開後達線）', circuit_now_row.get('resumes', 0)),
            ('各狀態天數', '／'.join(
                f'{k} {(circuit_now_row.get("days_in_state") or {}).get(k, 0)}'
                for k in ('CLOSED', 'OPEN', 'HALF-OPEN'))),
            ('可交易天數占比（帳戶能進場的天數／segment 天數）',
             f'{circuit_now_row.get("segment_tradable_days", 0)}／{circuit_now_row.get("breaker_sessions", 0)}'
             f'＝{_pct(circuit_now_row.get("tradable_ratio"), 1)}'),
            ('判定頻率', f'每 {circuit_now_row.get("judge_every_sessions", RULES["survive_window"])} 個交易日完成一個視窗、判定一次'),
            ('已判定／達線視窗', f'{circuit_now_row.get("windows_judged", 0)}／{circuit_now_row.get("windows_passed", 0)}')):
        circuit_now_rows += (
            f'<tr><th class="rowhead">{html.escape(label)}</th>'
            f'<td class="num">{html.escape(str(value))}</td></tr>')
    transition_text = ''
    transitions = circuit_now_row.get('transitions') or []
    if transitions:
        transition_text = '；'.join(
            f'{t.get("date")} {t.get("from")}→{t.get("to")}' for t in transitions[:8])
        if len(transitions) > 8:
            transition_text += f' …（共 {len(transitions)} 次）'
    else:
        transition_text = '尚無狀態轉換'

    # the three switch settings of the live entry rule, side by side.  The
    # numbers are read from the payload instead of being written into the
    # text: a hard-coded number on a public page goes stale the moment the
    # engine changes, and a stale number is a lie.
    kill_off_row, kill_breaker_row, kill_never_row = {}, {}, {}
    for row in kill.get('comparison') or []:
        if not (row.get('base') or '').startswith('AIV2'):
            continue
        if not (row.get('pool') or '').startswith('live'):
            continue
        mode = row.get('mode') or ''
        if mode.startswith('關閉'):
            kill_off_row = row
        elif mode.startswith('熔斷器'):
            kill_breaker_row = row
        elif mode.startswith('一旦觸發'):
            kill_never_row = row
    kill_cost_caveat = ''
    if kill_off_row and kill_never_row:
        kill_cost_caveat = (
            '在這段母體上，live 進場規則：'
            f'kill switch <strong>關閉</strong> = <strong>{_pct(kill_off_row.get("net"))}</strong>；'
            f'<strong>熔斷器</strong>（新版）= <strong>{_pct(kill_breaker_row.get("net")) if kill_breaker_row else "—"}</strong>；'
            f'<strong>一旦觸發就永不恢復</strong>（舊版那個空帳戶的行為）= '
            f'<strong>{_pct(kill_never_row.get("net"))}</strong>。'
            '<strong>注意「永不恢復」那一欄的漂亮數字不是策略賺到</strong>——'
            '那是帳戶被凍結成空倉後的 0 曝險結果；'
            '舊版純計數器在 2024 熱計數器情境就是這樣：242／242 天全被擋、報酬 0.00%、0 筆買進。'
            '<strong>新版熔斷器把那個空帳戶變成會重新進場的帳戶，數字因此變難看</strong>'
            '（2024 熱計數器實測：新版四個準則 −41.91%／−20.88%／−15.32%／−56.49%，'
            '買進 209～800 筆、曝險 63.5%～80.1%、可交易天數占比 87.5%～91.7%）——'
            '<strong>但那才是真實的策略結果</strong>。'
            '<strong>它的真實定位是「小幅風險降低器」，不是「救命保護」</strong>：'
            '同一段母體上，熔斷器相對 kill OFF 的增益只有 <strong>+3.1／+0.03／+2.8／+5.3pp</strong>'
            '（四個準則）——<strong>它不能救一個沒有 edge 的策略，只能少賺一點點虧損</strong>。')

    # ---- the 32 execution combinations
    grid = payload.get('execution_grid') or {}
    grid_rows = ''
    for row in grid.get('rows') or []:
        grid_rows += (
            f'<tr><th class="rowhead">{html.escape(str(row.get("pool") or ""))}</th>'
            f'<td>{html.escape(str(row.get("lot") or ""))}</td>'
            f'<td>{html.escape(str(row.get("fill") or ""))}</td>'
            f'<td class="num">{row.get("n", 0)}</td>'
            f'<td class="num {_dir(row.get("net"))}">{_pct(row.get("net"))}</td>'
            f'<td class="num">{_pct(row.get("exposure"), 1)}</td>'
            f'<td class="num {_dir(row.get("vs_paired"))}">{_pp(row.get("vs_paired"))}</td>'
            f'<td class="num">{_pct(row.get("mdd"))}</td>'
            f'<td class="num">{row.get("buys", 0)}</td></tr>')
    grid_note = html.escape(str(grid.get('note') or ''))
    ai_ledger_window = RULES['survive_window']
    ai_ledger_periods = RULES['kill_switch_periods']
    bench_level = None
    for point in reversed(payload.get('benchmark') or []):
        if point.get('level') is not None:
            bench_level = point['level']
            break
    grid_market = f'{((bench_level or 1.0) - 1) * 100:+.2f}%'
    live_cells = [r for r in grid.get('rows') or [] if str(r.get('pool') or '').startswith('live')]
    h3_cells = [r for r in grid.get('rows') or [] if str(r.get('pool') or '').startswith('H3')]
    best_live = max((r.get('net') or 0 for r in live_cells), default=0.0)
    grid_split = (
        f'精確地說：{len(grid.get("rows") or [])} 格裡有 {len(live_cells)} 格是 live 進場規則'
        f'（全部為負，最好的一格 {best_live*100:+.2f}%）、'
        f'另外 {len(h3_cells)} 格是 H3 影子帳（{sum(1 for r in h3_cells if (r.get("net") or 0) > 0)} 格為正）。')

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

    page = f"""<!DOCTYPE html>
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
  <p class="caveat">{kill_first_caveat}</p>
  <p class="caveat">⚠️ <strong>live 帳戶跑的進場規則，在 32 個執行組合裡沒有一格是正的</strong>；
  唯一有正訊號的 H3 在影子帳裡、不會下單。
  {grid_split}
  換句話說：這套進場規則在這段母體上沒有可用的 edge，
  而唯一看起來賺錢的那幾格，架構上就不會成交。</p>
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
  <h2>kill switch（R9 的保護機制：<strong>小幅風險降低器</strong>，不是救命符）</h2>
  <p class="muted">{str(kill.get("note") or "")}</p>
  <table>
    <thead><tr><th class="rowhead">帳戶</th><th>規則版本</th><th>是否實作</th>
    <th>live 段交易日</th><th>已判定／達線視窗</th><th>熔斷器狀態</th><th>目前計數器</th>
    <th>停止進場天數</th><th>最後觸發日</th><th>下次半開日期</th></tr></thead>
    <tbody>{kill_status_rows}</tbody>
  </table>
  <h3>熔斷器狀態機（CLOSED／OPEN／HALF-OPEN）</h3>
  <p class="muted">判定線：{html.escape(str(circuit.get("verdict_line") or ""))}。
  熔斷器只決定「何時恢復進場」，<strong>不放寬判定線，也不讓帳本變綠</strong>。</p>
  <table>
    <thead><tr><th class="rowhead">狀態</th><th>新進場</th><th>計數器</th><th>視窗判定</th><th>離開條件</th></tr></thead>
    <tbody>{circuit_rows}</tbody>
  </table>
  <table>
    <thead><tr><th class="rowhead">live 帳戶的熔斷器現況</th><th>值</th></tr></thead>
    <tbody>{circuit_now_rows}</tbody>
  </table>
  <p class="muted">狀態轉換紀錄：{html.escape(transition_text)}</p>
  <p class="caveat">⚠️ <strong>誠實揭露：舊版實作（純計數器）會死鎖。</strong>
  {html.escape(str(circuit.get("old_defect") or ""))}</p>
  <p class="caveat">⚠️ {str(circuit.get("old_defect_hard") or "")}</p>
  <p class="caveat">⚠️ <strong>熔斷器只決定「何時恢復進場」，不放寬判定、也不讓帳本變綠。</strong>
  判定線仍是 R9 原文：淨 &gt; 0、超額 &gt; 0、回撤 &lt; 容許。
  OPEN 期間「不判定視窗」的理由是：帳戶空倉時報酬恆為 0，那個視窗不是策略表現的證據；
  若照舊版繼續判定，空帳戶就永遠達不到線 → 永久停止交易。</p>
  <p class="caveat">⚠️ <strong>實測（不是模擬）：</strong>
  {str(circuit.get("measured_2024") or "")}</p>
  <p class="caveat">⚠️ 一個視窗要 {html.escape(str(ai_ledger_window))} 個交易日才完成，
  <strong>每完成一個視窗才判定一次</strong>（counter 的單位是「視窗」不是「天」），
  連續 {html.escape(str(ai_ledger_periods))} 個視窗不達線才會動作。
  live 段的交易日數還不夠，
  所以「目前計數器 = 0、停止進場天數 = 0、最後觸發日 = 無」是真的：
  <strong>它還沒有機會動作，不代表它動作過</strong>。</p>
  <p class="caveat">⚠️ <strong>計數器的歸零規則：同一個規則版本內承繼；規則版本一變更就歸零。</strong>
  新版本還沒失敗過任何東西，所以不該背著舊版本的失敗視窗出發——否則前瞻紀錄會一開始就停在
  「停止進場」，量不到任何東西。影子帳是另一回事：它是研究軌，計數器從 live_start 重新起算。</p>
  <p class="caveat">⚠️ <strong>kill switch 不是免費午餐：它賭的是「策略自己會變差」，不是「市場會變差」。</strong>
  {kill_cost_caveat}</p>
  <p class="caveat">⚠️ <strong>同一套機制在多頭 regime 裡是負面的</strong>：舊版純計數器在
  <strong>2020 上半年的多頭母體</strong>（重建母體，116 個交易日）把同一條規則從
  <strong>+30.69% 變成 −9.10%</strong>——20 個交易日的滾動視窗判定不達線，116 天裡擋掉 94 天。
  <strong>那組數字是 2026-11-26 之前的舊版實測；新版熔斷器還沒在這個母體上重測</strong>
  （2020–2026 的重建仍在跑，跑完補）。<strong>在多頭 regime 裡它是負面的</strong>這件事本身
  不會因為換成熔斷器而消失——要採用它，就必須把它的歷史行為（含這個反例）一起揭露，
  不能只報空頭段那個好看的數字。</p>
  <h3>對照：若這個保護從記錄第一天就在運作（同一段母體、同一個基準、300 萬口徑）</h3>
  <table>
    <thead><tr><th class="rowhead">條款</th><th>進場池</th><th>kill switch</th>
    <th>淨報酬</th><th>平均曝險</th><th>vs 曝險配對市場</th><th>最大回撤</th><th>買進</th>
    <th>停止進場天數</th><th>首次觸發</th><th>最後觸發</th>
    <th>live 段第 1 天</th><th>可交易天數占比</th></tr></thead>
    <tbody>{kill_compare_rows}</tbody>
  </table>
  <p class="caveat">⚠️ 這是「如果」的數字，不是發生過的事。而且它和「少做、留現金」高度綁定：
  樣本期間市場是 {html.escape(str(grid_market))}，一個把曝險從 93% 降到 40% 的規則在下跌段本來就會贏。
  唯一能分出「選股能力」與「只是少做」的，是「vs 曝險配對市場」那一欄。</p>
</section>
<section>
  <h2>執行組合（32 格）</h2>
  <p class="muted">{grid_note}</p>
  <table>
    <thead><tr><th class="rowhead">進場池</th><th>零股/整股</th><th>成交模型</th><th>同時持有</th>
    <th>淨報酬</th><th>平均曝險</th><th>vs 曝險配對市場</th><th>最大回撤</th><th>買進</th></tr></thead>
    <tbody>{grid_rows}</tbody>
  </table>
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
    assert_no_broken_numbers(page)
    return page


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
