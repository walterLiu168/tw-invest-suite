"""
Publish the latest market-screen HTML to GitHub Pages via gh-pages branch.

Uses existing `walterLiu168/stock-report` repo (public, intended for stock reports).

Steps:
  1. Enable Pages on stock-report (gh-pages branch)
  2. Clone the repo (or just the gh-pages branch)
  3. Copy all reports/*.html to the gh-pages root
  4. Commit + push
  5. Print the public URL

Re-run anytime to refresh.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPORTS_DIR = Path.home() / ".claude" / "skills" / "tw-invest-suite" / "reports"
REPO = "walterLiu168/stock-report"
PAGES_URL_BASE = f"https://walterLiu168.github.io/stock-report"


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def enable_pages():
    """Enable GitHub Pages on stock-report, source = gh-pages branch."""
    print("  Enabling Pages on stock-report (gh-pages branch)…")
    r = subprocess.run(
        ["gh", "api", f"repos/{REPO}/pages", "-X", "POST",
         "-f", "source[branch]=gh-pages",
         "-f", "source[path]=/",
         "-f", "build_type=legacy"],
        capture_output=True, text=True
    )
    if r.returncode == 0:
        print("    ✓ Pages enabled (or already was)")
    else:
        # Pages may already be enabled; check
        if "already" in r.stderr.lower() or "422" in r.stderr:
            print("    ✓ Pages already enabled")
        else:
            print(f"    ⚠️  Pages enable: {r.stderr.strip()[:200]}")


def publish_via_workflow():
    """Use gh-workflow to publish: just copy HTML to gh-pages branch and push."""
    # We'll work in a temp dir to avoid messing with the user's workspace
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        env = os.environ.copy()
        env["GH_TOKEN"] = ""  # use gh's auth

        # 1. Clone gh-pages branch (create if not exists)
        print(f"  Cloning {REPO} gh-pages branch…")
        clone_url = f"https://github.com/{REPO}.git"
        # First try to clone the branch
        r = subprocess.run(
            ["git", "clone", "--branch", "gh-pages", "--depth", "1", clone_url, str(tmp)],
            capture_output=True, text=True, env=env
        )
        if r.returncode != 0:
            # Branch doesn't exist — create an empty orphan branch
            print("    gh-pages branch doesn't exist, creating…")
            tmp.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init", "-b", "gh-pages"], cwd=tmp, check=True, env=env, capture_output=True)
            subprocess.run(["git", "remote", "add", "origin", clone_url], cwd=tmp, check=True, env=env, capture_output=True)
            # Need at least one commit to push
            (tmp / "index.html").write_text("<html><body><h1>Initial</h1></body></html>")
            subprocess.run(["git", "add", "."], cwd=tmp, check=True, env=env, capture_output=True)
            subprocess.run(
                ["git", "-c", "user.email=bot@local", "-c", "user.name=tw-invest-suite",
                 "commit", "-m", "init gh-pages"],
                cwd=tmp, check=True, env=env, capture_output=True
            )

        # 2. Copy reports/*.html + *.md to tmp (overwrite)
        for f in REPORTS_DIR.glob("*.html"):
            shutil.copy(f, tmp / f.name)
        for f in REPORTS_DIR.glob("*.md"):
            shutil.copy(f, tmp / f.name)
        # Also a simple index page linking to the latest
        latest_html = "market-screen-" + __import__("datetime").datetime.now().strftime("%Y-%m-%d") + ".html"
        index_html = f"""<!DOCTYPE html>
<html lang="zh-TW"><head><meta charset="UTF-8">
<title>tw-invest-suite · market screen reports</title>
<style>
body{{font-family:-apple-system,"Segoe UI","Microsoft JhengHei",sans-serif;
  max-width:900px;margin:2rem auto;padding:1rem;background:#0f1419;color:#e1e4e8;line-height:1.6;}}
h1{{color:#58a6ff}}a{{color:#58a6ff;text-decoration:none}}
a:hover{{text-decoration:underline}}li{{margin:0.5rem 0}}
.updated{{color:#8b949e;font-size:0.85rem}}
</style></head>
<body>
<h1>📊 tw-invest-suite · 市場掃描報告</h1>
<p class="updated">最後更新：{__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
<h2>最新報告</h2>
<ul>
  <li><a href="{latest_html}">📈 市場掃描（{latest_html}）</a> — HTML 互動報告</li>
  <li><a href="market-screen-{__import__('datetime').datetime.now().strftime('%Y-%m-%d')}.md">📄 市場掃描 Markdown</a></li>
  <li><a href="deep-dive-prompts-{__import__('datetime').datetime.now().strftime('%Y-%m-%d')}.md">🔬 Deep-dive prompts</a></li>
  <li><a href="watchlist-{__import__('datetime').datetime.now().strftime('%Y-%m-%d')}.md">👁️ Watchlist 追蹤</a></li>
</ul>
<h2>過往報告</h2>
<p>所有 HTML 在 <code>https://{REPO.split('/')[0]}.github.io/{REPO.split('/')[1]}/</code> 根目錄</p>
</body></html>"""
        (tmp / "index.html").write_text(index_html, encoding="utf-8")

        # 3. Commit + push
        subprocess.run(["git", "add", "."], cwd=tmp, check=True, env=env, capture_output=True)
        # Check if anything changed
        r = subprocess.run(["git", "diff", "--cached", "--stat"], cwd=tmp, capture_output=True, text=True, env=env)
        if not r.stdout.strip():
            print("    no changes to commit")
            return
        msg = f"update market screen reports {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}"
        subprocess.run(
            ["git", "-c", "user.email=bot@local", "-c", "user.name=tw-invest-suite",
             "commit", "-m", msg],
            cwd=tmp, check=True, env=env, capture_output=True
        )
        print("  Pushing to gh-pages…")
        r = subprocess.run(
            ["git", "push", "origin", "gh-pages", "--force"],
            cwd=tmp, capture_output=True, text=True, env=env
        )
        if r.returncode == 0:
            print("    ✓ pushed")
        else:
            print(f"    ❌ push failed: {r.stderr}")
            sys.exit(1)


def main():
    print("=== tw-invest-suite · publish to GitHub Pages ===\n")
    print(f"  Target: {REPO}")
    print(f"  Source: {REPORTS_DIR}\n")

    # 1. Enable Pages (idempotent)
    enable_pages()
    print()

    # 2. Publish via gh-pages branch
    publish_via_workflow()

    # 3. URL
    url = f"{PAGES_URL_BASE}/index.html"
    print(f"\n✅ Done. Public URL: {url}")
    print(f"   Latest report: {PAGES_URL_BASE}/market-screen-{__import__('datetime').datetime.now().strftime('%Y-%m-%d')}.html")
    print(f"\nNote: GitHub Pages may take 1-2 min to deploy the new commit.")


if __name__ == "__main__":
    main()
