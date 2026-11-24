"""Track the danger list: what was flagged, and whether it earned its keep.

Two records, kept apart on purpose:

* **live** - every published session's flag set, written once and never
  rewritten (``public/data/danger-history/<date>.json``).  The rule version
  travels with the entry, so a later rule change cannot rewrite history.
* **backtest** - the current 130% rule applied to the maintenance history that
  exists in ``finmind_taiwan_margin_maintenance`` (72 sessions so far).  A
  backtest is not a track record, and the page labels it as such.

The metric is always the **excess against the equal-weight market**, never the
absolute return: the hard rule flags 27-47% of the market on any given day, so
"flagged names fell" proves nothing on its own.  The same population, the same
sessions, the same method as the 2026-11-20 gate evaluation.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import pipeline_state as ps

HORIZONS = (1, 3, 5, 10, 20)
HARD_RULE = 130.0
RULE_ID = 'D027-v1'
LEDGER_DIR = 'danger-history'
LEDGER_FILE = 'danger-track.json'


def rule_version() -> str:
    """Identify the rules as of today.

    The scoring code is hashed in, so any later edit to the scan changes the
    version of every entry written from then on.  Entries written earlier keep
    the version they were flagged under.
    """
    scan = ROOT / 'src' / 'margin_rebound' / 'scan.py'
    try:
        return f"{RULE_ID}+{ps.sha256(scan)[:8]}"
    except OSError:
        return RULE_ID


def write_ledger(date: str, payload: dict, public: Path) -> dict:
    """Record the flag set as published.  Existing entries are never rewritten."""
    directory = public / 'data' / LEDGER_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'{date}.json'
    if path.is_file():
        return json.loads(path.read_text(encoding='utf-8-sig'))
    rows = payload.get('rows') or []
    entry = {
        'date': date,
        'rule_version': rule_version(),
        'nightly_id': payload.get('nightly_id') or '',
        'generated_at': payload.get('generated_at'),
        'counts': {
            'candidates': len(rows),
            'danger': sum(1 for r in rows if r.get('severity') == 'danger'),
            'alert': sum(1 for r in rows if r.get('severity') == 'alert'),
        },
        'danger': sorted(r['ticker'] for r in rows if r.get('severity') == 'danger'),
        'alert': sorted(r['ticker'] for r in rows if r.get('severity') == 'alert'),
    }
    ps.atomic_json(path, entry)
    return entry


def _closes(cur, first_date: str) -> tuple[list[str], dict]:
    cur.execute("SELECT DISTINCT Date FROM daily_data2_full WHERE Date >= %s ORDER BY Date", (first_date,))
    sessions = [str(r['Date']) for r in cur.fetchall()]
    cur.execute("SELECT Ticker, Date, Close FROM daily_data2_full WHERE Date >= %s", (first_date,))
    closes = {}
    for row in cur.fetchall():
        closes[(str(row['Ticker']), str(row['Date']))] = float(row['Close'])
    return sessions, closes


def _basket_stats(flag_sets: dict[str, set[str]], sessions: list[str], closes: dict,
                   horizons=HORIZONS) -> dict:
    """Mean forward return of the flagged baskets against the equal-weight market."""
    index = {d: i for i, d in enumerate(sessions)}
    basket = {h: [] for h in horizons}
    market = {h: defaultdict(list) for h in horizons}
    for date, names in flag_sets.items():
        i = index.get(date)
        if i is None or not names:
            continue
        for h in horizons:
            j = i + h
            if j >= len(sessions):
                continue
            target = sessions[j]
            rets = [closes[(t, target)] / closes[(t, date)] - 1.0
                    for t in names
                    if (t, target) in closes and (t, date) in closes and closes[(t, date)]]
            if rets:
                basket[h].append((date, sum(rets) / len(rets)))
        day = [(t, c) for (t, d), c in closes.items() if d == date]
        if day:
            for h in horizons:
                j = i + h
                if j >= len(sessions):
                    continue
                target = sessions[j]
                rets = [closes[(t, target)] / c - 1.0 for t, c in day if (t, target) in closes and c]
                if rets:
                    market[h][date] = sum(rets) / len(rets)
    out = {}
    for h in horizons:
        rows = basket[h]
        paired = [(b, market[h][d]) for d, b in rows if d in market[h]]
        if not paired:
            continue
        basket_mean = sum(b for b, _ in paired) / len(paired)
        market_mean = sum(m for _, m in paired) / len(paired)
        out[str(h)] = {
            'sessions': len(paired),
            'basket': round(basket_mean, 6),
            'market': round(market_mean, 6),
            'excess': round(basket_mean - market_mean, 6),
            'beats_market': sum(1 for b, m in paired if b > m),
        }
    return out


def live_record(public: Path) -> dict:
    """The sessions published by this system, with their forward outcomes."""
    directory = public / 'data' / LEDGER_DIR
    if not directory.is_dir():
        return {'sessions': 0, 'windows': {}, 'first_date': '', 'last_date': '', 'rule_versions': []}
    entries = []
    for path in sorted(directory.glob('*.json')):
        try:
            entries.append(json.loads(path.read_text(encoding='utf-8-sig')))
        except (OSError, json.JSONDecodeError):
            continue
    if not entries:
        return {'sessions': 0, 'windows': {}, 'first_date': '', 'last_date': '', 'rule_versions': []}
    import db_client as db
    flag_sets = {e['date']: set(e.get('danger') or []) for e in entries}
    first = min(flag_sets)
    with db.get_cursor() as cur:
        sessions, closes = _closes(cur, first)
    windows = _basket_stats(flag_sets, sessions, closes)
    return {
        'sessions': len(entries),
        'first_date': first,
        'last_date': max(flag_sets),
        'rule_versions': sorted({e.get('rule_version') or '' for e in entries}),
        'windows': windows,
    }


def backtest_record() -> dict:
    """The current 130% rule applied to the maintenance history that exists.

    This is a backtest, not a track record: the rule was applied to history
    after the fact, and it only covers tier 1 (the hard rule) because that is
    what the maintenance table can reproduce on its own.
    """
    import db_client as db
    with db.get_cursor() as cur:
        cur.execute("SELECT DISTINCT trade_date FROM finmind_taiwan_margin_maintenance ORDER BY trade_date")
        dates = [str(r['trade_date']) for r in cur.fetchall()]
        if not dates:
            return {'sessions': 0, 'windows': {}, 'range': ''}
        cur.execute("SELECT trade_date, ticker FROM finmind_taiwan_margin_maintenance "
                    "WHERE margin_maintenance < %s", (HARD_RULE,))
        flag_sets: dict[str, set[str]] = defaultdict(set)
        for row in cur.fetchall():
            flag_sets[str(row['trade_date'])].add(str(row['ticker']))
        sessions, closes = _closes(cur, dates[0])
    windows = _basket_stats(flag_sets, sessions, closes)
    counts = sorted(len(v) for v in flag_sets.values())
    return {
        'sessions': len(dates),
        'range': f'{dates[0]}..{dates[-1]}',
        'windows': windows,
        'flagged_per_session': {
            'min': counts[0] if counts else 0,
            'median': counts[len(counts) // 2] if counts else 0,
            'max': counts[-1] if counts else 0,
        },
    }


def verdict(windows: dict) -> tuple[str, str]:
    """A plain sentence about whether the screen earned its keep."""
    if not windows:
        return 'unknown', '還沒有足夠的評估資料'
    long_window = windows.get('20') or windows.get('10')
    if not long_window:
        return 'unknown', '還沒有足夠的評估資料'
    excess = long_window['excess']
    beats = long_window['beats_market'] / max(long_window['sessions'], 1)
    if excess > 0 and beats > 0.5:
        return 'has_edge', (f'旗標籃子比市場多 {excess*100:.2f}pp，'
                             f'並在 {long_window["beats_market"]}/{long_window["sessions"]} 個交易日贏過市場')
    if excess > 0:
        return 'weak_edge', (f'旗標籃子比市場多 {excess*100:.2f}pp，'
                             f'但只有 {long_window["beats_market"]}/{long_window["sessions"]} 個交易日贏過市場')
    return 'no_edge', (f'旗標籃子比市場少 {abs(excess)*100:.2f}pp，'
                       '這張篩選目前沒有鑑別力')


def evaluate(public: Path) -> dict:
    live = live_record(public)
    backtest = backtest_record()
    # The live record only counts once it has enough sessions to mean anything;
    # until then the verdict comes from the backtest and says so.
    live_usable = live.get('sessions', 0) >= 20 and bool(live.get('windows'))
    source = live['windows'] if live_usable else backtest['windows']
    kind, note = verdict(source)
    track = {
        'updated_at': ps.datetime.now().isoformat(),
        'method': {
            'benchmark': '同一批交易日的等權全市場',
            'horizons': list(HORIZONS),
            'metric': '超額（旗標籃子 − 市場），不是絕對報酬',
            'why': '硬規則每天會標到 27-47% 的全市場，「被標的跌了」本身不構成訊息',
        },
        'live': live,
        'backtest': backtest,
        'verdict': kind,
        'verdict_note': note,
        'verdict_source': 'live' if live_usable else 'backtest',
        'caveat': ('這是「相對風險篩選」不是「獲利訊號」：回溯 1~10 日的旗標籃子仍然是負的'
                   '（賣掉比不賣少賠，但不是賺）。'),
    }
    ps.atomic_json(public / 'data' / LEDGER_FILE, track)
    return track
