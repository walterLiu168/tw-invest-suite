"""build_ticker_meta.py — 從 yfinance cache 產出 tickers.json + chips-history-index.json
tickers.json 加 industry_zh / sector_zh 欄位給前端用
優先用 TWSE 官方 48 分類（tw-industry.json），yfinance fallback
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
CACHE = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_cache")
DATA_DIR = ROOT / "public" / "data"
HIST_DIR = DATA_DIR / "chips-history"

from industry_zh import zh_industry, zh_sector, tw_industry, tw_name, resolve  # noqa: E402


def main():
    # tickers.json
    out = []
    for f in CACHE.glob("*.json"):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        t = f.stem
        yf = (j.get("yfinance") or {}).get("data") or {}
        if not yf:
            continue
        ind_en = yf.get("industry") or ""
        sec_en = yf.get("sector") or ""
        # 優先用 TWSE 中文名 / 分類
        tw_name_v = tw_name(t)
        ind_zh = resolve(t, ind_en, sec_en)
        sec_zh = zh_sector(sec_en)
        out.append({
            "ticker": t,
            "name": tw_name_v or yf.get("longName") or t,  # 中文名優先
            "sector": sec_en,
            "industry": ind_en,
            "sector_zh": sec_zh,
            "industry_zh": ind_zh,
        })
    out.sort(key=lambda x: x["ticker"])
    p = DATA_DIR / "tickers.json"
    p.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"[tickers] {p}  ({len(out)} entries, {p.stat().st_size//1024} KB)")

    # chips-history-index.json
    dates = sorted([f.stem for f in HIST_DIR.glob("*.json")])
    p2 = DATA_DIR / "chips-history-index.json"
    p2.write_text(json.dumps({"dates": dates, "count": len(dates)}, ensure_ascii=False), encoding="utf-8")
    print(f"[history-index] {p2}  ({len(dates)} dates)")


if __name__ == "__main__":
    main()
