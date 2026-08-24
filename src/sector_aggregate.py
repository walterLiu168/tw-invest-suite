"""板塊輪動 — 把 1,962 檔依產業 (yfinance industry) 加總
產出:
  public/data/sectors.json
  public/sectors.html
"""
import json
import os
import statistics
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
# 22:25 batch 工作目錄 (cache + finmind_client 都在這)
SKILL_DIR = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite")
SCRIPTS_DIR = SKILL_DIR / "scripts"
CACHE_DIR = SCRIPTS_DIR / "_cache"
sys.path.insert(0, str(SCRIPTS_DIR))

import finmind_client as fm  # noqa: E402
from industry_zh import zh_industry, resolve  # noqa: E402

PUBLIC_DIR = ROOT / "public"
DATA_DIR = PUBLIC_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 跳過 PE 異常值：負值或 > 200（金融股/虧損股會把中位數拉歪）
PE_MAX = 200.0
PE_MIN = 0.0
# 跳過市值過小（殼股會拉動法人買賣超）
MKT_CAP_MIN = 500_000_000  # 5 億

# 大類別 fallback 用的 rough 中文 mapping
INDUSTRY_ZH = {
    "Basic Materials": "原物料",
    "Communication Services": "通訊服務",
    "Consumer Cyclical": "消費循環",
    "Consumer Defensive": "消費防禦",
    "Energy": "能源",
    "Financial Services": "金融服務",
    "Healthcare": "醫療保健",
    "Industrials": "工業",
    "Real Estate": "不動產",
    "Technology": "科技",
    "Utilities": "公用事業",
}


def load_ticker_metadata():
    """讀 1962 個 cache 檔，產出 ticker → (name, sector, industry, mkt_cap, pe, pe_src)"""
    meta = {}
    skipped = 0
    for f in CACHE_DIR.glob("*.json"):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            skipped += 1
            continue
        t = f.stem
        yf = (j.get("yfinance") or {}).get("data") or {}
        fp = (j.get("finmind_pe") or {}).get("data") or {}
        name = yf.get("longName") or t
        sector = yf.get("sector") or ""
        industry = yf.get("industry") or sector or "未分類"
        mkt_cap = yf.get("marketCap") or 0
        # PE 優先用 FinMind（P/E 來自月報較準），yfinance fallback
        pe = fp.get("PER")
        if pe is None or pe <= 0:
            pe = yf.get("trailingPE")
        meta[t] = {
            "name": name,
            "sector": sector,
            "industry": industry,
            "mkt_cap": float(mkt_cap) if mkt_cap else 0.0,
            "pe": float(pe) if pe and pe > PE_MIN else None,
        }
    print(f"[meta] {len(meta)} tickers loaded, {skipped} skipped", file=sys.stderr)
    return meta


def compute_revenue_yoy(meta):
    """讀 finmind_month，算每檔的最近月營收 YoY %。
    回傳 ticker → yoy_pct (float or None)"""
    yoy = {}
    for f in CACHE_DIR.glob("*.json"):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        t = f.stem
        rows = ((j.get("finmind_month") or {}).get("data")) or []
        if not rows or len(rows) < 13:
            yoy[t] = None
            continue
        # 排序（最新在前）
        rows = sorted(rows, key=lambda r: r.get("date", ""), reverse=True)
        latest = rows[0]
        latest_amt = latest.get("revenue") or 0
        latest_year = latest.get("revenue_year")
        latest_month = latest.get("revenue_month")
        if not latest_year or not latest_month or not latest_amt:
            yoy[t] = None
            continue
        # 找去年同月
        target = (latest_year - 1, latest_month)
        prev_ym = None
        for r in rows[1:]:
            if (r.get("revenue_year"), r.get("revenue_month")) == target:
                prev_ym = r
                break
        if not prev_ym or not prev_ym.get("revenue"):
            yoy[t] = None
            continue
        prev_amt = prev_ym["revenue"]
        if prev_amt <= 0:
            yoy[t] = None
        else:
            yoy[t] = (latest_amt - prev_amt) / prev_amt * 100.0
    print(f"[yoy] computed for {sum(1 for v in yoy.values() if v is not None)} tickers", file=sys.stderr)
    return yoy


def fetch_institutional_5d(meta):
    """抓近 5 個交易日的 TaiwanStockInstitutionalInvestorsBuySell
    FinMind quirk：stock_id 空字串時只回傳單日資料，所以每天要單獨打一次
    總共 7 次（涵蓋 7 個日曆日），抓非空回應裡最新的 5 個交易日
    """
    all_rows = []
    today = datetime.now()
    # 試最近 9 個日曆日
    for offset in range(0, 9):
        d = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        try:
            rows = fm.stock_institutional(stock_id="", start_date=d, end_date=d)
        except Exception as e:
            print(f"[inst] {d} ERR: {e}", file=sys.stderr)
            continue
        if rows:
            print(f"[inst] {d} {len(rows)} rows", file=sys.stderr)
            all_rows.extend(rows)
        # rate-limit
        time.sleep(0.5)

    # 用 (ticker, date) 為 key 存 3 法人淨買超 (股)
    by_ticker_date = {}
    dates = set()
    for r in all_rows:
        t = str(r.get("stock_id", "")).strip()
        d = r.get("date", "")
        cat = r.get("name", "")
        if not t or not d or not cat:
            continue
        dates.add(d)
        key = (t, d)
        b = r.get("buy") or 0
        s_v = r.get("sell") or 0
        try:
            net = float(b) - float(s_v)
        except (TypeError, ValueError):
            continue
        slot = by_ticker_date.setdefault(key, {"f": 0.0, "t": 0.0, "d": 0.0})
        if cat == "Foreign_Investor":
            slot["f"] = net
        elif cat == "Investment_Trust":
            slot["t"] = net
        elif cat in ("Dealer_self", "Dealer_Hedging"):
            slot["d"] += net
        # Foreign_Dealer_Self / "Dealer" (legacy) 略過

    sorted_dates = sorted(dates, reverse=True)[:5]
    print(f"[inst] using dates: {sorted_dates}", file=sys.stderr)

    inst5 = {}
    for t in set(k[0] for k in by_ticker_date.keys()):
        f = t_v = d_v = 0.0
        for d in sorted_dates:
            v = by_ticker_date.get((t, d))
            if v is None:
                continue
            f += v["f"]
            t_v += v["t"]
            d_v += v["d"]
        inst5[t] = {
            "foreign_5d_shares": f,
            "trust_5d_shares": t_v,
            "dealer_5d_shares": d_v,
            "three_net_5d_shares": f + t_v + d_v,
        }
    print(f"[inst5] computed for {len(inst5)} tickers", file=sys.stderr)
    return inst5, sorted_dates


def aggregate(meta, yoy, inst5):
    """依 industry 加總 (股 → 張)
    注意：法人加總用全市場（含小股本），不過 mkt_cap 過濾
    （小股本也可能被法人砍/拉，列入才是真實全貌）
    """
    by_industry = {}
    for t, m in meta.items():
        ind = m["industry"] or "未分類"
        by_industry.setdefault(ind, []).append(t)  # 仍用英文 group，但顯示用中文
    sectors = []
    skipped_pe = 0
    for ind, tickers in by_industry.items():
        f_sum = t_sum = d_sum = 0.0
        f_n = t_n = d_n = 0
        for t in tickers:
            v = inst5.get(t)
            if not v:
                continue
            f_sum += v["foreign_5d_shares"]; f_n += 1
            t_sum += v["trust_5d_shares"]; t_n += 1
            d_sum += v["dealer_5d_shares"]; d_n += 1
        # 轉成「張」(÷1000)
        three_net = (f_sum + t_sum + d_sum) / 1000.0 if (f_n and t_n and d_n) else None
        f_lots = f_sum / 1000.0 if f_n else None
        t_lots = t_sum / 1000.0 if t_n else None
        d_lots = d_sum / 1000.0 if d_n else None

        # PE 中位數
        pes = [meta[t]["pe"] for t in tickers if meta[t]["pe"] is not None and meta[t]["pe"] < PE_MAX]
        pe_med = statistics.median(pes) if pes else None
        if not pes:
            skipped_pe += 1

        # 月營收 YoY 中位數
        yoys = [yoy[t] for t in tickers if yoy.get(t) is not None]
        yoy_med = statistics.median(yoys) if yoys else None

        # 總市值（只算有 mkt_cap 的）
        mkt_cap = sum(meta[t]["mkt_cap"] for t in tickers if meta[t]["mkt_cap"] > 0)

        # 代表股：mkt_cap 最大；都沒就取第一個
        with_cap = [t for t in tickers if meta[t]["mkt_cap"] > 0]
        lead = max(with_cap, key=lambda t: meta[t]["mkt_cap"]) if with_cap else (tickers[0] if tickers else None)

        sectors.append({
            "industry": ind,
            "industry_zh": resolve(tickers[0], ind, meta[tickers[0]].get("sector", "") if tickers else "") if tickers else zh_industry(ind),
            "count": len(tickers),
            "lead_ticker": lead,
            "lead_name": meta[lead]["name"] if lead else "",
            "mkt_cap_total": mkt_cap,
            "foreign_5d_lots": round(f_lots, 0) if f_lots is not None else None,
            "trust_5d_lots": round(t_lots, 0) if t_lots is not None else None,
            "dealer_5d_lots": round(d_lots, 0) if d_lots is not None else None,
            "three_net_5d_lots": round(three_net, 0) if three_net is not None else None,
            "pe_median": round(pe_med, 2) if pe_med else None,
            "yoy_median_pct": round(yoy_med, 2) if yoy_med else None,
        })
    sectors.sort(key=lambda s: (s["three_net_5d_lots"] or 0) * -1)
    print(f"[agg] {len(sectors)} industries, {skipped_pe} have no PE", file=sys.stderr)
    return sectors


def write_json(sectors, dates):
    out = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "trading_dates_5d": dates,
        "industry_count": len(sectors),
        "ticker_count_total": sum(s["count"] for s in sectors),
        "sectors": sectors,
    }
    p = DATA_DIR / "sectors.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[json] wrote {p}", file=sys.stderr)
    return out


def fmt_lots(n):
    """法人買賣超以「張」為單位"""
    if n is None:
        return "—"
    sign = "+" if n > 0 else ("−" if n < 0 else "")
    if abs(n) >= 10000:
        return f"{sign}{n/10000:.1f}萬"
    if abs(n) >= 1000:
        return f"{sign}{n/1000:.1f}k"
    return f"{sign}{int(n)}"


def fmt_pct(n, decimals=1):
    if n is None:
        return "—"
    sign = "+" if n > 0 else ("−" if n < 0 else "")
    return f"{sign}{abs(n):.{decimals}f}%"


def fmt_pe(n):
    if n is None:
        return "—"
    return f"{n:.1f}"


def render_html(sectors, dates, total_tickers):
    """產出 sectors.html
    設計原則：
    - D026 台股色：紅=正/漲/+，綠=負/跌/-
    - D016 一行一訊息：每個 chip = 1 個事實
    - 行動裝置優先：手機上單欄可讀
    """
    today = datetime.now().strftime("%Y-%m-%d")
    rows = []
    for s in sectors:
        # 法人淨買超：紅=正（買超），綠=負（賣超）
        three = s["three_net_5d_lots"]
        three_class = "v-pos" if (three or 0) > 0 else ("v-neg" if (three or 0) < 0 else "")
        # 月營收 YoY：紅=正（成長），綠=負（衰退）
        yoy = s["yoy_median_pct"]
        yoy_class = "v-pos" if (yoy or 0) > 0 else ("v-neg" if (yoy or 0) < 0 else "")
        # PE 中位數：紅=高（貴），綠=低（便宜）— 估值偏主觀，這裡標中性
        pe = s["pe_median"]

        rows.append(f'''
  <a class="sector-card" href="https://walterliu168.github.io/tw-invest-suite/analyze/{s["lead_ticker"]}.html" target="_blank" rel="noopener">
    <div class="sector-head">
      <div class="sector-name">{s.get("industry_zh") or s["industry"]}</div>
      <div class="sector-lead">代表性：{s["lead_ticker"]} {s["lead_name"][:18]}</div>
    </div>
    <div class="sector-chips">
      <div class="chip">
        <div class="chip-k">5 日法人淨買超</div>
        <div class="chip-v {three_class}">{fmt_lots(three)} 張</div>
      </div>
      <div class="chip">
        <div class="chip-k">月營收 YoY</div>
        <div class="chip-v {yoy_class}">{fmt_pct(yoy)}</div>
      </div>
      <div class="chip">
        <div class="chip-k">PE 中位數</div>
        <div class="chip-v">{fmt_pe(pe)}</div>
      </div>
      <div class="chip">
        <div class="chip-k">檔數 / 總市值</div>
        <div class="chip-v">{s["count"]} 檔 · {s["mkt_cap_total"]/1e12:.1f} 兆</div>
      </div>
    </div>
  </a>''')
    rows_html = "\n".join(rows)

    # 5 個交易日字串
    dates_str = " · ".join(dates[::-1]) if dates else "—"

    html = f'''<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>板塊輪動 · tw-invest-suite</title>
<meta name="description" content="台股 1,962 檔依產業加總：5 日法人淨買超、月營收 YoY、PE 中位數">
<meta name="theme-color" content="#0a0e1a">
<meta property="og:title" content="板塊輪動 · tw-invest-suite">
<meta property="og:description" content="台股 1,962 檔依產業加總，看資金正湧向哪些板塊">
<meta property="og:image" content="https://walterliu168.github.io/tw-invest-suite/data/og.png">
<link rel="manifest" href="manifest.json">
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><text y='26' font-size='28'>🌊</text></svg>">
<style>
:root {{
  --bg: #0a0e1a;
  --panel: #131b2e;
  --panel2: #1a2440;
  --ink: #e6ecf5;
  --muted: #8aa0c0;
  --acc: #5fb1ff;
  --cyan: #39c5cf;
  --border: #1f2942;
  /* D026: 台股色 — 紅=正/漲/多頭, 綠=負/跌/空頭 */
  --red: #ec7063;
  --red-soft: #5a2a25;
  --green: #58d68d;
  --green-soft: #1f3a2a;
  --amber: #f5b041;
}}
* {{ box-sizing: border-box; }}
body {{ margin: 0; padding: 0; background: var(--bg); color: var(--ink); font-family: -apple-system, "Microsoft JhengHei", "Noto Sans TC", system-ui, sans-serif; line-height: 1.5; }}
a {{ color: inherit; text-decoration: none; }}
a:hover .sector-card {{ border-color: var(--acc); transform: translateY(-1px); }}

/* Header */
.hdr {{ max-width: 1200px; margin: 0 auto; padding: 32px 24px 16px; }}
.hdr h1 {{ margin: 0 0 8px; font-size: 1.6rem; }}
.hdr .sub {{ color: var(--muted); font-size: 0.92rem; margin: 0; }}
.hdr .meta {{ display: flex; flex-wrap: wrap; gap: 12px; margin-top: 16px; font-size: 0.82rem; color: var(--muted); }}
.hdr .meta .pill {{ background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 4px 12px; }}
.hdr .meta .pill b {{ color: var(--ink); }}

/* Nav */
.nav {{ max-width: 1200px; margin: 0 auto; padding: 0 24px 16px; display: flex; flex-wrap: wrap; gap: 8px; }}
.nav a {{ padding: 6px 14px; border: 1px solid var(--border); border-radius: 8px; color: var(--muted); font-size: 0.86rem; }}
.nav a:hover {{ background: var(--panel); color: var(--ink); text-decoration: none; }}
.nav a.cta {{ background: var(--acc); color: #000; border-color: var(--acc); font-weight: 600; }}

/* Legend */
.legend {{ max-width: 1200px; margin: 0 auto 8px; padding: 0 24px; color: var(--muted); font-size: 0.82rem; }}
.legend .swatch {{ display: inline-block; width: 12px; height: 12px; border-radius: 3px; vertical-align: middle; margin: 0 4px; }}
.legend .red {{ background: var(--red); }}
.legend .green {{ background: var(--green); }}

/* Grid */
.grid {{ max-width: 1200px; margin: 0 auto; padding: 16px 24px 60px; display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; }}
.sector-card {{ display: block; background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 16px; transition: all 0.15s; }}
.sector-head {{ margin-bottom: 12px; }}
.sector-name {{ font-size: 1.05rem; font-weight: 600; color: var(--ink); }}
.sector-lead {{ color: var(--muted); font-size: 0.78rem; margin-top: 4px; }}
.sector-chips {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
.chip {{ background: var(--panel2); border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; }}
.chip-k {{ color: var(--muted); font-size: 0.72rem; }}
.chip-v {{ font-size: 1rem; font-weight: 600; margin-top: 2px; font-variant-numeric: tabular-nums; }}
.v-pos {{ color: var(--red); }}   /* D026 紅=正 */
.v-neg {{ color: var(--green); }} /* D026 綠=負 */

footer {{ max-width: 1200px; margin: 24px auto 40px; padding: 0 24px; color: var(--muted); font-size: 0.82rem; text-align: center; }}
footer a {{ color: var(--acc); }}
</style>
</head>
<body>

<div class="hdr">
  <h1>🌊 板塊輪動</h1>
  <p class="sub">台股 {total_tickers} 檔依產業 (yfinance industry) 加總 — 每日 22:25 自動更新</p>
  <div class="meta">
    <div class="pill">📅 資料日 <b>{today}</b></div>
    <div class="pill">📊 5 日區間 <b>{dates_str}</b></div>
    <div class="pill">🏷 板塊數 <b>{len(sectors)}</b></div>
  </div>
</div>

<div class="nav">
  <a href="readme.html">🏠 首頁</a>
  <a href="watchlist.html">📊 24 檔精選</a>
  <a href="analyze.html">🔍 查個股</a>
  <a href="analyze/patterns.html">🎯 型態搜尋</a>
  <a class="cta" href="data/sectors.json" target="_blank">⬇️ JSON</a>
</div>

<div class="legend">
  <span class="swatch red"></span> 紅色 = 正向（買超 / 成長）
  <span class="swatch green" style="margin-left: 16px;"></span> 綠色 = 負向（賣超 / 衰退）
  （台股慣例 — 與美股相反）
</div>

<div class="grid">
{rows_html}
</div>

<footer>
  板塊輪動資料源：yfinance（產業分類）＋ FinMind（月營收、PE、法人買賣超）<br>
  報告為研究參考，非投資建議 · 過往績效不保證未來表現<br>
  <a href="https://github.com/walterLiu168/tw-invest-suite">📦 Source</a>
</footer>

</body>
</html>'''
    p = PUBLIC_DIR / "sectors.html"
    p.write_text(html, encoding="utf-8")
    print(f"[html] wrote {p}", file=sys.stderr)
    return p


def main():
    t0 = time.time()
    print(f"[start] {datetime.now():%Y-%m-%d %H:%M:%S}", file=sys.stderr)
    meta = load_ticker_metadata()
    yoy = compute_revenue_yoy(meta)
    inst5, dates = fetch_institutional_5d(meta)
    sectors = aggregate(meta, yoy, inst5)
    out = write_json(sectors, dates)
    render_html(sectors, dates, out["ticker_count_total"])
    print(f"[done] {time.time()-t0:.1f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
