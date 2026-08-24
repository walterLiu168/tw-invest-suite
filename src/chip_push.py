"""chip_push.py — 籌碼異動 Telegram 推播 (P3.3)
讀 chips.json + chips-advanced.json → 組合成盤後推播
門檻：
  - 土洋同買/同賣 (5d ≥ 0.5 億)
  - 外資連買/連賣 ≥ 3 天 且 5d 累計 ≥ 5 億
  - 現價 vs 法人 20 日均價 折溢價 ≥ 5% (雷達)
發送：Telegram bot (需 TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID env)
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "public" / "data"
CHIPS = DATA / "chips.json"
ADVANCED = DATA / "chips-advanced.json"
LOG = ROOT / "outputs" / "chip-push.log"
LOG.parent.mkdir(parents=True, exist_ok=True)

# Telegram 設定
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()


def compose_message():
    """組合成 Telegram 訊息 (HTML format)"""
    if not CHIPS.exists() or not ADVANCED.exists():
        return None, "no chips data"
    chips = json.loads(CHIPS.read_text(encoding="utf-8"))
    adv = json.loads(ADVANCED.read_text(encoding="utf-8"))

    today = chips["date"]
    lines = [f"<b>📡 tw-invest-suite 籌碼異動</b>  ·  {today}"]

    # 1. 土洋同買 (前 5)
    sb = chips["tabs"]["same_buy"][:5]
    if sb:
        lines.append("\n<b>🔥 土洋同買 (5d ≥ 0.5 億)</b>")
        for p in sb:
            f_twd = p.get("f_5d_twd") or 0
            t_twd = p.get("t_5d_twd") or 0
            lines.append(f"  <code>{p['ticker']}</code> {p['name'][:14]}  外資 {f_twd:+.1f} 投信 {t_twd:+.1f} 億")

    # 2. 土洋同賣 (前 5)
    ss = chips["tabs"]["same_sell"][:5]
    if ss:
        lines.append("\n<b>💧 土洋同賣 (5d ≥ 0.5 億)</b>")
        for p in ss:
            f_twd = p.get("f_5d_twd") or 0
            t_twd = p.get("t_5d_twd") or 0
            lines.append(f"  <code>{p['ticker']}</code> {p['name'][:14]}  外資 {f_twd:+.1f} 投信 {t_twd:+.1f} 億")

    # 3. 外資連買 ≥ 3 天 且 5d 累計 ≥ 5 億 (從 chips + adv 取)
    feats = {f["ticker"]: f for f in adv["features"]}
    consec_buy = [p for p in chips["tabs"]["f_consec_buy"] if p["f_streak"] >= 3]
    big_buy = [p for p in consec_buy if feats.get(p["ticker"], {}).get("cum_5d_shares", 0) > 500_000]  # 50 萬股 = 5 億(假設 100元)
    big_buy = sorted(big_buy, key=lambda x: -feats.get(x["ticker"], {}).get("cum_5d_shares", 0))[:5]
    if big_buy:
        lines.append(f"\n<b>📈 外資連買 ≥ 3 天 + 5d 大單</b>")
        for p in big_buy:
            cum = feats.get(p["ticker"], {}).get("cum_5d_shares", 0)
            cum_twd = (cum * (feats.get(p["ticker"], {}).get("price", 0))) / 1e8
            lines.append(f"  <code>{p['ticker']}</code> {p['name'][:14]}  連買 {p['f_streak']} 天 5d {cum_twd:+.1f} 億")

    # 4. 法人 20 日均價 折溢價 ≥ 5% (前 5)
    below = sorted([x for x in adv["features"] if (x.get("vs_vwap_pct") or 0) <= -5], key=lambda x: x.get("vs_vwap_pct") or 0)[:3]
    above = sorted([x for x in adv["features"] if (x.get("vs_vwap_pct") or 0) >= 5], key=lambda x: -(x.get("vs_vwap_pct") or 0))[:3]
    if below:
        lines.append(f"\n<b>⬇️ 現價 < 法人 20 日 VWAP (折價 ≥ 5%)</b>")
        for p in below:
            lines.append(f"  <code>{p['ticker']}</code> {p['name'][:14]}  收 {p['price']:.0f}  折 {p['vs_vwap_pct']:+.1f}%")
    if above:
        lines.append(f"\n<b>⬆️ 現價 > 法人 20 日 VWAP (溢價 ≥ 5%)</b>")
        for p in above:
            lines.append(f"  <code>{p['ticker']}</code> {p['name'][:14]}  收 {p['price']:.0f}  溢 {p['vs_vwap_pct']:+.1f}%")

    lines.append(f"\n<a href=\"https://walterliu168.github.io/tw-invest-suite/chips-advanced.html\">查看完整籌碼進階 →</a>")
    lines.append(f"<a href=\"https://walterliu168.github.io/tw-invest-suite/chips.html\">查看籌碼排行 →</a>")
    return "\n".join(lines), None


def send_telegram(text):
    """送 Telegram"""
    if not BOT_TOKEN or not CHAT_ID:
        return False, "no bot_token/chat_id"
    import httpx
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        r = httpx.post(url, json={
            "chat_id": CHAT_ID, "text": text, "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=20.0)
        if r.is_success:
            return True, "ok"
        return False, r.text[:200]
    except Exception as e:
        return False, str(e)


def main():
    text, err = compose_message()
    if not text:
        print(f"[err] {err}", file=sys.stderr)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] ERR: {err}\n")
        return 1
    # 寫 log（不論送不送）
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}]\n{text}\n\n")
    if BOT_TOKEN and CHAT_ID:
        ok, msg = send_telegram(text)
        print(f"[telegram] {ok} {msg}", file=sys.stderr)
        return 0 if ok else 2
    else:
        print(f"[skip telegram] no bot_token/chat_id — message logged to {LOG}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
