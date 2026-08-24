"""fetch_tw_industry.py — 抓 FinMind TaiwanStockInfo 拿官方 48 個產業分類
存成 public/data/tw-industry.json
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
SKILL_DIR = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite")
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import finmind_client as fm  # noqa: E402

OUT = ROOT / "public" / "data" / "tw-industry.json"


def main():
    t0 = time.time()
    print(f"[start] {datetime.now():%Y-%m-%d %H:%M:%S}", file=sys.stderr)
    # 1 call 拿全市場 (3560 列)
    rows = fm.query("TaiwanStockInfo", stock_id="", start_date="", end_date="")
    print(f"[fetch] {len(rows)} rows", file=sys.stderr)
    by_ticker = {}
    by_industry = {}
    skipped = 0
    for r in rows:
        t = str(r.get("stock_id", "")).strip()
        ind = r.get("industry_category", "") or ""
        name = r.get("stock_name", "") or ""
        if not t:
            skipped += 1
            continue
        by_ticker[t] = {"name": name, "industry": ind}
        by_industry[ind] = by_industry.get(ind, 0) + 1
    out = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "total": len(by_ticker),
        "industry_count": len(by_industry),
        "by_ticker": by_ticker,
        "by_industry": dict(sorted(by_industry.items(), key=lambda x: -x[1])),
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] {time.time()-t0:.1f}s  {len(by_ticker)} tickers  {len(by_industry)} industries", file=sys.stderr)
    print(f"  -> {OUT}  ({OUT.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
