"""The danger list: the stocks whose evidence says sell now.

One definition, two views.  The margin-distress score is not recomputed here -
the rows come from the margin-rebound scan, so there is exactly one definition
of a distressed stock (the same one the certified chain already uses for the
130% hard rule).  This module adds the model's own view (20-day big-loss
probability, expected net return, the AI's action and its reason flags) and
renders the page.  The AI ledger will read the same rows, so the two views
cannot disagree.

Colour convention, unchanged from the rest of the site: red is 多/漲/正, green is
空/跌/負.  A cell that states a direction uses that convention; a cell that
states a risk level (the maintenance rate) stays in plain ink and the severity
is carried by the badge and the legend, so one colour never means two things.
"""
from __future__ import annotations

import html
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import pipeline_state as ps

CONFIG = ROOT / 'scripts' / 'daily_chain_audit_config.json'

REASON_FLAGS = (
    ('forced_buying', 'minerva_reason_forced_buying'),
    ('float_squeeze', 'minerva_reason_float_squeeze'),
    ('no_rise_control', 'minerva_reason_no_rise_control'),
    ('fomo_exhaustion', 'minerva_reason_fomo_exhaustion'),
    ('liquidity_impact', 'minerva_reason_liquidity_impact'),
    ('narrative_spread', 'minerva_reason_narrative_spread'),
    ('info_reprice', 'minerva_reason_info_reprice'),
)

MODEL_COLUMNS = (
    'ticker', 'close_price', 'change_pct', 'ai_action', 'p_big_loss20',
    'p_win20_net_1pct', 'pred_net_return', 'rank_liquid', 'leverage_risk_score',
    'short_pressure_score', 'chip_foreign_sell_streak', 'chip_institution_sell_streak',
)


def ai_root() -> Path:
    try:
        return Path(json.loads(CONFIG.read_text(encoding='utf-8-sig'))['ai_root'])
    except Exception:
        return Path(r'D:\CODEX\AI-Telegram')


def report_date() -> str:
    import report_inputs
    return report_inputs.report_date()


def margin_rows(date: str) -> list[dict]:
    """The margin-rebound scan output: one definition of a distressed stock."""
    path = ps.RUNTIME / 'outputs' / 'margin_rebound' / f'{date}.json'
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding='utf-8-sig'))
    return [row for row in (payload.get('candidates') or []) if isinstance(row, dict)]


def model_rows(date: str) -> dict[str, dict]:
    """The model's own view for the same session, keyed by ticker."""
    path = ai_root() / 'output' / 'daily_prediction_refresh' / f'predictions_{date}.csv'
    if not path.is_file():
        return {}
    import pandas as pd
    frame = pd.read_csv(path, low_memory=False)
    wanted = list(MODEL_COLUMNS) + [column for _, column in REASON_FLAGS]
    for column in wanted:
        if column not in frame.columns:
            frame[column] = None
    out: dict[str, dict] = {}
    for row in frame.to_dict('records'):
        ticker = str(row.get('ticker') or '').strip()
        if not ticker:
            continue
        reasons = [name for name, column in REASON_FLAGS if row.get(column)]
        out[ticker] = {
            'close': row.get('close_price'),
            'change_pct': row.get('change_pct'),
            'ai_action': row.get('ai_action'),
            'p_big_loss20': row.get('p_big_loss20'),
            'p_win20_net_1pct': row.get('p_win20_net_1pct'),
            'pred_net_return': row.get('pred_net_return'),
            'rank_liquid': row.get('rank_liquid'),
            'leverage_risk_score': row.get('leverage_risk_score'),
            'short_pressure_score': row.get('short_pressure_score'),
            'foreign_sell_streak': row.get('chip_foreign_sell_streak'),
            'institution_sell_streak': row.get('chip_institution_sell_streak'),
            'reasons': reasons,
        }
    return out


def number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value


def severity_of(row: dict) -> str:
    """tier 1 is the 130% hard rule; tier 2 is the early-warning band."""
    tier = row.get('tier')
    if tier in (1, '1'):
        return 'danger'
    if tier in (2, '2'):
        return 'alert'
    maint = number(row.get('maint_rate'))
    if maint is not None and maint < 130:
        return 'danger'
    return 'alert'


def build(date: str) -> dict:
    candidates = margin_rows(date)
    model = model_rows(date)
    rows = []
    for candidate in candidates:
        ticker = str(candidate.get('ticker') or '').strip()
        if not ticker:
            continue
        view = model.get(ticker, {})
        scores = candidate.get('scores') or {}
        rows.append({
            'ticker': ticker,
            'company': candidate.get('company') or '',
            'industry': candidate.get('industry') or '',
            'close': number(candidate.get('close')),
            'change_pct': view.get('change_pct'),
            'maint_rate': number(candidate.get('maint_rate')),
            'maint_source': candidate.get('maint_source') or '',
            'margin_chg_1d_pct': number(candidate.get('margin_chg_1d_pct')),
            'margin_chg_3d_pct': number(candidate.get('margin_chg_3d_pct')),
            'composite': number(candidate.get('composite')),
            'scores': {k: number(v) for k, v in scores.items()},
            'rsi': number(candidate.get('rsi')),
            'bias_pct': number(candidate.get('bias_pct')),
            'vol_ratio': number(candidate.get('vol_ratio')),
            'lower_shadow': number(candidate.get('lower_shadow')),
            'avg_cost_120d': number(candidate.get('avg_cost_120d')),
            'days_on_list': candidate.get('days_on_list'),
            'first_seen': candidate.get('first_seen') or '',
            'ai_comment': candidate.get('ai_comment') or '',
            'ai_action': view.get('ai_action') or '',
            'p_big_loss20': view.get('p_big_loss20'),
            'p_win20_net_1pct': view.get('p_win20_net_1pct'),
            'pred_net_return': view.get('pred_net_return'),
            'leverage_risk_score': view.get('leverage_risk_score'),
            'short_pressure_score': view.get('short_pressure_score'),
            'foreign_sell_streak': view.get('foreign_sell_streak'),
            'institution_sell_streak': view.get('institution_sell_streak'),
            'reasons': view.get('reasons') or [],
            'severity': severity_of(candidate),
            'tier': candidate.get('tier'),
        })
    order = {'danger': 0, 'alert': 1}
    rows.sort(key=lambda r: (order.get(r['severity'], 2),
                             -(r['composite'] or 0),
                             r['ticker']))
    for index, row in enumerate(rows, start=1):
        row['rank'] = index
    summary = {
        'candidates': len(candidates),
        'danger': sum(1 for r in rows if r['severity'] == 'danger'),
        'alert': sum(1 for r in rows if r['severity'] == 'alert'),
        'model_rows': len(model),
        'covered': sum(1 for r in rows if r['ai_action']),
    }
    return {
        'date': date,
        'nightly_id': (os.environ.get('TW_NIGHTLY_ID')
                       or (ps.read_json(ps.STATE).get('nightly_id') if ps.STATE.is_file() else '') or ''),
        'generated_at': ps.datetime.now().isoformat(),
        'rules': {
            'hard_rule': '融資維持率 < 130%（斷頭風險）→ 危險',
            'alert_rule': '130-150% 且融資連 3 日下降 → 警戒',
            'ranking': '先危險後警戒，同組依 7 維風險分數由高到低',
            'legend': '紅＝多／漲／正，綠＝空／跌／負（與全站一致）；風險等級由 ⚠️／⚡ 標記承載，不靠顏色猜',
        },
        'summary': summary,
        'rows': rows,
    }


def _num(value, digits=2, dash='—'):
    if value is None:
        return dash
    return f'{value:,.{digits}f}'


def _pct(value, digits=2, dash='—'):
    if value is None:
        return dash
    return f'{value * 100:.{digits}f}%'


def _dir_class(value):
    """Red is 多/漲/正, green is 空/跌/負 - the site's existing convention."""
    if value is None:
        return ''
    if value > 0:
        return 'up'
    if value < 0:
        return 'down'
    return ''


def _cell(value, digits=2, suffix='', kind='dir'):
    if value is None:
        return '<td class="num muted">—</td>'
    css = _dir_class(value) if kind == 'dir' else ''
    text = f'{value:,.{digits}f}{suffix}'
    return f'<td class="num {css}">{text}</td>'


def _windows_table(title: str, note: str, windows: dict) -> str:
    if not windows:
        return f'<div class="track-block"><h3>{html.escape(title)}</h3><p class="muted">{html.escape(note)}：尚無資料</p></div>'
    head = ''.join(f'<th>{h} 日</th>' for h in ('1', '3', '5', '10', '20') if h in windows)
    cells = []
    for label, key, fmt in (('旗標籃子', 'basket', 'pct'), ('等權市場', 'market', 'pct'),
                            ('超額', 'excess', 'pp'), ('贏過市場', 'beats_market', 'count')):
        values = []
        for h in ('1', '3', '5', '10', '20'):
            if h not in windows:
                continue
            row = windows[h]
            if fmt == 'pct':
                values.append(f'<td class="num {"up" if row[key] > 0 else "down" if row[key] < 0 else ""}">{row[key]*100:.2f}%</td>')
            elif fmt == 'pp':
                values.append(f'<td class="num {"up" if row[key] > 0 else "down" if row[key] < 0 else ""}">{row[key]*100:+.2f}pp</td>')
            else:
                values.append(f'<td class="num">{row["beats_market"]}/{row["sessions"]}</td>')
        cells.append(f'<tr><th class="rowhead">{label}</th>{"".join(values)}</tr>')
    return (f'<div class="track-block"><h3>{html.escape(title)}</h3>'
            f'<p class="muted">{html.escape(note)}</p>'
            f'<table class="track-table"><tr><th class="rowhead"></th>{head}</tr>{"".join(cells)}</table></div>')


def _track_section(track: dict) -> str:
    if not track:
        return ''
    live = track.get('live') or {}
    backtest = track.get('backtest') or {}
    verdict = track.get('verdict') or 'unknown'
    mark = {'has_edge': '✅', 'weak_edge': '⚠️', 'no_edge': '❌', 'unknown': '⚪'}.get(verdict, '⚪')
    live_note = (f'已發佈 {live.get("sessions", 0)} 個交易日（{live.get("first_date", "")} → {live.get("last_date", "")}）'
                 f'　規則版本 {", ".join(live.get("rule_versions") or []) or "—"}')
    backtest_note = (f'把現行 130% 硬規則套回 {backtest.get("sessions", 0)} 個有維持率歷史的交易日'
                     f'（{backtest.get("range", "")}）——這是回溯量測，不是 live 記錄')
    return f"""
<section class="track">
  <h2>📊 這張表的成績</h2>
  <p class="muted">方法：超額＝旗標籃子 − 同批交易日的等權全市場。硬規則每天會標到 27-47% 的全市場，
  「被標的跌了」本身不構成訊息，所以只看超額與贏過市場的天數。</p>
  <p class="verdict {verdict}">{mark} <b>{html.escape(track.get('verdict_note') or '')}</b></p>
  <p class="caveat">⚠️ {html.escape(track.get('caveat') or '')}</p>
  {_windows_table('回溯量測', backtest_note, backtest.get('windows') or {})}
  {_windows_table('live 記錄', live_note, live.get('windows') or {})}
</section>
"""


def render_html(payload: dict) -> str:
    date = payload['date']
    summary = payload['summary']
    rules = payload['rules']
    rows = payload['rows']
    body = []
    for row in rows:
        danger = row['severity'] == 'danger'
        badge = ('<span class="sev danger">⚠️ 危險</span>' if danger
                 else '<span class="sev alert">⚡ 警戒</span>')
        reasons = '、'.join(row['reasons']) or '—'
        action = row['ai_action'] or '—'
        action_class = {'ADD': 'up', 'REDUCE': 'down'}.get(action, '')
        action_cell = f'<td class="act {action_class}">{html.escape(action)}</td>' if action else '<td class="act muted">—</td>'
        comment = html.escape(str(row['ai_comment'] or ''))
        body.append(
            '<tr data-severity="{sev}" data-composite="{comp}" data-maint="{maint}" '
            'data-bigloss="{bigloss}" data-days="{days}" data-rank="{rank}">'
            f'<td class="rank">{row["rank"]}</td>'
            f'<td>{badge}</td>'
            f'<td class="ticker"><a href="analyze.html?t={row["ticker"]}">{row["ticker"]}</a>'
            f'<span class="co">{html.escape(str(row["company"] or ""))}</span></td>'
            f'<td class="ind">{html.escape(str(row["industry"] or ""))}</td>'
            f'{_cell(row["close"])}'
            f'{_cell(row["change_pct"], suffix="%")}'
            f'<td class="num strong">{_num(row["maint_rate"], 1)}%</td>'
            f'{_cell(row["margin_chg_1d_pct"], suffix="%")}'
            f'{_cell(row["margin_chg_3d_pct"], suffix="%")}'
            f'<td class="num strong">{_num(row["composite"], 1)}</td>'
            f'<td class="num">{_num(row["days_on_list"], 0)}</td>'
            f'{_cell(row["p_big_loss20"], digits=2)}'
            f'{_cell(row["pred_net_return"], digits=2, suffix="%")}'
            f'{action_cell}'
            f'<td class="reason">{reasons}</td>'
            f'<td class="comment" title="{comment}">{html.escape(comment)[:40]}</td>'
            '</tr>')

    legend = (
        '<div class="legend">'
        '<span><span class="sev danger">⚠️ 危險</span> 融資維持率 &lt; 130%（斷頭風險）</span>'
        '<span><span class="sev alert">⚡ 警戒</span> 130-150% 且融資連 3 日下降</span>'
        '<span class="up">紅＝多／漲／正</span><span class="down">綠＝空／跌／負</span>'
        '<span class="muted">維持率、風險分數以數字呈現，等級看 ⚠️／⚡</span>'
        '</div>'
    )
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>⚠️ 危險名單 — {date}</title>
<style>
:root {{ --bg:#0a0e1a; --panel:#131b2e; --panel2:#1a2440; --ink:#e6ecf5; --muted:#8aa0c0;
  --acc:#5fb1ff; --cyan:#39c5cf; --border:#1f2942; --red:#ec7063; --red-soft:#5a2a25;
  --green:#58d68d; --green-soft:#1f3a2a; --amber:#f5b041; --danger:#b3423a; }}
* {{ box-sizing: border-box; }}
body {{ margin:0; padding:0; background:var(--bg); color:var(--ink);
  font-family:-apple-system,"Microsoft JhengHei","Noto Sans TC",system-ui,sans-serif; line-height:1.5; }}
a {{ color:inherit; text-decoration:none; }}
.module-tabs {{ max-width:1500px; margin:0 auto; padding:24px 24px 0; display:flex; flex-wrap:wrap; gap:6px; }}
.mod-tab {{ padding:7px 14px; border:1px solid var(--border); border-radius:8px; color:var(--muted); font-size:.85rem; }}
.mod-tab:hover {{ background:var(--panel); color:var(--ink); }}
.mod-tab.active {{ background:var(--danger); color:#fff; border-color:var(--danger); font-weight:600; }}
.hdr {{ max-width:1500px; margin:0 auto; padding:20px 24px 10px; }}
.hdr h1 {{ margin:0 0 6px; font-size:1.6rem; }}
.hdr .sub {{ color:var(--muted); font-size:.92rem; margin:0 0 10px; }}
.hdr .meta {{ display:flex; flex-wrap:wrap; gap:8px; font-size:.82rem; }}
.hdr .pill {{ background:var(--panel); border:1px solid var(--border); border-radius:14px; padding:4px 12px; color:var(--muted); }}
.hdr .pill b {{ color:var(--ink); }}
main {{ max-width:1500px; margin:0 auto; padding:10px 24px 60px; }}
.legend {{ display:flex; flex-wrap:wrap; gap:16px; font-size:.8rem; color:var(--muted); margin-bottom:12px; }}
.sev {{ display:inline-block; padding:1px 8px; border-radius:6px; font-size:.72rem; font-weight:600; white-space:nowrap; }}
.sev.danger {{ background:var(--danger); color:#fff; }}
.sev.alert {{ background:rgba(245,176,65,.18); color:var(--amber); }}
.controls {{ display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-bottom:10px; font-size:.82rem; }}
.controls button {{ background:var(--panel); color:var(--muted); border:1px solid var(--border);
  padding:6px 12px; border-radius:8px; cursor:pointer; font-size:.82rem; font-family:inherit; }}
.controls button.active {{ background:var(--acc); color:#000; border-color:var(--acc); font-weight:600; }}
.controls select {{ background:var(--panel); color:var(--ink); border:1px solid var(--border);
  border-radius:8px; padding:6px 10px; font-size:.82rem; font-family:inherit; }}
table {{ width:100%; border-collapse:collapse; font-size:.83rem; }}
th {{ position:sticky; top:0; background:var(--panel2); color:var(--muted); text-align:left;
  padding:8px 10px; border-bottom:1px solid var(--border); font-weight:600; white-space:nowrap; }}
td {{ padding:7px 10px; border-bottom:1px solid rgba(31,41,66,.6); vertical-align:top; }}
tr:hover td {{ background:rgba(95,177,255,.06); }}
td.num {{ text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }}
td.strong {{ font-weight:600; }}
td.rank {{ color:var(--muted); text-align:right; width:2.4rem; }}
td.ticker {{ white-space:nowrap; }}
td.ticker a {{ color:var(--acc); font-weight:600; }}
td.ticker .co {{ display:block; color:var(--muted); font-size:.74rem; max-width:9rem;
  overflow:hidden; text-overflow:ellipsis; }}
td.ind {{ color:var(--muted); max-width:7rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
td.act {{ font-weight:600; }}
td.reason {{ color:var(--muted); max-width:11rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
td.comment {{ color:var(--muted); max-width:16rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.up {{ color:var(--red); }}
.down {{ color:var(--green); }}
.muted {{ color:var(--muted); }}
.empty {{ color:var(--muted); padding:26px; text-align:center; }}
.track {{ background:var(--panel); border:1px solid var(--border); border-radius:12px;
  padding:14px 16px; margin:0 0 16px; }}
.track h2 {{ margin:0 0 6px; font-size:1.02rem; }}
.track p {{ margin:0 0 8px; font-size:.82rem; }}
.track-block {{ margin-top:12px; }}
.track-block h3 {{ margin:0 0 2px; font-size:.88rem; color:var(--ink); }}
.track-block p {{ margin:0 0 4px; font-size:.78rem; }}
.track-table {{ width:auto; margin-top:4px; font-size:.8rem; }}
.track-table th, .track-table td {{ padding:4px 10px; border-bottom:1px solid rgba(31,41,66,.5); }}
.track-table th.rowhead {{ color:var(--muted); font-weight:500; text-align:left; }}
.track-table thead th, .track-table tr:first-child th {{ background:transparent; position:static; }}
.verdict {{ font-size:.9rem; }}
.verdict.has_edge {{ color:var(--green); }}
.verdict.weak_edge {{ color:var(--amber); }}
.verdict.no_edge {{ color:var(--red); }}
.verdict.unknown {{ color:var(--muted); }}
.caveat {{ color:var(--amber); }}
</style>
</head>
<body>
<nav class="module-tabs">
  <a class="mod-tab" href="readme.html">🏠 首頁</a>
  <a class="mod-tab active" href="danger.html">⚠️ 危險名單</a>
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
  <h1>⚠️ 危險名單</h1>
  <p class="sub">融資維持率斷頭風險 × 7 維風險分數 × 20 日模型 — 排序後最該處理的在前</p>
  <div class="meta">
    <div class="pill">📅 資料日 <b>{date}</b></div>
    <div class="pill">⚠️ 危險 <b>{summary['danger']}</b></div>
    <div class="pill">⚡ 警戒 <b>{summary['alert']}</b></div>
    <div class="pill">📋 掃描候選 <b>{summary['candidates']}</b></div>
    <div class="pill">🧠 模型有訊號 <b>{summary['covered']}</b></div>
  </div>
</div>
<main>
  {legend}
  {_track_section(payload.get('track') or {})}
  <div class="controls">
    <button class="active" data-filter="all">全部</button>
    <button data-filter="danger">⚠️ 危險</button>
    <button data-filter="alert">⚡ 警戒</button>
    <select id="sort">
      <option value="rank">排序：風險分數（預設）</option>
      <option value="maint">排序：維持率由低到高</option>
      <option value="bigloss">排序：20 日大跌機率由高到低</option>
      <option value="days">排序：在榜天數由多到少</option>
    </select>
    <span class="muted" id="count"></span>
  </div>
  <table id="grid">
    <thead><tr>
      <th>#</th><th>等級</th><th>標的</th><th>板塊</th><th>收盤</th><th>漲跌</th>
      <th>維持率</th><th>融資 1 日</th><th>融資 3 日</th><th>風險分數</th><th>在榜</th>
      <th>20 日大跌機率</th><th>20 日預期淨報酬</th><th>AI 動作</th><th>AI 理由</th><th>說明</th>
    </tr></thead>
    <tbody>
      {''.join(body) if body else '<tr><td class="empty" colspan="16">本期沒有可用的風險掃描資料</td></tr>'}
    </tbody>
  </table>
</main>
<script>
(function () {{
  var grid = document.getElementById('grid');
  var tbody = grid.tBodies[0];
  var rows = Array.prototype.slice.call(tbody.rows);
  var filter = 'all';
  var counter = document.getElementById('count');
  function apply() {{
    var visible = 0;
    rows.forEach(function (row) {{
      var show = filter === 'all' || row.getAttribute('data-severity') === filter;
      row.style.display = show ? '' : 'none';
      if (show) {{
        visible++;
        var cell = row.cells[0];
        if (cell) {{ cell.textContent = String(visible); }}
      }}
    }});
    counter.textContent = '顯示 ' + visible + ' / ' + rows.length;
  }}
  document.querySelectorAll('.controls button').forEach(function (button) {{
    button.addEventListener('click', function () {{
      document.querySelectorAll('.controls button').forEach(function (b) {{ b.classList.remove('active'); }});
      button.classList.add('active');
      filter = button.getAttribute('data-filter');
      apply();
    }});
  }});
  document.getElementById('sort').addEventListener('change', function (event) {{
    var key = event.target.value;
    var getter = {{
      rank: function (r) {{ return -parseFloat(r.getAttribute('data-composite') || '0'); }},
      maint: function (r) {{ return parseFloat(r.getAttribute('data-maint') || '9999'); }},
      bigloss: function (r) {{ return -parseFloat(r.getAttribute('data-bigloss') || '0'); }},
      days: function (r) {{ return -parseFloat(r.getAttribute('data-days') || '0'); }}
    }}[key];
    var sorted = rows.slice().sort(function (a, b) {{
      var d = getter(a) - getter(b);
      return d !== 0 ? d : a.getAttribute('data-rank') - b.getAttribute('data-rank');
    }});
    sorted.forEach(function (row) {{ tbody.appendChild(row); }});
    rows = sorted;
    apply();
  }});
  apply();
}})();
</script>
</body>
</html>
"""


def write(date: str, public: Path) -> dict:
    """Build the rows and write both artifacts. Missing scan output is not an
    error: the margin scan is an optional stage, so the page simply says there
    is no scan for this session instead of failing the whole release."""
    payload = build(date)
    data_dir = public / 'data'
    data_dir.mkdir(parents=True, exist_ok=True)
    ps.atomic_json(data_dir / 'danger.json', payload)
    import danger_track
    danger_track.write_ledger(date, payload, public)
    track = danger_track.evaluate(public, date, payload.get('nightly_id') or '')
    payload['track'] = track
    (public / 'danger.html').write_text(render_html(payload), encoding='utf-8')
    return payload


def main() -> int:
    date = report_date()
    payload = write(date, ps.PUBLIC)
    summary = payload['summary']
    print(f"danger: date={date} danger={summary['danger']} alert={summary['alert']} "
          f"candidates={summary['candidates']} model_rows={summary['model_rows']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
