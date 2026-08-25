#!/usr/bin/env python3
# Deploy public/ to gh-pages branch
import os
import shutil
import subprocess
import sys

REPO_DIR = r"C:\Users\icemo\Projects\tw-invest-suite"
# 用 timestamp 讓每次 deploy 都有新目錄（避免 git object lock 問題）
import time as _time
TMP_DIR = r"C:\Users\icemo\Projects\tw-invest-suite-ghpages-" + _time.strftime("%Y%m%d-%H%M%S")
PUBLIC_DIR = os.path.join(REPO_DIR, "public")
GH_PAGES_BRANCH = "gh-pages"
# analyze pages 是 render_only.py 產出，輸出在 Groove-Lab (1965 個 .html)
ANALYZE_SRC = r"C:\Groove-Lab\analyze"


def run(cmd, cwd=None, check=True):
    print(f"  $ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if r.stdout.strip():
        print(f"  stdout: {r.stdout.strip()[:500]}")
    if r.returncode != 0:
        print(f"  exit {r.returncode}: {(r.stderr or r.stdout)[:300]}")
    if check and r.returncode != 0:
        sys.exit(1)
    return r


# Step 1: Clean and create temp dir
print("=== Step 1: Create temp dir for gh-pages ===")
if os.path.exists(TMP_DIR):
    print(f"  Removing existing {TMP_DIR}")
    shutil.rmtree(TMP_DIR)
os.makedirs(TMP_DIR)
print(f"  Created: {TMP_DIR}")

# Step 2: git init + add remote
print("\n=== Step 2: git init + remote ===")
run(["git", "init", "-b", "main"], cwd=TMP_DIR)
run(["git", "remote", "add", "origin", "https://github.com/walterLiu168/tw-invest-suite.git"], cwd=TMP_DIR)

# Step 3: Copy public/* contents into temp dir (preserve hidden files like .nojekyll)
print("\n=== Step 3: Copy public/* to temp dir ===")
for item in os.listdir(PUBLIC_DIR):
    src = os.path.join(PUBLIC_DIR, item)
    dst = os.path.join(TMP_DIR, item)
    if os.path.isdir(src):
        shutil.copytree(src, dst)
        print(f"  dir: {item}")
    else:
        shutil.copy2(src, dst)
        print(f"  file: {item}")

# Step 3.5: Copy analyze/ pages (1965 HTML 來自 render_only.py → C:\Groove-Lab\analyze\)
print("\n=== Step 3.5: Copy analyze/ from Groove-Lab ===")
if os.path.isdir(ANALYZE_SRC):
    dst_analyze = os.path.join(TMP_DIR, "analyze")
    if os.path.isdir(dst_analyze):
        shutil.rmtree(dst_analyze)
    shutil.copytree(ANALYZE_SRC, dst_analyze)
    n = len([f for f in os.listdir(dst_analyze) if f.endswith(".html")])
    print(f"  analyze: {n} files from {ANALYZE_SRC}")
else:
    print(f"  [warn] {ANALYZE_SRC} not found, skip analyze/")
    if os.path.isdir(src):
        shutil.copytree(src, dst)
        print(f"  dir: {item}")
    else:
        shutil.copy2(src, dst)
        print(f"  file: {item}")

# Step 4: Add .nojekyll (so GitHub Pages doesn't try Jekyll processing)
print("\n=== Step 4: Add .nojekyll ===")
nojekyll = os.path.join(TMP_DIR, ".nojekyll")
with open(nojekyll, "w", encoding="utf-8") as f:
    f.write("")
print(f"  created: {nojekyll}")

# Step 5: git add + commit
print("\n=== Step 5: git add + commit ===")
run(["git", "add", "."], cwd=TMP_DIR)
run(["git", "config", "user.email", "walterLiu168@users.noreply.github.com"], cwd=TMP_DIR)
run(["git", "config", "user.name", "walterLiu168"], cwd=TMP_DIR)
run(["git", "commit", "-m", "Deploy GitHub Pages site from public/"], cwd=TMP_DIR)

# Step 6: Push to gh-pages branch
print("\n=== Step 6: Push to gh-pages branch ===")
run(["git", "push", "origin", "HEAD:gh-pages", "--force"], cwd=TMP_DIR)

print("\n=== Done! gh-pages branch pushed ===")
