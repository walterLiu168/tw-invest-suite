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
    wanted = {"watchlist.html", "patterns.html", "data/patterns.json", "data/watchlist-full.json"}
    wanted.update(f"analyze/{p['ticker']}.html" for p in manifest["tickers"])
    wanted.add(f"data/publish_manifest_{manifest['data_date']}.json")
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", action="store_true", help="Push the prepared release; default only prepares locally")
    ap.add_argument("--prepare-only", action="store_true")
    args = ap.parse_args()
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
        run(["git", "commit", "-m", f"Daily release {manifest['data_date']} run {manifest['nightly_id']}"], root)
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
        result.update(status="verified", verified_at=datetime.now().isoformat())
        ps.atomic_json(RESULT, result)
        # Same publishing job finishes the report after actual remote verification.
        post = subprocess.run([sys.executable, str(ps.REPO / "scripts" / "postflight_daily.py"), "--after-publish"], timeout=240)
        import build_dashboard
        build_dashboard.main()
        for rel in ("data/dashboard.md", f"data/daily_summary_{manifest['data_date']}.md"):
            src = ps.PUBLIC / rel
            if src.is_file():
                shutil.copy2(src, root / rel)
        run(["git", "add", "data"], root)
        if run(["git", "diff", "--cached", "--name-only"], root):
            run(["git", "commit", "-m", f"Verified daily status {manifest['data_date']}"], root)
            run(["git", "push", "origin", "HEAD:gh-pages"], root)
            # Verify the morning report itself after its final publication too.
            for attempt in range(10):
                try:
                    req = urllib.request.Request(pm.GITHUB_PAGES_BASE + "/data/dashboard.md?run=" + manifest["nightly_id"], headers={"Cache-Control": "no-cache"})
                    with urllib.request.urlopen(req, timeout=20) as response:
                        dashboard_hash = hashlib.sha256(response.read()).hexdigest()
                    if dashboard_hash != ps.sha256(root / "data" / "dashboard.md"):
                        raise ValueError("remote dashboard SHA mismatch")
                    break
                except Exception:
                    if attempt == 9:
                        raise
                    time.sleep(30)
        print(f"PUBLISHED_AND_VERIFIED data_date={manifest['data_date']} postflight_exit={post.returncode}")
        return post.returncode
    except Exception as e:
        ps.atomic_json(RESULT, {"status": "failed", "error": str(e), "at": datetime.now().isoformat()})
        print(f"FATAL: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
