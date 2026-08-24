"""generate_og.py — 每日 OG 圖 1200x630
從 watchlist.html parse 24 檔精選，畫成 1200x630 圖卡
台股色：紅=漲/正，綠=跌/負 (D026)
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Pillow not installed. Run: pip install Pillow", file=sys.stderr)
    sys.exit(1)

# 顏色（與 readme.html / sectors.html 一致，深底）
BG = (10, 14, 26)         # #0a0e1a
PANEL = (19, 27, 46)      # #131b2e
PANEL2 = (26, 36, 64)     # #1a2440
BORDER = (31, 41, 66)     # #1f2942
INK = (230, 236, 245)     # #e6ecf5
MUTED = (138, 160, 192)   # #8aa0c0
ACC = (95, 177, 255)      # #5fb1ff
CYAN = (57, 197, 207)     # #39c5cf
PURPLE = (188, 140, 255)  # #bc8cff
# D026 台股色
RED = (236, 112, 99)      # #ec7063 漲/正
GREEN = (88, 214, 141)    # #58d68d 跌/負
AMBER = (245, 176, 65)    # #f5b041

W, H = 1200, 630

# 字型（用 Windows 內建）
F_BOLD = "C:/Windows/Fonts/msjhbd.ttc"
F_REG = "C:/Windows/Fonts/msjh.ttc"
F_MONO = "C:/Windows/Fonts/consola.ttf"


def font(size, bold=True, mono=False):
    if mono:
        return ImageFont.truetype(F_MONO, size)
    # Pillow 12 在 Windows 上對 .ttc 預設 index 是 0（拿 Microsoft JhengHei），
    # index=1 拿 JhengHei UI — 兩者字集相同，都能完整渲染繁體中文。
    # emoji 仍缺（emoji 不在任何 CJK 字型裡），所以 OG 文字中要避免 emoji
    return ImageFont.truetype(F_BOLD if bold else F_REG, size, index=1)


def parse_watchlist(html_path: Path):
    """從 watchlist.html parse 出所有 pick 資料
    兩種結構：
    1) <div class="pick">...<span class="pick-ticker">... (margin 區)
    2) <div class="pick-head long/short">...<span class="pick-ticker">... (price-bucket 區)
    """
    html = html_path.read_text(encoding="utf-8")
    picks = []

    # --- 結構 1: <div class="pick"> margin 區塊 ---
    pick_blocks = re.findall(
        r'<div class="pick">\s*<div class="pick-head">(.*?)<div class="pick-grid">(.*?)<div class="pick-meta',
        html, re.DOTALL,
    )
    for head, grid in pick_blocks:
        m = re.search(r'<span class="pick-ticker">(\d+)</span>', head)
        if not m:
            continue
        ticker = m.group(1)
        m = re.search(r'<span class="pick-name">([^<]+)</span>', head)
        name = m.group(1).strip() if m else ""
        m = re.search(r'<span class="pick-industry[^"]*">([^<]+)</span>', head)
        industry = m.group(1).strip() if m else ""
        cells = re.findall(r'<div class="k">([^<]+)</div>\s*<div class="v[^"]*">([^<]+)</div>', grid)
        price = chg = maint = ""
        for k, v in cells:
            k = k.strip(); v = v.strip()
            if k == "收盤":
                price = v
            elif "跌幅" in k or "漲幅" in k:
                chg = v
            elif "維持率" in k:
                maint = v
        picks.append({
            "ticker": ticker, "name": name, "industry": industry,
            "price": price, "chg_pct": chg, "margin_maint": maint,
            "horizon": "margin", "tags": [],
        })

    # --- 結構 2: <div class="pick-head long/short"> price-bucket 區塊 ---
    head_blocks = re.findall(
        r'<div class="pick-head (long|short)">(.*?)(?=<div class="pick-head (?:long|short)">|</main>)',
        html, re.DOTALL,
    )
    for horizon, body in head_blocks:
        m = re.search(r'<span class="pick-ticker">(\d+)</span>', body)
        if not m:
            continue
        ticker = m.group(1)
        m = re.search(r'<span class="pick-name">([^<]+)</span>', body)
        name = m.group(1).strip() if m else ""
        # industry
        m = re.search(r'>([^<>·]+)業\s*·\s*市值', body)
        industry = m.group(1).strip() + "業" if m else ""
        # price + chg
        m = re.search(r'<div class="pick-price [^"]*">([^<]+)\s*<span[^>]*>([^<]+)</span>', body)
        price = m.group(1).strip() if m else ""
        chg = m.group(2).strip() if m else ""
        # tags
        tags = re.findall(r'<span class="tag tag-(\w+)[^"]*">([^<]+)</span>', body)
        tag_texts = [t[1] for t in tags[:4]]
        picks.append({
            "ticker": ticker, "name": name, "industry": industry,
            "price": price, "chg_pct": chg, "margin_maint": "",
            "horizon": horizon, "tags": tag_texts,
        })

    return picks


def draw_text_centered(draw, xy, text, fnt, fill):
    """中英混排：簡單用 getbbox 量寬度"""
    bbox = draw.textbbox((0, 0), text, font=fnt)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    x, y = xy
    draw.text((x - w // 2, y - h // 2), text, font=fnt, fill=fill)


def draw_pick_card(draw, x, y, w, h, pick, accent):
    """畫一個 pick 卡片"""
    # 卡片底
    draw.rounded_rectangle([x, y, x + w, y + h], radius=14, fill=PANEL, outline=BORDER, width=2)
    # 左側 accent 條
    draw.rectangle([x, y, x + 4, y + h], fill=accent)
    # ticker + name
    pad = 16
    draw.text((x + pad, y + 12), pick["ticker"], font=font(28, bold=True, mono=True), fill=ACC)
    # name
    name = pick["name"][:10]  # 避免太長
    draw.text((x + pad, y + 50), name, font=font(20, bold=False), fill=INK)
    # industry
    ind = pick.get("industry", "")[:16]
    if ind:
        draw.text((x + pad, y + 78), ind, font=font(13), fill=MUTED)
    # 右側 price
    price = pick.get("price", "")
    if price:
        bbox = draw.textbbox((0, 0), price, font=font(26, bold=True, mono=True))
        pw = bbox[2] - bbox[0]
        draw.text((x + w - pad - pw, y + 12), price, font=font(26, bold=True, mono=True), fill=INK)
    # 漲跌
    chg = pick.get("chg_pct", "")
    if chg:
        # D026: 紅=漲/正, 綠=跌/負
        is_pos = chg.startswith("+") or ("負" not in chg and "−" not in chg and "-" not in chg)
        # 但 "%" 前面若是負號 → 負
        if "-" in chg or "−" in chg or "跌" in chg or "下" in chg:
            is_pos = False
        if "+" in chg or "漲" in chg or "上" in chg:
            is_pos = True
        color = RED if is_pos else (GREEN if chg else INK)
        bbox = draw.textbbox((0, 0), chg, font=font(18, bold=True, mono=True))
        cw = bbox[2] - bbox[0]
        draw.text((x + w - pad - cw, y + 50), chg, font=font(18, bold=True, mono=True), fill=color)
    # margin maint (if present)
    maint = pick.get("margin_maint", "")
    if maint:
        draw.text((x + pad, y + 100), f"維持率 {maint}", font=font(15, bold=True, mono=True), fill=AMBER)
    # tags
    tags = pick.get("tags", [])[:3]
    tx = x + pad
    ty = y + h - 30
    for t in tags:
        bbox = draw.textbbox((0, 0), t, font=font(12))
        tw = bbox[2] - bbox[0] + 12
        draw.rounded_rectangle([tx, ty, tx + tw, ty + 22], radius=6, fill=PANEL2, outline=BORDER, width=1)
        draw.text((tx + 6, ty + 3), t, font=font(12), fill=INK)
        tx += tw + 6


def draw_pick_row(draw, x, y, w, h, pick, idx):
    """畫單行 pick（用於第二區）"""
    draw.rounded_rectangle([x, y, x + w, y + h], radius=8, fill=PANEL, outline=BORDER, width=1)
    # idx badge
    draw.ellipse([x + 8, y + h // 2 - 12, x + 32, y + h // 2 + 12], fill=ACC)
    draw.text((x + 14, y + h // 2 - 10), str(idx), font=font(14, bold=True, mono=True), fill=BG)
    # ticker
    draw.text((x + 44, y + 6), pick["ticker"], font=font(18, bold=True, mono=True), fill=ACC)
    # name
    name = pick["name"][:10]
    draw.text((x + 130, y + 10), name, font=font(13), fill=INK)
    # industry
    ind = pick.get("industry", "")[:10]
    if ind:
        draw.text((x + 230, y + 10), ind, font=font(12), fill=MUTED)
    # price (右側)
    price = pick.get("price", "")
    if price:
        bbox = draw.textbbox((0, 0), price, font=font(15, bold=True, mono=True))
        pw = bbox[2] - bbox[0]
        draw.text((x + w - 200 - pw, y + 6), price, font=font(15, bold=True, mono=True), fill=INK)
    # 漲跌
    chg = pick.get("chg_pct", "")
    if chg:
        is_pos = "+" in chg or "漲" in chg
        is_neg = "-" in chg or "−" in chg or "跌" in chg
        color = RED if is_pos else (GREEN if is_neg else INK)
        draw.text((x + w - 90, y + 6), chg, font=font(15, bold=True, mono=True), fill=color)


def render_og(picks, out_path: Path, date_str: str):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # 背景：漸層
    for y in range(H):
        c = (
            int(BG[0] + (PANEL[0] - BG[0]) * y / H * 0.5),
            int(BG[1] + (PANEL[1] - BG[1]) * y / H * 0.5),
            int(BG[2] + (PANEL[2] - BG[2]) * y / H * 0.5),
        )
        d.line([(0, y), (W, y)], fill=c)

    # === Header (y: 0-80) ===
    # 左：logo + 標題
    d.text((40, 22), "tw-invest-suite", font=font(22, bold=True), fill=ACC)
    d.text((40, 52), f"台股深度選股 · {date_str}", font=font(18), fill=INK)
    # 右：日期 + 統計
    d.text((W - 380, 22), f"{date_str}", font=font(16, mono=True), fill=MUTED)
    d.text((W - 380, 48), f"{len(picks)} 檔精選", font=font(16, bold=True), fill=CYAN)
    # 分隔線
    d.line([(0, 80), (W, 80)], fill=BORDER, width=1)

    # === Top 3 大卡片 (y: 100-280, h=180) ===
    if len(picks) >= 3:
        card_w = (W - 80 - 20) // 3  # 3 張卡片，gap 10
        for i, p in enumerate(picks[:3]):
            x = 40 + i * (card_w + 10)
            accent = ACC if i == 0 else (CYAN if i == 1 else PURPLE)
            draw_pick_card(d, x, 100, card_w, 180, p, accent)

    # === 中段說明 (y: 300-340) ===
    d.text((40, 305), "今日焦點 24 檔精選（剩餘 6 檔）", font=font(15, bold=True), fill=AMBER)
    d.line([(0, 340), (W, 340)], fill=BORDER, width=1)

    # === 後 6 個 pick (y: 360-560, 6 行 × ~32px) ===
    if len(picks) > 3:
        row_h = 30
        row_gap = 4
        for i, p in enumerate(picks[3:9]):
            y = 360 + i * (row_h + row_gap)
            draw_pick_row(d, 40, y, W - 80, row_h, p, i + 4)

    # === Footer (y: 580-630) ===
    d.line([(0, 580), (W, 580)], fill=BORDER, width=1)
    d.text((40, 600), "walterliu168.github.io/tw-invest-suite", font=font(15, mono=True), fill=ACC)
    d.text((W - 530, 600), "18 大師 · 9 型態 · 1,962 檔", font=font(15), fill=MUTED)
    d.text((W - 250, 600), "每日 22:25 自動更新", font=font(13), fill=MUTED)

    img.save(out_path, "PNG", optimize=True)
    print(f"[og] wrote {out_path} ({out_path.stat().st_size // 1024} KB)")


def main():
    if len(sys.argv) < 3:
        print("Usage: python generate_og.py <watchlist.html> <out.png>")
        sys.exit(1)
    html = Path(sys.argv[1])
    out = Path(sys.argv[2])
    out.parent.mkdir(parents=True, exist_ok=True)
    # 從 html 標題或檔名取日期
    m = re.search(r"(\d{4}-\d{2}-\d{2})", html.read_text(encoding="utf-8")[:1000])
    date_str = m.group(1) if m else datetime.now().strftime("%Y-%m-%d")
    picks = parse_watchlist(html)
    print(f"[parse] {len(picks)} picks from {html.name}")
    if not picks:
        print("[err] no picks parsed", file=sys.stderr)
        sys.exit(1)
    render_og(picks, out, date_str)


if __name__ == "__main__":
    main()
