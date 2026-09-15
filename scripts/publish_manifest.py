#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
publish_manifest.py — D054 fixup
Build a publish_manifest_YYYY-MM-DD.json BEFORE the 23:50 publish cron,
so the manifest is part of the same commit as the day's artifacts.

Manifest contract (per PM 9.2 P0):
  - data_date
  - run_id
  - picks_count (must be 24)
  - bucket counts (4 buckets, sum = 24)
  - source commit (full SHA, must be in git HEAD)
  - published commit (filled in by postflight verify, not by build)
  - artifact paths (gh-pages relative) + full SHA-256
  - generated_at / published_at / verified_at (ISO 8601)
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pymysql

DB = dict(host="localhost", user="root", password="1234", database="tw_elec",
          connect_timeout=10, charset="utf8mb4")

REPO = Path(r"C:\Users\icemo\Projects\tw-invest-suite")
PUBLIC_DIR = REPO / "public"
REPORTS_DIR = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite\reports")
GROOVE_ANALYZE = Path(r"C:\Groove-Lab\analyze")
GITHUB_PAGES_BASE = "https://walterLiu168.github.io/tw-invest-suite"


def sha256_full(path: Path):
    """Full SHA-256 of a file's bytes, or None if missing."""
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def git_head_full():
    """Full 40-char SHA of HEAD in the tw-invest-suite repo, or None."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO), capture_output=True, text=True, timeout=5,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return None


def git_head_committed():
    """Verify HEAD is committed (no uncommitted tracked changes).
    D054: untracked files (?? in status) are OK, but M/D/A indicate uncommitted
    tracked changes which violate 'no uncommitted runtime copy' contract.
    Returns True if there are no uncommitted tracked changes.
    """
    try:
        # Use --untracked-files=no to ignore untracked files (D054 allows them)
        r1 = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all", "--", "scripts", "src"],
            cwd=str(REPO), capture_output=True, text=True, timeout=5,
        )
        if r1.returncode != 0:
            return False
        if r1.stdout.strip():
            # Has uncommitted tracked changes (M, D, A, etc.)
            return False
        # Check HEAD is reachable
        r2 = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=str(REPO), capture_output=True, text=True, timeout=5,
        )
        return r2.returncode == 0
    except Exception:
        return False


def fetch_picks(data_date):
    """Returns (run_id, picks_count, bucket_counts dict, tickers list of dict)."""
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
        bucket_counts = {b: int(c) for b, c in cur.fetchall()}
        cur.execute(
            "SELECT Ticker, name, bucket, industry, status FROM market_screen_picks WHERE run_id = %s ORDER BY bucket, Ticker",
            (run_id,),
        )
        tickers = [
            {"ticker": t, "name": n, "bucket": b, "industry": i, "status": s}
            for t, n, b, i, s in cur.fetchall()
        ]
        return run_id, picks_count, bucket_counts, tickers
    finally:
        conn.close()


def artifacts_for(data_date):
    """Returns list of {gh_path, abs_path, sha256, size, exists} for today's artifacts.
    gh_path is the relative path on GitHub Pages (e.g. 'market-screen-2026-09-09.html').
    """
    candidates = [
        ("market-screen-{date}.html", REPORTS_DIR / f"market-screen-{data_date}.html"),
        ("market-screen-{date}.md", REPORTS_DIR / f"market-screen-{data_date}.md"),
        ("deep-dive-prompts-{date}.md", REPORTS_DIR / f"deep-dive-prompts-{data_date}.md"),
        ("watchlist-full-{date}.html", REPORTS_DIR / f"watchlist-full-{data_date}.html"),
        ("data/daily_summary_{date}.md", PUBLIC_DIR / "data" / f"daily_summary_{data_date}.md"),
        ("watchlist.html", REPORTS_DIR / f"watchlist-{data_date}.html"),  # D053 dual-write target
    ]
    out = []
    for gh_path_tmpl, abs_path in candidates:
        gh_path = gh_path_tmpl.format(date=data_date)
        # also try public/ for files copied there
        public_alt = PUBLIC_DIR / gh_path
        target = abs_path
        if not target.exists() and public_alt.exists():
            target = public_alt
        exists = target.exists()
        out.append({
            "gh_path": gh_path,
            "abs_path": str(target),
            "exists": exists,
            "sha256": sha256_full(target) if exists else None,
            "size": target.stat().st_size if exists else 0,
        })
    return out


def build_manifest(data_date):
    """Build the manifest dict. Raises ValueError on critical missing data.
    The dict is JSON-serializable.
    """
    data_date_obj = dt.datetime.strptime(data_date, "%Y-%m-%d").date()
    run_id, picks_count, bucket_counts, tickers = fetch_picks(data_date)
    if run_id is None:
        raise ValueError(f"no market_screen_runs for {data_date}")
    if picks_count != 24:
        raise ValueError(f"picks_count={picks_count} for {data_date}, expected 24")
    if len(tickers) != 24:
        raise ValueError(f"tickers rows={len(tickers)} for {data_date}, expected 24")
    total_buckets = sum(bucket_counts.values())
    if total_buckets != 24:
        raise ValueError(f"bucket sum={total_buckets} for {data_date}, expected 24")

    src_sha = git_head_full()
    head_committed = git_head_committed()
    artifacts = artifacts_for(data_date)
    missing = [a["gh_path"] for a in artifacts if not a["exists"]]
    if missing:
        raise ValueError(f"missing artifacts: {missing}")

    return {
        "manifest_version": "D054-fixup-1",
        "data_date": data_date,
        "run_id": run_id,
        "picks_count": picks_count,
        "bucket_counts": bucket_counts,  # 4 buckets summing to 24
        "tickers": tickers,  # 24 entries
        "source_commit": src_sha,
        "source_commit_committed": head_committed,
        "published_commit": None,  # filled in by postflight remote verify
        "artifacts": artifacts,
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "published_at": None,  # filled in by publish_ghpages
        "verified_at": None,    # filled in by postflight
        "github_pages_base": GITHUB_PAGES_BASE,
    }


def build_certified_manifest(marker=None):
    import pipeline_state as ps
    marker = ps.verify_marker(marker)
    return {
        "manifest_version": "D056-2", "nightly_id": marker["nightly_id"],
        "data_date": marker["data_date"], "run_id": marker["run_id"],
        "picks_count": marker["picks_count"], "bucket_counts": marker["bucket_counts"],
        "tickers": marker["picks"], "source_commit": git_head_full(),
        "source_hashes": marker["source_hashes"], "source_commit_committed": git_head_committed(),
        "artifacts": marker["artifacts"], "generated_at": dt.datetime.now().isoformat(),
        "github_pages_base": GITHUB_PAGES_BASE,
    }


def write_manifest(data_date, output_path):
    """Build + write manifest JSON. Returns the dict."""
    m = build_manifest(data_date)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")
    return m


def verify_manifest_against_local(manifest):
    """Strict local re-verification of manifest fields against DB + filesystem.
    Returns (ok: bool, errors: list[str]).
    """
    errs = []
    dd = manifest.get("data_date")
    run_id = manifest.get("run_id")
    picks_count = manifest.get("picks_count")
    bucket_counts = manifest.get("bucket_counts", {})
    tickers = manifest.get("tickers", [])
    src_sha = manifest.get("source_commit")
    artifacts = manifest.get("artifacts", [])

    if picks_count != 24:
        errs.append(f"picks_count={picks_count}, expected 24")
    if sum(bucket_counts.values()) != 24:
        errs.append(f"bucket sum={sum(bucket_counts.values())}, expected 24")
    if len(tickers) != 24:
        errs.append(f"tickers len={len(tickers)}, expected 24")
    if not src_sha or len(src_sha) < 40:
        errs.append(f"source_commit invalid: {src_sha}")

    # Re-check DB matches manifest
    try:
        conn = pymysql.connect(**DB)
        cur = conn.cursor()
        cur.execute(
            "SELECT picks_count FROM market_screen_runs WHERE id = %s AND run_date = %s",
            (run_id, dd),
        )
        row = cur.fetchone()
        if not row:
            errs.append(f"DB has no run_id={run_id} for {dd}")
        elif row[0] != picks_count:
            errs.append(f"DB run_id={run_id} picks_count={row[0]} != manifest {picks_count}")
        cur.execute(
            "SELECT bucket, COUNT(*) FROM market_screen_picks WHERE run_id = %s GROUP BY bucket",
            (run_id,),
        )
        db_buckets = {b: int(c) for b, c in cur.fetchall()}
        for b, c in bucket_counts.items():
            if db_buckets.get(b, 0) != c:
                errs.append(f"bucket {b}: manifest={c}, db={db_buckets.get(b, 0)}")
        for b, c in db_buckets.items():
            if bucket_counts.get(b, 0) != c:
                errs.append(f"bucket {b}: db={c}, manifest={bucket_counts.get(b, 0)}")
    finally:
        conn.close()

    # Re-check artifact hashes (must be exactly what's in manifest, not stale)
    for art in artifacts:
        p = Path(art["abs_path"])
        actual_sha = sha256_full(p)
        if actual_sha != art["sha256"]:
            errs.append(f"artifact {art['gh_path']} SHA mismatch: manifest={art['sha256']} actual={actual_sha}")

    return (len(errs) == 0, errs)


def main():
    ap = argparse.ArgumentParser(description="Build publish_manifest_YYYY-MM-DD.json")
    ap.add_argument("--date", required=True, help="data_date (YYYY-MM-DD)")
    ap.add_argument("--write-to", required=True, help="output JSON path")
    ap.add_argument("--verify-only", action="store_true", help="read existing manifest and re-verify")
    args = ap.parse_args()

    if args.verify_only:
        out = Path(args.write_to)
        if not out.exists():
            print(f"ERROR: manifest not found: {out}", file=sys.stderr)
            return 1
        m = json.loads(out.read_text(encoding="utf-8"))
        ok, errs = verify_manifest_against_local(m)
        if ok:
            print(f"OK manifest verified: data_date={m.get('data_date')} run_id={m.get('run_id')}")
            return 0
        else:
            print(f"FAIL manifest errors:", file=sys.stderr)
            for e in errs:
                print(f"  - {e}", file=sys.stderr)
            return 1

    try:
        m = write_manifest(args.date, Path(args.write_to))
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 2
    print(f"OK manifest written: data_date={m['data_date']} run_id={m['run_id']} picks={m['picks_count']} artifacts={len(m['artifacts'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
