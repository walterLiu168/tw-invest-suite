# 部署指南

## 方式 1: GitHub Pages

### 一次性設定
```powershell
# 1. 建立 repo
gh repo create walterLiu168/tw-invest-suite --public --source=. --remote=origin

# 2. 推上去
git add -A
git commit -m "Initial commit"
git push -u origin main

# 3. 啟用 Pages
#   https://github.com/walterLiu168/tw-invest-suite/settings/pages
#   Source: Deploy from a branch
#   Branch: main, /public
```

### 之後更新
```powershell
.\scripts\publish_analyze_ghpages.ps1
```

## 方式 2: groovelab.dev

直接 file serve，從 `C:\Groove-Lab\` 對外。

不需要 build step。

## 方式 3: 純本地（debug）

直接瀏覽 `C:\Groove-Lab\analyze\2330.html` 即可。

## 注意事項

1. **1,962 個 HTML 不進 git**（見 `.gitignore`），只在本地 render 後 deploy
2. **Cache 也不進 git**（在 `~/.cache_manager/`）
3. **DB 是 localhost**，deploy 前不需要改設定
4. **不要把 FinMind token commit 進 git**（放 `~/.finmind_token`）
