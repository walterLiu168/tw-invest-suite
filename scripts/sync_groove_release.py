"""Copy only certified stock-report paths; preserve GrooveLab's music app and data."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import shutil
import urllib.request
import uuid

import pipeline_state as ps

GROOVE = Path(r"C:\Groove-Lab")
RESULT = ps.RUNTIME / "_debug" / "groove_publication_result.json"


def verify_paths(root, relative_paths, base):
    def check(relative):
        request = urllib.request.Request(base + "/" + relative + "?verify=" + uuid.uuid4().hex, headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"})
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read()
        if hashlib.sha256(body).hexdigest() != ps.sha256(root / relative):
            raise ValueError(f"Groove remote SHA mismatch: {relative}")
        return relative
    with ThreadPoolExecutor(max_workers=4) as executor:
        return list(executor.map(check, sorted(relative_paths)))


def deploy(root, manifest):
    root = Path(root).resolve()
    paths = {artifact["gh_path"]: artifact["sha256"] for artifact in manifest["artifacts"]}
    for name in ("data/dashboard.md", f"data/daily_summary_{manifest['data_date']}.md", f"data/publish_manifest_{manifest['data_date']}.json"):
        paths[name] = ps.sha256(root / name)
    # Each manifest path is reviewed by the analytical completion gate. Reject escapes,
    # and protect the music application's root entrypoint and configuration.
    for relative, expected in paths.items():
        source = (root / relative).resolve()
        dest = (GROOVE / relative).resolve()
        if not source.is_relative_to(root) or not dest.is_relative_to(GROOVE.resolve()):
            raise ValueError("Unsafe Groove release path")
        if relative in {"index.html", "server.py", "config.yml"} or ps.sha256(source) != expected:
            raise ValueError(f"Invalid certified Groove source: {relative}")
    for relative, expected in paths.items():
        dest = GROOVE / relative
        if dest.is_file() and ps.sha256(dest) == expected:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        temp = dest.with_name(dest.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            shutil.copy2(root / relative, temp)
            if ps.sha256(temp) != expected:
                raise ValueError(f"Groove copy SHA mismatch: {relative}")
            os.replace(temp, dest)
        finally:
            temp.unlink(missing_ok=True)
    wanted = {"watchlist.html", "patterns.html", "analyze/index.html", "analyze/patterns.html", "analyze/patterns.json", "data/patterns.json", "data/watchlist-full.json", "data/dashboard.md", f"data/daily_summary_{manifest['data_date']}.md", f"data/publish_manifest_{manifest['data_date']}.json"}
    wanted.update(f"analyze/{pick['ticker']}.html" for pick in manifest["tickers"])
    wanted.update(a['gh_path'] for a in manifest['artifacts'] if not a['gh_path'].startswith('analyze/'))
    verified = verify_paths(root, wanted, "https://groovelab.dev")
    result = {"nightly_id": manifest["nightly_id"], "data_date": manifest["data_date"], "run_id": manifest["run_id"], "status": "verified", "copied_paths": len(paths), "verified_paths": verified}
    ps.atomic_json(RESULT, result)
    return result


def sync_verified():
    marker = ps.verify_marker()
    result = ps.read_json(ps.RUNTIME / "_debug" / "publication_result.json")
    if result.get("nightly_id") != marker["nightly_id"] or result.get("status") != "verified" or result.get("report_status") != "verified" or result.get("postflight_exit") != 0:
        raise ValueError("Canonical publication and final postflight must pass before Groove sync")
    prepared = ps.read_json(ps.RUNTIME / "_debug" / "prepared_release.json")
    if prepared["nightly_id"] != marker["nightly_id"]:
        raise ValueError("Prepared release belongs to another run")
    root = Path(prepared["root"])
    manifest = ps.read_json(root / "data" / f"publish_manifest_{marker['data_date']}.json")
    if manifest["nightly_id"] != marker["nightly_id"] or manifest["artifacts"] != marker["artifacts"]:
        raise ValueError("Prepared manifest differs from certified marker")
    print(deploy(root, manifest))
    return 0


def main():
    receipt = {"status": "syncing"}
    try:
        run = ps.read_json(ps.STATE)
        receipt.update({key: run[key] for key in ("nightly_id", "data_date", "run_id")})
        ps.atomic_json(RESULT, receipt)
        return sync_verified()
    except Exception as error:
        ps.atomic_json(RESULT, {**receipt, "status": "failed", "error": str(error)})
        raise


if __name__ == "__main__":
    raise SystemExit(main())
