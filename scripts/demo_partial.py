"""Demo: real TaiwanStockInfo (no token) + mock all other sections for 2330."""
import sys, os
from datetime import datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import finmind_client as fm
import analyze_stock as a

stock_id = "2330"

# Real info (no token needed)
all_info = fm.stock_info(stock_id)
real_info = [r for r in all_info if r.get("stock_id") == stock_id]
if not real_info:
    print(f"Could not find {stock_id} in TaiwanStockInfo")
    sys.exit(1)

# Build a dataset with real info + sensible mock for the rest
end = datetime.now()
start = (end - timedelta(days=365)).strftime("%Y-%m-%d")
end_s = end.strftime("%Y-%m-%d")

# Mock plausible data based on TSMC's known figures
mock_price = []
import random
random.seed(2330)
base = 950
for i in range(252):
    d = (end - timedelta(days=252 - i)).strftime("%Y-%m-%d")
    base += random.uniform(-15, 18)
    o = base + random.uniform(-5, 5)
    h = base + random.uniform(0, 12)
    l = base - random.uniform(0, 12)
    c = base + random.uniform(-3, 3)
    v = random.randint(15000, 40000)
    mock_price.append({
        "date": d, "open": round(o, 2), "max": round(h, 2),
        "min": round(l, 2), "close": round(c, 2),
        "Trading_Volume": v, "Trading_money": round(c * v * 1000, 0)
    })

mock_per = [{"date": end_s, "PER": 22.5, "PBR": 5.8}]
mock_dividend = [
    {"year": 2024, "cash_earnings_distribution": 4.0, "stock_earnings_distribution": 0, "stock_ex_dividend_date": "2025-06-15"},
    {"year": 2023, "cash_earnings_distribution": 3.5, "stock_earnings_distribution": 0, "stock_ex_dividend_date": "2024-06-15"},
    {"year": 2022, "cash_earnings_distribution": 3.0, "stock_earnings_distribution": 0, "stock_ex_dividend_date": "2023-06-15"},
]
mock_inst = []
for i in range(20):
    d = (end - timedelta(days=i)).strftime("%Y-%m-%d")
    mock_inst.extend([
        {"date": d, "name": "Foreign_Investor", "buy": random.randint(1000, 8000), "sell": random.randint(1000, 8000)},
        {"date": d, "name": "Investment_Trust", "buy": random.randint(100, 2000), "sell": random.randint(100, 2000)},
        {"date": d, "name": "Dealer", "buy": random.randint(50, 1500), "sell": random.randint(50, 1500)},
    ])

d = {
    "stock_id": stock_id,
    "info": real_info,
    "price": mock_price,
    "per": mock_per,
    "dividend": mock_dividend,
    "institutional": mock_inst,
    "news": [{"date": end_s, "title": "[demo] 真實新聞需要 FinMind token 才能抓", "source": "demo", "link": ""}],
    "shareholding": [],
    "financial": [],
    "balance_sheet": [],
    "fetch_errors": ["price/per/dividend/institutional/news 為 demo mock 資料（因 FinMind token 尚未提供）"],
}

md = a.build_report(d)
out = os.path.expanduser(f"~/.claude/skills/tw-invest-suite/reports/demo/{stock_id}-partial-demo.md")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    f.write(md)
print(f"Saved partial demo: {out}")
print(f"Length: {len(md)} chars")
print()
print("Real company info found:")
for k, v in real_info[0].items():
    print(f"  {k}: {v}")
