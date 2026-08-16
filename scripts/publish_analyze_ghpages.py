"""
Publish 1,962 analyze HTML files to GitHub Pages.

Source: C:\\Groove-Lab\\analyze\\
Target: walterLiu168/stock-report gh-pages branch under `analyze/` directory

After deploy: https://walterLiu168.github.io/stock-report/analyze/
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPO = "walterLiu168/stock-report"
SOURCE_DIR = Path(r"C:\Groove-Lab\analyze")
PAGES_URL_BASE = f"https://walterLiu168.github.io/stock-report/analyze"


def main():
    print(f"=== Publish analyze/ to GitHub Pages ===\n")
    print(f"  Source: {SOURCE_DIR}")
    print(f"  Target: {REPO} gh-pages branch under /analyze/\n")

    if not SOURCE_DIR.exists():
        print(f"  ERR: {SOURCE_DIR} not found")
        sys.exit(1)

    html_files = list(SOURCE_DIR.glob("*.html"))
    print(f"  Found {len(html_files)} HTML files\n")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        env = os.environ.copy()
        env["GH_TOKEN"] = ""  # use gh CLI auth

        clone_url = f"https://github.com/{REPO}.git"

        # 1. Clone gh-pages branch
        print(f"  Cloning {REPO} gh-pages branch...")
        r = subprocess.run(
            ["git", "clone", "--branch", "gh-pages", "--depth", "1", clone_url, str(tmp)],
            capture_output=True, text=True, env=env
        )
        if r.returncode != 0:
            print(f"    gh-pages clone failed: {r.stderr[:200]}")
            print(f"    Trying to create gh-pages branch...")
            tmp.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init", "-b", "gh-pages"], cwd=tmp, check=True,
                          env=env, capture_output=True)
            subprocess.run(["git", "remote", "add", "origin", clone_url], cwd=tmp,
                          check=True, env=env, capture_output=True)
            (tmp / "index.html").write_text("<html><body><h1>Initial</h1></body></html>")
            subprocess.run(["git", "add", "."], cwd=tmp, check=True, env=env, capture_output=True)
            subprocess.run(
                ["git", "-c", "user.email=bot@local", "-c", "user.name=tw-invest-suite",
                 "commit", "-m", "init gh-pages"],
                cwd=tmp, check=True, env=env, capture_output=True
            )

        # 2. Copy analyze/ contents
        target_dir = tmp / "analyze"
        target_dir.mkdir(exist_ok=True)
        for f in html_files:
            shutil.copy(f, target_dir / f.name)
        print(f"  Copied {len(html_files)} files to {target_dir}")

        # 3. Commit + push
        subprocess.run(["git", "add", "."], cwd=tmp, check=True, env=env, capture_output=True)
        r = subprocess.run(["git", "diff", "--cached", "--stat"], cwd=tmp,
                          capture_output=True, text=True, env=env)
        if not r.stdout.strip():
            print("    no changes to commit")
            return
        print(f"  Changes:\n{r.stdout[:300]}")

        msg = f"publish {len(html_files)} analyze reports {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}"
        subprocess.run(
            ["git", "-c", "user.email=bot@local", "-c", "user.name=tw-invest-suite",
             "commit", "-m", msg],
            cwd=tmp, check=True, env=env, capture_output=True
        )
        print(f"  Pushing to gh-pages...")
        r = subprocess.run(
            ["git", "push", "origin", "gh-pages", "--force"],
            cwd=tmp, capture_output=True, text=True, env=env
        )
        if r.returncode == 0:
            print(f"    ✓ pushed")
        else:
            print(f"    ❌ push failed: {r.stderr}")
            sys.exit(1)

    print(f"\n✅ Done. Public URL: {PAGES_URL_BASE}/")
    print(f"   Example: {PAGES_URL_BASE}/2330.html")
    print(f"   Index:   {PAGES_URL_BASE}/index.html")
    print(f"\nNote: GitHub Pages may take 1-2 min to deploy.")


if __name__ == "__main__":
    main()
