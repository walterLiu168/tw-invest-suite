"""Watchlist history: every run, every pick, every day.

The daily watchlist is a 24-name snapshot that is replaced every night, so the
page itself can never answer "when was this name in the list, and what did we
do after it showed up?".  The picks live in MySQL
(`market_screen_runs` / `market_screen_picks`) with `close_at_pick`, `score`,
`rationale`, `bucket` and `horizon` kept for every run, and canonical closes
live in `daily_data2_full`.  This module turns that into one compact JSON
document the history page can fetch:

    public/data/watchlist-history.json

Schema (see the history page for the human-readable version):
    date, nightly_id, source      identity, required by the nightly contract
    runs, dates, current          coverage
    tickers[ticker]
        name, industry            from the newest run the ticker appeared in
        first_seen, last_seen     bounds of the ticker appearing in the list
        appearances               number of runs the ticker appeared in
        in_current                still on the latest watchlist
        entries[]                 one per run the ticker appeared in
            d    run date
            b    market-cap bucket
            h    horizon (long / short / ...)
            s    status
            sc   score
            c    close on the run date
            chg  change_pct on the run date
            e60  excess_return_60d at pick time
            e240 excess_return_240d at pick time
            r    rationale
        path[]                    canonical daily closes from first_seen to
                                  last_seen: [date, close, ret_since_first]

Read-only: it never writes to the database and never touches a certified
artifact outside `public/data/`.
"""
from __future__ import annotations

import json
import os
import re
import sys
import uuid
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import db_client as db  # noqa: E402

SOURCE = "canonical MySQL market_screen_runs / market_screen_picks / daily_data2_full"
MAX_RATIONALE = 400
RATIONALE_FIELD = re.compile(r"\*\*([^*]+)\*\*\s*[：:]\s*")


def _rows(cursor, sql, params=()):
    """Return a list of dicts, whether the cursor is a tuple or dict cursor."""
    cursor.execute(sql, params)
    rows = cursor.fetchall()
    if not rows:
        return []
    if isinstance(rows[0], dict):
        return [dict(row) for row in rows]
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row)) for row in rows]


def _num(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, 4) if number == number else None


def _text(value, limit=None):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:limit] if limit else text


def parse_rationale(text):
    """Split the pick rationale into its labelled facts.

    The rationale is written as ``**方向**：偏多 **失效條件**：…``.  Keeping the
    raw string would repeat every label 1,200 times and would force the page
    to render one blob; splitting it keeps each fact on its own line and makes
    the document smaller.
    """
    if not text:
        return None
    parts = RATIONALE_FIELD.split(str(text))
    facts = {}
    for index in range(1, len(parts) - 1, 2):
        key = parts[index].strip()
        value = parts[index + 1].strip()
        if key and value:
            facts[key] = value
    if not facts:
        stripped = str(text).strip()
        return {"說明": stripped} if stripped else None
    return facts


def build_history():
    """Assemble the full watchlist history from the database."""
    with db.get_cursor() as cursor:
        runs = _rows(cursor, """
            SELECT id, run_date, picks_count FROM market_screen_runs ORDER BY run_date
        """)
        picks = _rows(cursor, """
            SELECT id, run_id, ticker, name, industry, horizon, bucket, close_at_pick,
                   change_pct, volume, market_cap, excess_return_60d,
                   excess_return_240d, score, rationale, status
            FROM market_screen_picks ORDER BY run_id, ticker, id
        """)
        if not runs:
            raise ValueError("market_screen_runs is empty: no watchlist history to build")
        by_run = {r["id"]: r for r in runs}
        for pick in picks:
            pick["run_date"] = str(by_run[pick["run_id"]]["run_date"])[:10]
        # market_screen_picks has no unique key on (run_id, ticker): a ticker can
        # be written twice for the same run, which also means that run carries
        # fewer distinct names than picks_count.  Count the duplicate so the
        # document can disclose it instead of quietly double-counting a name.
        seen_pick = set()
        deduped = []
        duplicate_runs = defaultdict(list)
        for pick in picks:
            key = (pick["run_id"], str(pick["ticker"]))
            if key in seen_pick:
                duplicate_runs[pick["run_date"]].append(str(pick["ticker"]))
                continue
            seen_pick.add(key)
            deduped.append(pick)
        picks = deduped
        ticker_set = sorted({str(p["ticker"]) for p in picks})
        first_date = min(str(r["run_date"])[:10] for r in runs)
        last_date = max(str(r["run_date"])[:10] for r in runs)
        closes = _rows(cursor, """
            SELECT d.Ticker AS ticker, d.Date AS trade_date, d.Close AS close
            FROM daily_data2_full d
            JOIN (SELECT DISTINCT ticker FROM market_screen_picks) p
              ON p.ticker = d.Ticker
            WHERE d.Date BETWEEN %s AND %s
            ORDER BY d.Ticker, d.Date
        """, (first_date, last_date))

    price_map = {}
    for row in closes:
        price_map.setdefault(str(row["ticker"]), []).append(
            (str(row["trade_date"])[:10], _num(row["close"])))

    entries = {}
    for pick in picks:
        ticker = str(pick["ticker"])
        entries.setdefault(ticker, []).append({
            "d": pick["run_date"],
            "b": _text(pick["bucket"]),
            "h": _text(pick["horizon"]),
            "s": _text(pick["status"]),
            "sc": _num(pick["score"]),
            "c": _num(pick["close_at_pick"]),
            "chg": _num(pick["change_pct"]),
            "e60": _num(pick["excess_return_60d"]),
            "e240": _num(pick["excess_return_240d"]),
            "r": parse_rationale(_text(pick["rationale"], MAX_RATIONALE)),
        })

    latest_run = runs[-1]
    current = {str(p["ticker"]) for p in picks
               if p["run_id"] == latest_run["id"]}

    # canonical names/industries; the picks table carries blanks for some rows
    try:
        industries = db.all_industries() or {}
    except Exception:  # noqa: BLE001 - metadata is a nice-to-have, not required
        industries = {}

    tickers = {}
    for ticker, items in entries.items():
        items.sort(key=lambda e: e["d"])
        newest = items[-1]
        meta = industries.get(ticker) or {}
        pick_name = newest.get("name")
        if not pick_name or str(pick_name).strip() == ticker:
            pick_name = meta.get("company")
        pick_industry = newest.get("industry")
        if not pick_industry:
            pick_industry = meta.get("industry")
        path = []
        base = None
        for day, close in price_map.get(ticker, []):
            if day < items[0]["d"]:
                continue
            if base is None:
                base = close
            path.append([day, round(close, 2) if close is not None else None,
                         round(close / base - 1.0, 6) if base and close else None])
        tickers[ticker] = {
            "name": pick_name or ticker,
            "industry": pick_industry,
            "first_seen": items[0]["d"],
            "last_seen": items[-1]["d"],
            "appearances": len(items),
            "in_current": ticker in current,
            "entries": items,
            "path": path,
        }

    return {
        "runs": len(runs),
        "dates": [str(r["run_date"])[:10] for r in runs],
        "current": {"date": str(latest_run["run_date"])[:10],
                    "run_id": int(latest_run["id"]),
                    "picks_count": int(latest_run["picks_count"] or 0)},
        "duplicate_pick_rows": {day: sorted(set(names))
                                for day, names in sorted(duplicate_runs.items())},
        "tickers": tickers,
        "schema": {
            "d": "run date", "b": "market-cap bucket", "h": "horizon",
            "s": "status", "sc": "score", "c": "close on run date",
            "chg": "change_pct on run date", "e60": "excess_return_60d",
            "e240": "excess_return_240d", "r": "rationale",
            "path": "[date, close, return since first_seen]",
        },
    }


def atomic_json_compact(path: Path, value):
    """Write compact JSON atomically.

    The nightly helper pretty-prints with indent=2; this document is ~1 MB and
    is fetched by a phone, so it is written compact instead.  GitHub Pages
    still serves it gzip-compressed.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                              default=str), encoding="utf-8")
    os.replace(tmp, path)


def write_json(history, path: Path, date: str, nightly_id: str):
    """Write the history document with the identity the nightly contract wants."""
    payload = dict(history)
    payload.update(date=date, nightly_id=nightly_id, source=SOURCE)
    atomic_json_compact(path, payload)
    return payload


def main():
    import pipeline_state as ps
    run = ps.read_json(ps.STATE)
    history = build_history()
    path = ps.PUBLIC / "data" / "watchlist-history.json"
    write_json(history, path, run.get("data_date", ""), run.get("nightly_id", ""))
    print(f"watchlist_history: runs={history['runs']} tickers={len(history['tickers'])} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
