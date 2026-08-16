"""
Watchlist / tracking for market screen picks.

Functions:
  - save_run()        record a market screen run
  - save_picks()      store picks from a screen run
  - get_active_picks() return all currently-active picks
  - update_daily_performance() refresh daily P&L for each active pick
  - get_performance_report() summarize performance by horizon / bucket
"""
import os
import sys
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional

import pymysql

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db_client as db  # noqa: E402
import market_screen as ms  # noqa: E402


def _conn():
    return pymysql.connect(host="localhost", user="root", password="1234",
                           database="tw_elec", charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)


def save_run(total_tickers: int, picks_count: int, notes: str = "") -> int:
    """Insert a market_screen_runs row, return run_id."""
    today = date.today()
    now = datetime.now()
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO market_screen_runs (run_date, run_at, total_tickers, picks_count, notes)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                run_at = VALUES(run_at),
                total_tickers = VALUES(total_tickers),
                picks_count = VALUES(picks_count),
                notes = VALUES(notes)
        """, (today, now, total_tickers, picks_count, notes))
        cur.execute("SELECT id FROM market_screen_runs WHERE run_date = %s", (today,))
        row = cur.fetchone()
        conn.commit()
    return row["id"]


def save_picks(run_id: int, result: Dict[str, Dict[str, List[ms.Candidate]]]) -> int:
    """Insert all picks from a screen result. Returns count inserted."""
    rows = []
    for bucket_label, picks_by_horizon in result.items():
        for horizon in ("long", "short"):
            for c in picks_by_horizon.get(horizon, []):
                rows.append((
                    run_id,
                    c.ticker,
                    c.name,
                    c.industry or "",
                    horizon,
                    bucket_label,
                    float(c.close),
                    float(c.change_pct or 0),
                    int(c.volume),
                    float(c.market_cap) if c.market_cap else None,
                    float(c.excess_return_60d or 0),
                    float(c.excess_return_240d or 0),
                    None,  # score (could compute but skip for now)
                    c.zen_summary or "",
                ))
    if not rows:
        return 0
    with _conn() as conn:
        cur = conn.cursor()
        # Clear today's picks for this run first (idempotent)
        cur.execute("DELETE FROM market_screen_picks WHERE run_id = %s", (run_id,))
        cur.executemany("""
            INSERT INTO market_screen_picks
            (run_id, ticker, name, industry, horizon, bucket,
             close_at_pick, change_pct, volume, market_cap,
             excess_return_60d, excess_return_240d, score, rationale)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, rows)
        conn.commit()
    return len(rows)


def get_active_picks() -> List[Dict]:
    """Return all picks with status='active', newest first."""
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT p.*, r.run_date
            FROM market_screen_picks p
            JOIN market_screen_runs r ON r.id = p.run_id
            WHERE p.status = 'active'
            ORDER BY r.run_date DESC, p.bucket, p.horizon
        """)
        return cur.fetchall()


def update_daily_performance(tickers: Optional[List[str]] = None) -> int:
    """For each active pick, fetch latest price and upsert today's performance row.

    Returns the number of rows written.
    """
    active = get_active_picks()
    if tickers is not None:
        tickers_set = set(tickers)
        active = [p for p in active if p["ticker"] in tickers_set]
    if not active:
        return 0

    target_date = db.latest_date("daily_data2_full")
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    # Use latest data date if today has no data yet
    eff_date = target_date if target_date < today_str else today_str

    with _conn() as conn:
        cur = conn.cursor()
        # Bulk fetch current prices
        placeholders = ",".join(["%s"] * len(active))
        cur.execute(f"""
            SELECT Ticker, Close FROM daily_data2_full
            WHERE Date = %s AND Ticker IN ({placeholders})
        """, (eff_date, *[p["ticker"] for p in active]))
        price_map = {r["Ticker"]: float(r["Close"]) for r in cur.fetchall() if r.get("Close")}

        rows = []
        for p in active:
            cur_close = price_map.get(p["ticker"])
            if cur_close is None or cur_close == 0:
                continue
            pick_close = float(p["close_at_pick"] or 0)
            if pick_close == 0:
                continue
            ret_since_pick = (cur_close - pick_close) / pick_close
            # Get high/low since pick date
            cur.execute("""
                SELECT MAX(High) AS hi, MIN(Low) AS lo FROM daily_data2_full
                WHERE Ticker = %s AND Date >= %s
            """, (p["ticker"], p["run_date"]))
            r2 = cur.fetchone()
            hi = float(r2["hi"]) if r2 and r2["hi"] else cur_close
            lo = float(r2["lo"]) if r2 and r2["lo"] else cur_close
            drawdown = (cur_close - hi) / hi if hi > 0 else 0

            # Get ret since the run_date (price on run_date vs now)
            cur.execute("""
                SELECT Close FROM daily_data2_full
                WHERE Ticker = %s AND Date = %s
            """, (p["ticker"], p["run_date"]))
            r3 = cur.fetchone()
            run_close = float(r3["Close"]) if r3 and r3.get("Close") else pick_close
            ret_since_run = (cur_close - run_close) / run_close if run_close > 0 else 0

            rows.append((
                p["id"], p["ticker"], eff_date, cur_close,
                ret_since_pick, ret_since_run, hi, lo, drawdown
            ))

        if rows:
            cur.executemany("""
                INSERT INTO market_screen_performance
                (pick_id, ticker, trade_date, close,
                 ret_since_pick, ret_since_run, high_since, low_since, drawdown)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    close = VALUES(close),
                    ret_since_pick = VALUES(ret_since_pick),
                    ret_since_run = VALUES(ret_since_run),
                    high_since = VALUES(high_since),
                    low_since = VALUES(low_since),
                    drawdown = VALUES(drawdown)
            """, rows)
            conn.commit()
    return len(rows)


def get_performance_report() -> Dict:
    """Summarize performance by horizon / bucket."""
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                p.horizon,
                p.bucket,
                p.ticker, p.name,
                p.close_at_pick,
                latest.close AS current_close,
                latest.ret_since_pick,
                latest.ret_since_run,
                latest.high_since,
                latest.low_since,
                latest.drawdown,
                r.run_date
            FROM market_screen_picks p
            JOIN market_screen_runs r ON r.id = p.run_id
            LEFT JOIN market_screen_performance latest
                ON latest.pick_id = p.id
                AND latest.trade_date = (
                    SELECT MAX(trade_date) FROM market_screen_performance
                    WHERE pick_id = p.id
                )
            WHERE p.status = 'active'
            ORDER BY p.bucket, p.horizon, p.ticker
        """)
        rows = cur.fetchall()
    return {"picks": rows, "as_of": datetime.now().isoformat()}


def render_performance_md() -> str:
    """Render performance report as a Markdown summary."""
    data = get_performance_report()
    rows = data["picks"]
    if not rows:
        return "# 📊 市場掃描追蹤報告\n\n_尚無進行中的 picks_"

    by_bucket: Dict[str, List[Dict]] = {}
    for r in rows:
        by_bucket.setdefault(r["bucket"], []).append(r)

    today = date.today().strftime("%Y-%m-%d")
    out = [
        f"# 📊 市場掃描追蹤報告（{today}）",
        f"\n_資料截止 {data['as_of']}_\n",
        f"\n活躍 picks 總數：{len(rows)}\n",
    ]

    for bucket in ["<100", "100-300", "300-1000", ">1000"]:
        items = by_bucket.get(bucket, [])
        if not items:
            continue
        out.append(f"\n## {bucket} 元\n")
        out.append("| 代號 | 名稱 | 進場價 | 現價 | 報酬 | 最高 | 最低 | 回撤 | 進場日 |")
        out.append("|---|---|---|---|---|---|---|---|---|")
        for r in items:
            cur = r.get("current_close")
            pick = r.get("close_at_pick")
            ret = r.get("ret_since_pick")
            hi = r.get("high_since")
            lo = r.get("low_since")
            dd = r.get("drawdown")
            rd = r.get("run_date")
            ret_str = f"{ret*100:+.2f}%" if ret is not None else "—"
            hi_str = f"{hi:.1f}" if hi is not None else "—"
            lo_str = f"{lo:.1f}" if lo is not None else "—"
            dd_str = f"{dd*100:+.2f}%" if dd is not None else "—"
            cur_str = f"{cur:.1f}" if cur is not None else "—"
            pick_str = f"{pick:.1f}" if pick is not None else "—"
            horizon_tag = "📈" if r["horizon"] == "long" else "⚡"
            out.append(f"| {horizon_tag} {r['ticker']} | {r['name']} | {pick_str} | {cur_str} | {ret_str} | {hi_str} | {lo_str} | {dd_str} | {rd} |")

    # Summary stats
    rets = [r.get("ret_since_pick") for r in rows if r.get("ret_since_pick") is not None]
    if rets:
        avg = sum(rets) / len(rets)
        wins = sum(1 for r in rets if r > 0)
        out.append(f"\n## 總結\n")
        out.append(f"- 進場 picks：{len(rows)}")
        out.append(f"- 平均報酬：{avg*100:+.2f}%")
        out.append(f"- 勝率：{wins}/{len(rets)} = {wins/len(rets)*100:.0f}%")

    return "\n".join(out)


if __name__ == "__main__":
    print("[1/3] Running screener and saving to DB…")
    result = ms.screen_market()
    total = sum(len(v["long"]) + len(v["short"]) for v in result.values())
    run_id = save_run(total_tickers=1943, picks_count=total,
                     notes="auto-saved by run_market_screen")
    n = save_picks(run_id, result)
    print(f"  run_id={run_id}, saved {n} picks")

    print("[2/3] Updating daily performance…")
    n = update_daily_performance()
    print(f"  updated {n} performance rows")

    print("[3/3] Generating performance report…")
    md = render_performance_md()
    today = date.today().strftime("%Y-%m-%d")
    out_path = os.path.expanduser(
        f"~/.claude/skills/tw-invest-suite/reports/watchlist-{today}.md"
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"  → {out_path}")
    print(md[:600])
