"""build_ticker_meta.py — 從 yfinance cache 產出 tickers.json + chips-history-index.json
tickers.json 加 industry_zh / sector_zh / concept_categories 欄位給前端用
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

# 載入 concept-stocks.json 一次
CONCEPT_PATH = DATA_DIR / "concept-stocks.json"
TICKER_CONCEPTS = {}
if CONCEPT_PATH.exists():
    try:
        j = json.loads(CONCEPT_PATH.read_text(encoding="utf-8"))
        TICKER_CONCEPTS = j.get("ticker_to_concepts", {})
    except Exception:
        pass


def main():
    # tickers.json
    from report_inputs import load_inputs
    inputs = load_inputs()
    out = []
    for t, metadata in inputs['metadata'].items():
        ind_en = metadata['industry']
        sec_en = metadata['sector']
        tw_name_v = tw_name(t)
        ind_zh = resolve(t, ind_en, sec_en)
        sec_zh = zh_sector(sec_en)
        concepts = TICKER_CONCEPTS.get(t, [])
        out.append({
            "ticker": t,
            "name": metadata['name'],
            "date": inputs['date'],
            "sector": sec_en,
            "industry": ind_en,
            "sector_zh": sec_zh,
            "industry_zh": ind_zh,
            "concept_categories": concepts,
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
