"""build_ticker_meta.py — 從 yfinance cache 產出 tickers.json + chips-history-index.json"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_cache")
DATA_DIR = ROOT / "public" / "data"
HIST_DIR = DATA_DIR / "chips-history"


def main():
    # tickers.json
    out = []
    for f in CACHE.glob("*.json"):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        yf = (j.get("yfinance") or {}).get("data") or {}
        if not yf:
            continue
        out.append({
            "ticker": f.stem,
            "name": yf.get("longName") or f.stem,
            "sector": yf.get("sector") or "",
            "industry": yf.get("industry") or "",
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
