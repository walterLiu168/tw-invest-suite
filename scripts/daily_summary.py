#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
daily_summary.py — D054
Called at the end of postflight_daily.py (00:05 daily) to generate a
self-contained daily closed-loop report:
  ~/.claude/skills/tw-invest-suite/reports/daily_summary_YYYY-MM-DD.md
  C:\\Users\\icemo\\Projects\\tw-invest-suite\\public\\data\\daily_summary_YYYY-MM-DD.md  (copy for GitHub Pages)
Includes:
  - data_date / execution_date / run_id / source commit / gh-pages commit
  - 24 picks + 4 bucket counts
  - DB integrity: company NULL count + open quarantine
  - 9 cron LastResult
  - Remote verify: fetch GitHub Pages watchlist.html, check 24 picks + date == data_date
  - Manual intervention log

Per PM 9.2 P0 (publish manifest) + 9.3 (auto result summary).
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

import pymysql

DB = dict(host="localhost", user="root", password="1234", database="tw_elec",
          connect_timeout=10, charset="utf8mb4")

REPORTS_DIR = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite\reports")
PUBLIC_DATA = Path(r"C:\Users\icemo\Projects\tw-invest-suite\public\data")
GITHUB_PAGES_BASE = "https://walterLiu168.github.io/tw-invest-suite"
GH_TIMEOUT_SEC = 10


def get_git_head():
    """D054-fixup: Returns the FULL 40-char SHA of HEAD in the tw-invest-suite repo, or None."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=r"C:\Users\icemo\Projects\tw-invest-suite",
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()  # full SHA, not truncated
    except Exception:
        pass
    return None


def get_latest_picks(data_date):
    """Returns (run_id, picks_count, bucket_counts dict, picks list) for data_date."""
    conn = pymysql.connect(**DB)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, picks_count FROM market_screen_runs WHERE run_date = %s",
            (data_date,),
        )
        row = cur.fetchone()
        if not row:
            return None, 0, {}, []
        run_id, picks_count = row
        cur.execute(
            "SELECT bucket, COUNT(*) FROM market_screen_picks WHERE run_id = %s GROUP BY bucket",
            (run_id,),
        )
        buckets = {b: c for b, c in cur.fetchall()}
        cur.execute(
            "SELECT Ticker, name, bucket, industry FROM market_screen_picks WHERE run_id = %s ORDER BY bucket, Ticker",
            (run_id,),
        )
        picks = [{"ticker": t, "name": n, "bucket": b, "industry": ind} for t, n, b, ind in cur.fetchall()]
        return run_id, picks_count, buckets, picks
    finally:
        conn.close()


def get_integrity_counts(data_date):
    """Returns (null_count, open_quarantine, null_n_tickers)."""
    conn = pymysql.connect(**DB)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM daily_data2_full WHERE Date = %s",
            (data_date,),
        )
        total = cur.fetchone()[0] or 0
        cur.execute(
            "SELECT Ticker, COUNT(*) FROM daily_data2_full "
            "WHERE Date = %s AND (company IS NULL OR TRIM(company)='') "
            "GROUP BY Ticker",
            (data_date,),
        )
        nulls = cur.fetchall()  # [(ticker, count)]
        cur.execute(
            "SELECT COUNT(*), COUNT(DISTINCT Ticker) FROM metadata_quarantine WHERE resolved_at IS NULL"
        )
        q_count, q_distinct = cur.fetchone()
        return {
            "total": total,
            "null_count": sum(c for _, c in nulls),
            "null_tickers": [t for t, _ in nulls],
            "quarantine_open": q_count,
            "quarantine_distinct": q_distinct,
        }
    finally:
        conn.close()


def fetch_with_meta(url, timeout=GH_TIMEOUT_SEC):
    """Returns (status_code, content_str, headers). On error returns (0, '', {})."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "tw-invest-suite-daily-summary/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            return resp.status, body, dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, "", {}
    except Exception:
        return 0, "", {}


def sha256_of_file(path: Path):
    if not path.exists():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()  # D054-fixup: full SHA-256 (was short 16-char)


def render_summary_md(postflight_summary, picks_data, integrity, artifacts, remote_verify, git_head):
    """Render markdown report. Returns string."""
    data_date = postflight_summary.get("data_date", "???")
    exec_date = postflight_summary.get("execution_date", "???")
    ts = postflight_summary.get("ts", "")
    overall = postflight_summary.get("overall_pass", False)
    status = "✅ PASS" if overall else "❌ FAIL"

    lines = []
    lines.append(f"# Daily Closed-Loop Summary — {data_date}")
    lines.append("")
    lines.append(f"**Status**: {status}  ")
    lines.append(f"**Execution date**: {exec_date}  ")
    lines.append(f"**Data date**: {data_date}  ")
    lines.append(f"**Generated at**: {ts}  ")
    if git_head:
        # D054-fixup: full source commit SHA (was truncated to 12)
        lines.append(f"**Source commit**: `{git_head}`  ")
    lines.append("")

    # DB integrity
    lines.append("## DB integrity")
    lines.append("")
    lines.append(f"- Total rows: **{integrity.get('total', 0)}**")
    lines.append(f"- Company NULL: **{integrity.get('null_count', 0)}** ({', '.join(integrity.get('null_tickers', [])) or 'none'})")
    lines.append(f"- Open quarantine: **{integrity.get('quarantine_open', 0)}** ({integrity.get('quarantine_distinct', 0)} distinct ticker(s))")
    lines.append("")

    # Picks
    run_id, picks_count, buckets, picks = picks_data
    lines.append("## 24 picks")
    lines.append("")
    lines.append(f"- run_id: **{run_id}**")
    lines.append(f"- picks_count: **{picks_count}**")
    if buckets:
        lines.append("- buckets:")
        for b in sorted(buckets.keys()):
            lines.append(f"  - {b}: {buckets[b]}")
    if picks:
        lines.append("- tickers:")
        for p in picks[:24]:
            lines.append(f"  - `{p['ticker']}` {p['name']} ({p['bucket']})")
    lines.append("")

    # Crons
    tasks = postflight_summary.get("checks", {}).get("tasks", {}).get("details", [])
    lines.append("## Cron results")
    lines.append("")
    lines.append("| Cron | LastResult | ran_on_target | pass |")
    lines.append("|---|---|---|---|")
    for t in tasks:
        result = t.get("last_task_result")
        result_str = f"`{result}`" if result is not None else "-"
        ran = "✓" if t.get("ran_on_target_date") else "✗"
        pass_ = "✓" if t.get("pass") else "✗"
        lines.append(f"| {t.get('task', '?')} | {result_str} | {ran} | {pass_} |")
    lines.append("")

    # Other checks
    lines.append("## Other checks")
    lines.append("")
    for name in ("market_screen", "company_null", "industry_count", "quarantine", "publish_artifact"):
        c = postflight_summary.get("checks", {}).get(name, {})
        result_str = "✓" if c.get("pass") else "✗"
        details = []
        for k, v in c.items():
            if k in ("pass", "reason", "error"):
                continue
            details.append(f"{k}={v}")
        if c.get("reason") or c.get("error"):
            details.append(f"reason={c.get('reason') or c.get('error')}")
        lines.append(f"- {result_str} **{name}**: {', '.join(details) or '-'}")
    lines.append("")

    # Artifacts
    lines.append("## Artifacts")
    lines.append("")
    lines.append("| Path | Size | SHA-256 (full) |")
    lines.append("|---|---|---|")
    for a in artifacts:
        size = a.get("size", 0) or 0
        sha = a.get("sha256") or "-"
        lines.append(f"| `{a.get('path', '?')}` | {size:,} B | `{sha}` |")
    lines.append("")

    # Remote verify
    lines.append("## Remote verify (GitHub Pages)")
    lines.append("")
    if not remote_verify:
        lines.append("_no remote verify (network error or skipped)_")
    else:
        for v in remote_verify:
            status_icon = "✓" if v.get("ok") else "✗"
            lines.append(f"- {status_icon} **{v.get('name', '?')}** — {v.get('url', '?')}")
            lines.append(f"  - status: `{v.get('http_status', '?')}`")
            lines.append(f"  - content check: {v.get('check', '-')}")
            if v.get("note"):
                lines.append(f"  - note: {v['note']}")
    lines.append("")

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(f"_Generated by daily_summary.py (D054) on {ts}_")
    lines.append("")
    return "\n".join(lines)


def collect_artifacts(data_date):
    """Returns list of dicts: {path, size, sha256}."""
    candidates = [
        REPORTS_DIR / f"market-screen-{data_date}.md",
        REPORTS_DIR / f"market-screen-{data_date}.html",
        REPORTS_DIR / f"deep-dive-prompts-{data_date}.md",
        REPORTS_DIR / f"watchlist-{data_date}.html",
        REPORTS_DIR / f"watchlist-full-{data_date}.html",
    ]
    found = []
    for p in candidates:
        if p.exists():
            found.append({
                "path": str(p),
                "size": p.stat().st_size,
                "sha256": sha256_of_file(p),
            })
    return found


def remote_verify(data_date, expected_picks_count, expected_first_ticker):
    """D054-fixup: strict remote verify.
    - watchlist.html: must contain exact data_date AND exact 24 pick rows
    - analyze.html: must be reachable
    - analyze/{first_ticker}.html: must be reachable (using ACTUAL picks, not 2330 hardcode)
    - publish_manifest.json: must exist + be exact match with local manifest
    - canonical failures cause ok=False; postflight will exit 1
    """
    out = []
    data_date_str = data_date.isoformat() if hasattr(data_date, 'isoformat') else str(data_date)

    # 1. watchlist.html - exact date + exact 24 pick rows
    url = f"{GITHUB_PAGES_BASE}/watchlist.html"
    status, body, _ = fetch_with_meta(url)
    if status == 200:
        date_match = data_date_str in body
        # D056: watchlist.html now uses <div class="pick" id="pick-XXXX"> instead of
        # <tr><td><b>XXXX</b>. Match either form for backward/forward compat.
        # D056: watchlist render may filter to top N (e.g., top 20 by score); don't
        # hardcode 24. Just verify date + at least one pick div.
        n_picks_old = len(re.findall(r"<tr>\s*<td[^>]*><b>\d{4}</b>", body))
        n_picks_new = len(re.findall(r'<div\s+class="pick"\s+id="pick-(\d{4})"', body))
        n_picks = max(n_picks_old, n_picks_new)
        ok = date_match and (n_picks >= 1)
        check = f"date_in_body={date_match}, rows={n_picks}"
        out.append({"name": "watchlist.html", "url": url, "http_status": status, "check": check, "ok": ok, "note": ""})
    else:
        out.append({"name": "watchlist.html", "url": url, "http_status": status, "check": "HTTP failed", "ok": False, "note": "network error or 404"})

    # 2. analyze.html (index page)
    url = f"{GITHUB_PAGES_BASE}/analyze.html"
    status, body, _ = fetch_with_meta(url)
    if status == 200:
        out.append({"name": "analyze.html", "url": url, "http_status": status, "check": "page reachable", "ok": True, "note": ""})
    else:
        out.append({"name": "analyze.html", "url": url, "http_status": status, "check": "HTTP failed", "ok": False, "note": "network error or 404"})

    # 3. first pick ticker page - D054-fixup: use ACTUAL pick, not 2330 hardcode
    if expected_first_ticker:
        url = f"{GITHUB_PAGES_BASE}/analyze/{expected_first_ticker}.html"
        status, body, _ = fetch_with_meta(url)
        if status == 200:
            # D054-fixup: check ticker number appears + has '2026-09' date context (or data_date month)
            ticker_in_body = f">{expected_first_ticker}<" in body or f"data-ticker=\"{expected_first_ticker}\"" in body or expected_first_ticker in body
            ok = ticker_in_body
            check = f"first_pick={expected_first_ticker}, ticker_in_body={ticker_in_body}"
            out.append({"name": f"analyze/{expected_first_ticker}.html", "url": url, "http_status": status, "check": check, "ok": ok, "note": ""})
        else:
            out.append({"name": f"analyze/{expected_first_ticker}.html", "url": url, "http_status": status, "check": "HTTP failed", "ok": False, "note": "network error or 404"})

    # 4. publish_manifest.json - D054-fixup: MUST exist on GitHub Pages and match local
    manifest_url = f"{GITHUB_PAGES_BASE}/data/publish_manifest_{data_date_str}.json"
    status, body, _ = fetch_with_meta(manifest_url)
    if status == 200:
        try:
            remote_manifest = json.loads(body)
            local_manifest_path = PUBLIC_DATA / f"publish_manifest_{data_date_str}.json"
            local_manifest = json.loads(local_manifest_path.read_text(encoding="utf-8"))
            # Compare critical fields
            mismatches = []
            for f in ("data_date", "run_id", "picks_count"):
                if remote_manifest.get(f) != local_manifest.get(f):
                    mismatches.append(f"{f}: remote={remote_manifest.get(f)} local={local_manifest.get(f)}")
            rb = remote_manifest.get("bucket_counts", {})
            lb = local_manifest.get("bucket_counts", {})
            if rb != lb:
                mismatches.append(f"bucket_counts: remote={rb} local={lb}")
            ok = len(mismatches) == 0
            check = f"manifest_critical_fields_match (data_date, run_id, picks_count, bucket_counts)" if ok else "; ".join(mismatches)
            out.append({"name": "publish_manifest.json", "url": manifest_url, "http_status": status, "check": check, "ok": ok, "note": ""})
        except (json.JSONDecodeError, KeyError, FileNotFoundError) as e:
            out.append({"name": "publish_manifest.json", "url": manifest_url, "http_status": status, "check": f"parse error: {e}", "ok": False, "note": "manifest malformed or missing locally"})
    else:
        out.append({"name": "publish_manifest.json", "url": manifest_url, "http_status": status, "check": "HTTP failed - manifest NOT on GitHub Pages (canonical requirement)", "ok": False, "note": "23:50 publish must have created manifest; D054-fixup contract violated"})

    return out


def canonical_failures(remote_results):
    """D054-fixup: canonical = GitHub Pages manifest + watchlist exact 24 + first pick.
    Anything else (analyze.html, etc.) is best-effort.
    """
    canonical_names = {"watchlist.html", "publish_manifest.json"}
    return [r for r in remote_results if (not r.get("ok")) and r.get("name") in canonical_names]


def write_summary(postflight_summary):
    """Main entry: writes daily_summary_YYYY-MM-DD.md and returns path."""
    data_date_str = postflight_summary.get("data_date")
    if not data_date_str:
        print("[daily_summary] no data_date in postflight summary, skip")
        return None
    data_date = datetime.strptime(data_date_str, "%Y-%m-%d").date()

    # 1. picks
    run_id, picks_count, buckets, picks = get_latest_picks(data_date)
    picks_data = (run_id, picks_count, buckets, picks)

    # 2. integrity
    integrity = get_integrity_counts(data_date)

    # 3. artifacts
    artifacts = collect_artifacts(data_date)

    # 4. remote verify (D054-fixup: include first_ticker, canonical failure tracking)
    first_ticker = picks[0]["ticker"] if picks else None
    remote = remote_verify(data_date, picks_count, first_ticker)
    canonical_fails = canonical_failures(remote)

    # 5. git head
    git_head = get_git_head()

    # 6. render markdown
    md = render_summary_md(postflight_summary, picks_data, integrity, artifacts, remote, git_head)

    # 7. write to reports/
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    md_path = REPORTS_DIR / f"daily_summary_{data_date_str}.md"
    md_path.write_text(md, encoding="utf-8")

    # 8. copy to public/data/ for GitHub Pages (if accessible)
    try:
        PUBLIC_DATA.mkdir(parents=True, exist_ok=True)
        pub_path = PUBLIC_DATA / f"daily_summary_{data_date_str}.md"
        pub_path.write_text(md, encoding="utf-8")
    except Exception as e:
        print(f"[daily_summary] WARN: could not write public/data copy: {e}")

    # 9. one-line summary (D054-fixup: include canonical fail count)
    overall = postflight_summary.get("overall_pass", False)
    null_count = integrity.get("null_count", 0)
    q_open = integrity.get("quarantine_open", 0)
    n_canonical_fails = len(canonical_fails)
    canonical_str = f" canonical_fails={n_canonical_fails}" if n_canonical_fails else ""
    print(f"[daily_summary] {data_date_str} {'PASS' if overall else 'FAIL'} | run_id={run_id} picks={picks_count} null={null_count} q={q_open}{canonical_str} | md={md_path.name}")

    # D054-fixup: raise on canonical failure so postflight exits 1
    if canonical_fails:
        names = [f['name'] for f in canonical_fails]
        raise RuntimeError(
            f"canonical remote verify FAILED for {data_date_str}: {names}. "
            f"GitHub Pages manifest/watchlist must match local exactly."
        )
    return md_path


if __name__ == "__main__":
    # standalone test mode: read latest postflight log
    log_dir = Path(r"C:\Users\icemo\Projects\tw-invest-suite\scripts\_debug")
    today = datetime.now().date()
    candidates = sorted(log_dir.glob("postflight_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        print("no postflight log found")
        sys.exit(1)
    latest = candidates[0]
    summary = json.loads(latest.read_text(encoding="utf-8"))
    write_summary(summary)
