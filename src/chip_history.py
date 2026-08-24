"""chip_history.py — 每日備份最近 30 日的籌碼資料
產出 public/data/chips-history/{date}.json
每個檔案包含該日所有 ticker 的法人買賣超 (股)
"""
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite")
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import finmind_client as fm  # noqa: E402

OUT_DIR = ROOT / "public" / "data" / "chips-history"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# 抓 35 個日曆日 cover 30 個交易日
CAL_DAYS = 35
DAILY_KEEP = 30  # 留 30 個交易日


def fetch_daily(days_back):
    """一次抓 1 天全市場法人"""
    d = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    out = OUT_DIR / f"{d}.json"
    if out.exists():
        # 24 小時內不再重抓
        age_h = (datetime.now().timestamp() - out.stat().st_mtime) / 3600
        if age_h < 24:
            print(f"[skip] {d} ({age_h:.1f}h old)", file=sys.stderr)
            return
    try:
        rows = fm.stock_institutional(stock_id="", start_date=d, end_date=d)
    except Exception as e:
        print(f"[err] {d} {e}", file=sys.stderr)
        return
    if not rows:
        print(f"[empty] {d}", file=sys.stderr)
        return
    # 整理 per ticker 5 法人分項
    by = {}
    for r in rows:
        t = str(r.get("stock_id", "")).strip()
        cat = r.get("name", "")
        if not t or cat not in ("Foreign_Investor", "Investment_Trust", "Dealer_self", "Dealer_Hedging"):
            continue
        try:
            net = float(r.get("buy") or 0) - float(r.get("sell") or 0)
        except (TypeError, ValueError):
            continue
        slot = by.setdefault(t, {"f": 0.0, "t": 0.0, "d": 0.0})
        if cat == "Foreign_Investor":
            slot["f"] = net
        elif cat == "Investment_Trust":
            slot["t"] = net
        elif cat in ("Dealer_self", "Dealer_Hedging"):
            slot["d"] += net
    out.write_text(json.dumps({"date": d, "tickers": by}, ensure_ascii=False), encoding="utf-8")
    print(f"[ok] {d} {len(by)} tickers", file=sys.stderr)


def main():
    t0 = time.time()
    for offset in range(0, CAL_DAYS):
        fetch_daily(offset)
        time.sleep(0.5)
    # 刪掉 30 天前的
    files = sorted(OUT_DIR.glob("*.json"), key=lambda p: p.stem)
    for old in files[:-DAILY_KEEP]:
        old.unlink()
        print(f"[rm] {old.name}", file=sys.stderr)
    print(f"[done] {time.time()-t0:.1f}s  kept {len(list(OUT_DIR.glob('*.json')))} files", file=sys.stderr)


if __name__ == "__main__":
    main()
