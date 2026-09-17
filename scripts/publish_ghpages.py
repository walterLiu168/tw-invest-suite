"""Prepare an immutable release; scheduled --publish also verifies GitHub Pages."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

import pipeline_state as ps
import publish_manifest as pm

RESULT = ps.RUNTIME / "_debug" / "publication_result.json"


def run(args, cwd):
    r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    if r.returncode:
        raise RuntimeError(f"{args[0:2]} exit {r.returncode}: {(r.stderr or r.stdout)[-700:]}")
    return r.stdout.strip()


def verify_staged(root, manifest):
    for artifact in manifest["artifacts"]:
        relative = Path(artifact["gh_path"])
        target = (root / relative).resolve()
        if not target.is_relative_to(root.resolve()):
            raise ValueError("artifact path outside release")
        if ps.sha256(target) != artifact["sha256"]:
            raise ValueError(f"staged SHA mismatch: {relative}")


def initialize_release_git(root):
    run(["git", "init", "-b", "main"], root)
    # Git on Windows otherwise converts CRLF to LF on add, invalidating the
    # certified byte hashes even though the working tree remains unchanged.
    run(["git", "config", "core.autocrlf", "false"], root)
    attributes = root / ".git" / "info" / "attributes"
    attributes.parent.mkdir(parents=True, exist_ok=True)
    attributes.write_text("* -text -filter -ident -working-tree-encoding\n", encoding="utf-8")


def prepare_site(marker):
    manifest = pm.build_certified_manifest(marker)
    root = Path(tempfile.mkdtemp(prefix="tw-invest-release-", dir=ps.REPO.parent))
    # Fresh staging directory, never a mutable or partially overwritten deployed tree.
    for src in ps.PUBLIC.iterdir():
        if src.name == "analyze":
            continue
        dest = root / src.name
        if src.is_dir():
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)
    for a in manifest["artifacts"]:
        dest = root / a["gh_path"]
        if not dest.resolve().is_relative_to(root.resolve()):
            raise ValueError("invalid release path")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(a["abs_path"], dest)
    name = f"data/publish_manifest_{manifest['data_date']}.json"
    ps.atomic_json(root / name, manifest)
    ps.atomic_json(ps.PUBLIC / name, manifest)
    (root / ".nojekyll").touch()
    verify_staged(root, manifest)
    return root, manifest


def remote_verify(root, manifest):
    wanted = {"watchlist.html", "patterns.html", "analyze/patterns.html", "analyze/patterns.json", "data/patterns.json", "data/watchlist-full.json"}
    wanted.update(f"analyze/{p['ticker']}.html" for p in manifest["tickers"])
    wanted.update(a['gh_path'] for a in manifest['artifacts'] if not a['gh_path'].startswith('analyze/'))
    wanted.add(f"data/publish_manifest_{manifest['data_date']}.json")
    return remote_verify_paths(root, manifest, wanted)


def remote_verify_paths(root, manifest, wanted):
    def check(relative):
        request = urllib.request.Request(pm.GITHUB_PAGES_BASE + "/" + relative + "?run=" + manifest["nightly_id"], headers={"Cache-Control": "no-cache"})
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read()
        expected = ps.sha256(root / relative)
        if hashlib.sha256(body).hexdigest() != expected:
            raise ValueError(f"remote SHA mismatch: {relative}")
        return relative
    with ThreadPoolExecutor(max_workers=4) as pool:
        return list(pool.map(check, sorted(wanted)))


def commit_if_changed(root, message):
    """An identical certified release remains publishable on a Scheduler retry."""
    if run(["git", "diff", "--cached", "--name-only"], root):
        run(["git", "commit", "-m", message], root)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", action="store_true", help="Push the prepared release; default only prepares locally")
    ap.add_argument("--prepare-only", action="store_true")
    args = ap.parse_args()
    result = {}
    try:
        marker = ps.verify_marker()
        root, manifest = prepare_site(marker)
        print(f"PREPARED {root} data_date={manifest['data_date']} run_id={manifest['run_id']} artifacts={len(manifest['artifacts'])}", flush=True)
        ps.atomic_json(ps.RUNTIME / "_debug" / "prepared_release.json", {"root": str(root), "nightly_id": manifest["nightly_id"], "data_date": manifest["data_date"], "artifacts": len(manifest["artifacts"])})
        if not args.publish or args.prepare_only:
            return 0
        result = {"nightly_id": manifest["nightly_id"], "data_date": manifest["data_date"], "run_id": manifest["run_id"], "status": "publishing"}
        ps.atomic_json(RESULT, result)
        initialize_release_git(root)
        run(["git", "remote", "add", "origin", "https://github.com/walterLiu168/tw-invest-suite.git"], root)
        run(["git", "fetch", "--depth=1", "origin", "gh-pages"], root)
        run(["git", "reset", "--mixed", "FETCH_HEAD"], root)
        run(["git", "config", "user.email", "walterLiu168@users.noreply.github.com"], root)
        run(["git", "config", "user.name", "walterLiu168"], root)
        run(["git", "add", "-A"], root)
        commit_if_changed(root, f"Daily release {manifest['data_date']} run {manifest['nightly_id']}")
        verify_staged(root, manifest)
        ps.verify_marker(marker)  # no changed sources/artifacts while preparing
        run(["git", "push", "origin", "HEAD:gh-pages"], root)
        result["published_commit"] = run(["git", "rev-parse", "HEAD"], root)
        for attempt in range(10):
            try:
                result["verified_paths"] = remote_verify(root, manifest)
                break
            except Exception:
                if attempt == 9:
                    raise
                time.sleep(30)
        result.update(status="verified", analytical_verified=True, report_status="pending", verified_at=datetime.now().isoformat())
        ps.atomic_json(RESULT, result)
        # Same publishing job finishes the report after actual remote verification.
        post = subprocess.run([sys.executable, str(ps.REPO / "scripts" / "postflight_daily.py"), "--after-publish"], timeout=240)
        import build_dashboard
        build_dashboard.main()
        report_paths = ("data/dashboard.md", f"data/daily_summary_{manifest['data_date']}.md")
        for rel in report_paths:
            src = ps.PUBLIC / rel
            if not src.is_file():
                raise ValueError(f"missing final report: {rel}")
            shutil.copy2(src, root / rel)
        run(["git", "add", "data"], root)
        commit_if_changed(root, f"Verified daily status {manifest['data_date']}")
        run(["git", "push", "origin", "HEAD:gh-pages"], root)
        result["status_commit"] = run(["git", "rev-parse", "HEAD"], root)
        for attempt in range(10):
            try:
                result["verified_report_paths"] = remote_verify_paths(root, manifest, report_paths)
                break
            except Exception:
                if attempt == 9:
                    raise
                time.sleep(30)
        result.update(postflight_exit=post.returncode, report_status="verified",
                      reports_verified_at=datetime.now().isoformat(),
                      status="verified" if post.returncode == 0 else "failed")
        ps.atomic_json(RESULT, result)
        print(f"PUBLISHED_AND_VERIFIED data_date={manifest['data_date']} postflight_exit={post.returncode}")
        return post.returncode
    except Exception as e:
        result.update(status="failed", error=str(e), at=datetime.now().isoformat())
        ps.atomic_json(RESULT, result)
        print(f"FATAL: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
