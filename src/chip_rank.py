"""chip_rank.py — 籌碼排行 v1（P1）
抓 10 日法人資料，產出：
  1. 今日 3 法人淨買超排行
  2. 5 日 3 法人淨買超排行
  3. 外資連買/連賣天數
  4. 外資投信同買/同賣榜
"""
import json
import statistics
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL_DIR = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite")
SCRIPTS_DIR = SKILL_DIR / "scripts"
CACHE_DIR = SCRIPTS_DIR / "_cache"
sys.path.insert(0, str(SCRIPTS_DIR))

import finmind_client as fm  # noqa: E402

PUBLIC_DIR = ROOT / "public"
DATA_DIR = PUBLIC_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 法人分項代號對照
INST_CAT = {
    "Foreign_Investor": "f",   # 外資
    "Investment_Trust": "t",   # 投信
    "Dealer_self": "ds",        # 自營商 (自行)
    "Dealer_Hedging": "dh",     # 自營商 (避險)
}
# 同買/同賣門檻：5 日 法人淨買超 ≥ 0.5 億 (TWD)
# 用 yfinance close price 換算，沒抓到 close 就只用 張 算
SAME_SIDE_TWD = 50_000_000       # 0.5 億
SAME_SIDE_LOTS = 1000            # fallback: 5 日淨 ≥ 1000 張
CONSEC_MIN_DAYS = 3              # 連買/連賣最少 3 天


def load_meta():
    """讀 cache 的 yfinance 資料 + FinMind 最新收盤價"""
    meta = {}
    for f in CACHE_DIR.glob("*.json"):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        t = f.stem
        yf = (j.get("yfinance") or {}).get("data") or {}
        if not yf:
            continue
        meta[t] = {
            "name": yf.get("longName") or t,
            "industry": yf.get("industry") or yf.get("sector") or "",
            "sector": yf.get("sector") or "",
            "mkt_cap": float(yf.get("marketCap") or 0),
            "price": float(yf.get("regularMarketPrice") or 0) or float(yf.get("previousClose") or 0) or 0,
        }
    print(f"[meta] {len(meta)} tickers (yfinance)", file=sys.stderr)
    return meta


def fetch_latest_prices():
    """抓最近一個交易日的 TaiwanStockPrice（全市場）拿收盤價
    用來把 法人淨買超 (股) 換算成 TWD"""
    today = datetime.now()
    for offset in range(0, 6):
        d = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        try:
            rows = fm.stock_price(stock_id="", start_date=d, end_date=d)
        except Exception as e:
            print(f"[price] {d} ERR {e}", file=sys.stderr)
            continue
        if rows:
            prices = {}
            for r in rows:
                t = str(r.get("stock_id", "")).strip()
                c = r.get("close")
                if t and c is not None:
                    try:
                        prices[t] = float(c)
                    except (TypeError, ValueError):
                        pass
            print(f"[price] {d} {len(prices)} tickers", file=sys.stderr)
            return prices, d
        time.sleep(0.5)
    return {}, ""


def fetch_institutional_10d():
    """抓近 10 個交易日 FinMind TaiwanStockInstitutionalInvestorsBuySell
    （每天 1 次呼叫，stock_id="" → 全部 ticker）"""
    all_rows = []
    today = datetime.now()
    for offset in range(0, 12):  # 12 個日曆日 cover 10 trading days
        d = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        try:
            rows = fm.stock_institutional(stock_id="", start_date=d, end_date=d)
        except Exception as e:
            print(f"[inst] {d} ERR {e}", file=sys.stderr)
            continue
        if rows:
            all_rows.extend(rows)
        time.sleep(0.5)
    print(f"[inst] total {len(all_rows)} rows", file=sys.stderr)
    return all_rows


def build_per_ticker_calendar(all_rows):
    """把 raw rows 整理成 {ticker: [list of dated net dicts sorted asc]}
    每股當日 5 法人分項淨買超 (股)"""
    by = {}
    for r in all_rows:
        t = str(r.get("stock_id", "")).strip()
        d = r.get("date", "")
        cat = r.get("name", "")
        if not t or not d or cat not in INST_CAT:
            continue
        b = r.get("buy") or 0
        s = r.get("sell") or 0
        try:
            net = float(b) - float(s)
        except (TypeError, ValueError):
            continue
        slot = by.setdefault(t, {}).setdefault(d, {"f": 0.0, "t": 0.0, "d": 0.0, "ds": 0.0, "dh": 0.0})
        if cat == "Foreign_Investor":
            slot["f"] = net
        elif cat == "Investment_Trust":
            slot["t"] = net
        elif cat == "Dealer_self":
            slot["ds"] = net
        elif cat == "Dealer_Hedging":
            slot["dh"] = net
    # 排序 + 加總自營商
    out = {}
    for t, bydate in by.items():
        dates = sorted(bydate.keys(), reverse=True)
        series = []
        for d in dates:
            v = bydate[d]
            series.append({
                "date": d,
                "f": v["f"],
                "t": v["t"],
                "d": v["ds"] + v["dh"],  # 自營 = 自行 + 避險
                "ds": v["ds"],
                "dh": v["dh"],
            })
        out[t] = series
    return out


def compute_features(per_ticker, meta):
    """對每檔算 feature dict"""
    out = []
    for t, series in per_ticker.items():
        if not series:
            continue
        m = meta.get(t, {})
        if not m:
            continue
        price = m.get("price") or 0
        # 今日
        today = series[0]
        # 5 日 = 前 5 個交易日 (含今日)
        five = series[:5]
        f_5d = sum(d["f"] for d in five)
        t_5d = sum(d["t"] for d in five)
        d_5d = sum(d["d"] for d in five)
        three_5d = f_5d + t_5d + d_5d
        # 20 日 (沒抓到 20 天就用拿到的)
        twenty = series[:20]
        f_20d = sum(d["f"] for d in twenty)
        t_20d = sum(d["t"] for d in twenty)
        d_20d = sum(d["d"] for d in twenty)
        # 換算 TWD（用今日收盤）
        if price > 0:
            f_5d_twd = f_5d * price
            t_5d_twd = t_5d * price
            d_5d_twd = d_5d * price
            three_5d_twd = three_5d * price
        else:
            f_5d_twd = t_5d_twd = d_5d_twd = three_5d_twd = None
        # 外資連買/連賣天數
        f_streak = 0
        f_streak_dir = 0  # +1=買, -1=賣
        for d in series:
            if d["f"] > 0:
                if f_streak_dir == 1:
                    f_streak += 1
                else:
                    f_streak = 1
                    f_streak_dir = 1
                break  # 從今天往回數 (另寫一個反向)
            if d["f"] < 0:
                if f_streak_dir == -1:
                    f_streak += 1
                else:
                    f_streak = 1
                    f_streak_dir = -1
                break
        # 重新算連買/連賣：往回數
        f_streak = 0
        f_streak_dir = 0
        for d in series:
            if d["f"] > 0:
                if f_streak_dir in (0, 1):
                    f_streak += 1
                    f_streak_dir = 1
                else:
                    break
            elif d["f"] < 0:
                if f_streak_dir in (0, -1):
                    f_streak += 1
                    f_streak_dir = -1
                else:
                    break
            else:
                break  # 0 中斷
        # 同買 / 同賣：5 日外資 + 投信 同向且金額達標
        same_side = None  # "buy"/"sell"/None
        # t_5d_shares 是股單位，要先 ÷1000 換成張
        f_lots_5d = f_5d / 1000.0
        t_lots_5d = t_5d / 1000.0
        if price > 0 and f_5d_twd is not None and t_5d_twd is not None:
            # f_5d_twd 為原始 TWD 元，SAME_SIDE_TWD = 0.5 億 = 5e7 元
            f_big = abs(f_5d_twd) >= SAME_SIDE_TWD
            t_big = abs(t_5d_twd) >= SAME_SIDE_TWD
        else:
            f_big = abs(f_lots_5d) >= SAME_SIDE_LOTS
            t_big = abs(t_lots_5d) >= SAME_SIDE_LOTS
        if f_5d > 0 and t_5d > 0 and f_big and t_big:
            same_side = "buy"
        elif f_5d < 0 and t_5d < 0 and f_big and t_big:
            same_side = "sell"
        out.append({
            "ticker": t,
            "name": m["name"],
            "industry": m["industry"],
            "price": price,
            "today_f": today["f"],
            "today_t": today["t"],
            "today_d": today["d"],
            "f_5d_shares": f_5d,
            "t_5d_shares": t_5d,
            "d_5d_shares": d_5d,
            "three_5d_shares": three_5d,
            "f_5d_twd": round(f_5d_twd / 1e8, 2) if f_5d_twd is not None else None,
            "t_5d_twd": round(t_5d_twd / 1e8, 2) if t_5d_twd is not None else None,
            "d_5d_twd": round(d_5d_twd / 1e8, 2) if d_5d_twd is not None else None,
            "three_5d_twd": round(three_5d_twd / 1e8, 2) if three_5d_twd is not None else None,
            "f_20d_shares": f_20d,
            "f_streak": f_streak,
            "f_streak_dir": f_streak_dir,  # 1=買, -1=賣
            "same_side": same_side,
        })
    return out


def write_json(features, dates):
    by_today_buy = sorted([f for f in features if f["three_5d_shares"] > 0],
                           key=lambda x: -x["three_5d_shares"])
    by_today_sell = sorted([f for f in features if f["three_5d_shares"] < 0],
                            key=lambda x: x["three_5d_shares"])
    same_buy = [f for f in features if f["same_side"] == "buy"]
    same_sell = [f for f in features if f["same_side"] == "sell"]
    f_consec_buy = [f for f in features if f["f_streak_dir"] == 1 and f["f_streak"] >= CONSEC_MIN_DAYS]
    f_consec_sell = [f for f in features if f["f_streak_dir"] == -1 and f["f_streak"] >= CONSEC_MIN_DAYS]
    out = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "trading_dates_5d": dates[:5],
        "trading_dates_10d": dates,
        "ticker_count": len(features),
        "tabs": {
            "all_buy": by_today_buy,
            "all_sell": by_today_sell,
            "same_buy": same_buy,
            "same_sell": same_sell,
            "f_consec_buy": f_consec_buy,
            "f_consec_sell": f_consec_sell,
        },
        "meta": {
            "same_side_threshold_twd": SAME_SIDE_TWD,
            "same_side_threshold_lots_fallback": SAME_SIDE_LOTS,
            "consecutive_min_days": CONSEC_MIN_DAYS,
        },
    }
    p = DATA_DIR / "chips.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[json] {p}  buy={len(by_today_buy)} sell={len(by_today_sell)} same_buy={len(same_buy)} same_sell={len(same_sell)} f_buy≥3d={len(f_consec_buy)} f_sell≥3d={len(f_consec_sell)}", file=sys.stderr)
    return out


def fmt_shares(n):
    """股 → 張"""
    if n is None:
        return "—"
    lots = n / 1000.0
    sign = "+" if n > 0 else ("−" if n < 0 else "")
    if abs(lots) >= 10000:
        return f"{sign}{lots/10000:.1f}萬張"
    if abs(lots) >= 1000:
        return f"{sign}{lots/1000:.1f}k張"
    return f"{sign}{int(lots)}張"


def fmt_twd(n):
    """億"""
    if n is None:
        return "—"
    sign = "+" if n > 0 else ("−" if n < 0 else "")
    return f"{sign}{abs(n):.2f}億"


def fmt_pct(n):
    if n is None:
        return "—"
    sign = "+" if n > 0 else ("−" if n < 0 else "")
    return f"{sign}{abs(n):.1f}%"


def render_html(data, out_path: Path):
    today = data["date"]
    dates = data["trading_dates_5d"]
    tabs = data["tabs"]

    def card(p, accent_left, badge=None, streak=None, twd=None, lots=None):
        # 卡片 HTML
        t = p["ticker"]
        n = p["name"][:14]
        ind = p.get("industry", "")[:12]
        f_5d = p["f_5d_shares"]
        t_5d = p["t_5d_shares"]
        d_5d = p["d_5d_shares"]
        f_5d_twd = p.get("f_5d_twd")
        t_5d_twd = p.get("t_5d_twd")
        d_5d_twd = p.get("d_5d_twd")
        # D026: 紅=正/買超, 綠=負/賣超
        def cls(v):
            if v is None or v == 0: return ""
            return "v-pos" if v > 0 else "v-neg"
        badge_html = f'<span class="badge">{badge}</span>' if badge else ""
        streak_html = f'<span class="streak">{streak}</span>' if streak else ""
        twd_html = f'<span class="twd">{twd}</span>' if twd else ""
        return f'''
        <a class="card" href="analyze/{t}.html" target="_blank" rel="noopener">
          <div class="card-accent" style="background:{accent_left}"></div>
          <div class="card-head">
            <span class="ticker">{t}</span>
            <span class="name">{n}</span>
            {badge_html}{streak_html}
          </div>
          <div class="card-ind muted">{ind}{twd_html}</div>
          <div class="card-chips">
            <div class="chip"><div class="k">5 日外資</div><div class="v {cls(f_5d)}">{fmt_shares(f_5d)}</div></div>
            <div class="chip"><div class="k">5 日投信</div><div class="v {cls(t_5d)}">{fmt_shares(t_5d)}</div></div>
            <div class="chip"><div class="k">5 日自營</div><div class="v {cls(d_5d)}">{fmt_shares(d_5d)}</div></div>
          </div>
          <div class="card-foot muted">
            <span>{f"收 {p['price']:.2f}" if p.get('price') else "—"}</span>
            <span>5 日 TWD {fmt_twd(p.get("three_5d_twd"))}</span>
          </div>
        </a>'''

    def render_grid(items, accent_default, badge_map=None, streak_map=None, limit=60):
        items = items[:limit]
        html = []
        for p in items:
            badge = (badge_map or {}).get(p["ticker"])
            streak = (streak_map or {}).get(p["ticker"])
            html.append(card(p, accent_default, badge=badge, streak=streak))
        if not html:
            return '<div class="empty">無資料</div>'
        return "\n".join(html)

    # badges
    same_buy_tickers = {p["ticker"] for p in tabs["same_buy"]}
    same_sell_tickers = {p["ticker"] for p in tabs["same_sell"]}
    f_buy_streak = {f["ticker"]: f"連買 {f['f_streak']} 天" for f in tabs["f_consec_buy"]}
    f_sell_streak = {f["ticker"]: f"連賣 {f['f_streak']} 天" for f in tabs["f_consec_sell"]}

    body = f'''
    <div class="tab-content active" data-bucket="all-buy">
      <h2 class="bucket-title">全部 5 日法人淨買超 <small>前 60 檔 · 依 3 法人合計降冪</small></h2>
      <div class="grid">{render_grid(tabs["all_buy"], "var(--red)", badge_map={**{t: "同買" for t in same_buy_tickers}, **{t: f_buy_streak[t].replace("連買 ", "連買 ") for t in f_buy_streak}})}</div>
    </div>
    <div class="tab-content" data-bucket="all-sell">
      <h2 class="bucket-title">全部 5 日法人淨賣超 <small>前 60 檔</small></h2>
      <div class="grid">{render_grid(tabs["all_sell"], "var(--green)", badge_map={t: "同賣" for t in same_sell_tickers}, streak_map=f_sell_streak)}</div>
    </div>
    <div class="tab-content" data-bucket="same-buy">
      <h2 class="bucket-title">外資投信同買 <small>5 日法人淨買超 ≥ 0.5 億 (或 ≥ 1,000 張)</small></h2>
      <div class="grid">{render_grid(tabs["same_buy"], "var(--red)", badge_map={t: "同買" for t in same_buy_tickers}, streak_map=f_buy_streak)}</div>
    </div>
    <div class="tab-content" data-bucket="same-sell">
      <h2 class="bucket-title">外資投信同賣 <small>5 日法人淨賣超 ≥ 0.5 億 (或 ≥ 1,000 張)</small></h2>
      <div class="grid">{render_grid(tabs["same_sell"], "var(--green)", badge_map={t: "同賣" for t in same_sell_tickers}, streak_map=f_sell_streak)}</div>
    </div>
    <div class="tab-content" data-bucket="f-buy">
      <h2 class="bucket-title">外資連買 <small>連續 {CONSEC_MIN_DAYS}+ 天</small></h2>
      <div class="grid">{render_grid(tabs["f_consec_buy"], "var(--red)", badge_map={t: "同買" for t in same_buy_tickers}, streak_map=f_buy_streak)}</div>
    </div>
    <div class="tab-content" data-bucket="f-sell">
      <h2 class="bucket-title">外資連賣 <small>連續 {CONSEC_MIN_DAYS}+ 天</small></h2>
      <div class="grid">{render_grid(tabs["f_consec_sell"], "var(--green)", badge_map={t: "同賣" for t in same_sell_tickers}, streak_map=f_sell_streak)}</div>
    </div>
    '''

    html = f'''<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>籌碼排行 · tw-invest-suite</title>
<meta name="description" content="台股 1,962 檔法人流向排行 — 今日 / 5 日 / 連買連賣 / 同買同賣">
<meta name="theme-color" content="#0a0e1a">
<meta property="og:title" content="籌碼排行 · tw-invest-suite">
<meta property="og:description" content="1,962 檔法人流向 — 今日 3 法人淨買超、同買同賣、外資連買連賣">
<meta property="og:image" content="https://walterliu168.github.io/tw-invest-suite/data/og.png">
<link rel="manifest" href="manifest.json">
<link rel="stylesheet" href="assets/textsize.css">
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><text y='26' font-size='28'>💎</text></svg>">
<style>
:root {{ --bg:#0a0e1a; --panel:#131b2e; --panel2:#1a2440; --ink:#e6ecf5; --muted:#8aa0c0; --acc:#5fb1ff; --cyan:#39c5cf; --border:#1f2942; --red:#ec7063; --red-soft:#5a2a25; --green:#58d68d; --green-soft:#1f3a2a; --amber:#f5b041; }}
* {{ box-sizing: border-box; }}
body {{ margin: 0; padding: 0; background: var(--bg); color: var(--ink); font-family: -apple-system, "Microsoft JhengHei", "Noto Sans TC", system-ui, sans-serif; line-height: 1.5; }}
a {{ color: inherit; text-decoration: none; }}
a:hover .card {{ border-color: var(--acc); transform: translateY(-1px); }}
.hdr {{ max-width: 1200px; margin: 0 auto; padding: 32px 24px 12px; }}
.hdr h1 {{ margin: 0 0 6px; font-size: 1.6rem; }}
.hdr .sub {{ color: var(--muted); font-size: 0.92rem; margin: 0; }}
.hdr .meta {{ display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; font-size: 0.82rem; }}
.hdr .pill {{ background: var(--panel); border: 1px solid var(--border); border-radius: 14px; padding: 4px 12px; color: var(--muted); }}
.hdr .pill b {{ color: var(--ink); }}
.nav {{ max-width: 1200px; margin: 0 auto; padding: 0 24px 12px; display: flex; flex-wrap: wrap; gap: 6px; }}
.nav a {{ padding: 5px 12px; border: 1px solid var(--border); border-radius: 8px; color: var(--muted); font-size: 0.85rem; }}
.nav a:hover {{ background: var(--panel); color: var(--ink); text-decoration: none; }}
.tabs {{ max-width: 1200px; margin: 0 auto; padding: 0 24px; display: flex; flex-wrap: wrap; gap: 4px; }}
.tab {{ background: var(--panel); color: var(--muted); border: 1px solid var(--border); padding: 7px 14px; border-radius: 8px; cursor: pointer; font-size: 0.88rem; font-weight: 500; }}
.tab:hover {{ color: var(--ink); }}
.tab.active {{ background: var(--acc); color: #000; border-color: var(--acc); font-weight: 600; }}
.tab .cnt {{ background: rgba(0,0,0,0.25); padding: 1px 7px; border-radius: 8px; font-size: 0.7rem; margin-left: 4px; }}
.tab.active .cnt {{ background: rgba(255,255,255,0.3); color: #000; }}
main {{ max-width: 1200px; margin: 0 auto; padding: 16px 24px 60px; }}
.bucket-title {{ font-size: 1rem; color: var(--acc); margin: 0 0 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }}
.bucket-title small {{ color: var(--muted); font-weight: 400; font-size: 0.78rem; }}
.tab-content {{ display: none; }}
.tab-content.active {{ display: block; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px; }}
.card {{ display: block; background: var(--panel); border: 1px solid var(--border); border-radius: 10px; padding: 12px 14px 12px 18px; position: relative; transition: all 0.15s; overflow: hidden; }}
.card-accent {{ position: absolute; left: 0; top: 0; bottom: 0; width: 4px; }}
.card-head {{ display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 4px; }}
.ticker {{ font-size: 1.1rem; font-weight: 700; color: var(--acc); font-family: 'Consolas', monospace; }}
.name {{ color: var(--ink); font-weight: 500; font-size: 0.9rem; }}
.badge {{ background: var(--red-soft); color: var(--red); padding: 1px 7px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; }}
.badge.same-sell {{ background: var(--green-soft); color: var(--green); }}
.streak {{ background: var(--amber); color: #000; padding: 1px 7px; border-radius: 4px; font-size: 0.7rem; font-weight: 600; }}
.card-ind {{ font-size: 0.75rem; display: flex; gap: 8px; margin-bottom: 8px; }}
.twd {{ color: var(--cyan); font-weight: 600; font-size: 0.72rem; }}
.card-chips {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; margin-bottom: 6px; }}
.chip {{ background: var(--panel2); border: 1px solid var(--border); border-radius: 6px; padding: 4px 6px; }}
.chip .k {{ color: var(--muted); font-size: 0.62rem; }}
.chip .v {{ font-size: 0.85rem; font-weight: 600; margin-top: 1px; font-variant-numeric: tabular-nums; }}
.v-pos {{ color: var(--red); }}  /* D026 紅=正/買 */
.v-neg {{ color: var(--green); }} /* D026 綠=負/賣 */
.card-foot {{ display: flex; justify-content: space-between; font-size: 0.7rem; }}
.empty {{ color: var(--muted); text-align: center; padding: 40px; }}
footer {{ max-width: 1200px; margin: 0 auto 40px; padding: 0 24px; color: var(--muted); font-size: 0.82rem; text-align: center; }}
footer a {{ color: var(--acc); }}
</style>
</head>
<body>

<div class="hdr">
  <h1>💎 籌碼排行</h1>
  <p class="sub">台股 1,962 檔法人流向 — 今日 / 5 日 / 連買連賣 / 同買同賣</p>
  <div class="meta">
    <div class="pill">📅 資料日 <b>{today}</b></div>
    <div class="pill">📊 5 日區間 <b>{" · ".join(dates[::-1])}</b></div>
    <div class="pill">🏷 涵蓋 <b>{data['ticker_count']} 檔</b></div>
  </div>
</div>

<div class="nav">
  <a href="readme.html">🏠 首頁</a>
  <a href="watchlist.html">📊 24 檔精選</a>
  <a href="sectors.html">🌊 板塊輪動</a>
  <a href="analyze/patterns.html">🎯 型態搜尋</a>
  <a href="data/chips.json" target="_blank">⬇️ JSON</a>
</div>

<div class="tabs">
  <button class="tab active" data-tab="all-buy">全部買超 <span class="cnt">{len(tabs['all_buy'])}</span></button>
  <button class="tab" data-tab="all-sell">全部賣超 <span class="cnt">{len(tabs['all_sell'])}</span></button>
  <button class="tab" data-tab="same-buy">同買 <span class="cnt">{len(tabs['same_buy'])}</span></button>
  <button class="tab" data-tab="same-sell">同賣 <span class="cnt">{len(tabs['same_sell'])}</span></button>
  <button class="tab" data-tab="f-buy">外資連買 <span class="cnt">{len(tabs['f_consec_buy'])}</span></button>
  <button class="tab" data-tab="f-sell">外資連賣 <span class="cnt">{len(tabs['f_consec_sell'])}</span></button>
</div>

<main>
{body}
</main>

<footer>
  籌碼資料源：FinMind TaiwanStockInstitutionalInvestorsBuySell（每日全市場下載）<br>
  報告為研究參考，非投資建議 · 過往績效不保證未來表現<br>
  <a href="https://github.com/walterLiu168/tw-invest-suite">📦 Source</a>
</footer>

<script>
// Tabs
document.querySelectorAll('.tab').forEach(function (b) {{
  b.addEventListener('click', function () {{
    var k = b.getAttribute('data-tab');
    document.querySelectorAll('.tab').forEach(function (x) {{ x.classList.toggle('active', x === b); }});
    document.querySelectorAll('.tab-content').forEach(function (c) {{
      c.classList.toggle('active', c.getAttribute('data-bucket') === k);
    }});
  }});
}});
</script>
<script src="assets/textsize.js"></script>

</body>
</html>'''
    out_path.write_text(html, encoding="utf-8")
    print(f"[html] {out_path}", file=sys.stderr)


def main():
    t0 = time.time()
    print(f"[start] {datetime.now():%Y-%m-%d %H:%M:%S}", file=sys.stderr)
    meta = load_meta()
    prices, price_date = fetch_latest_prices()
    # 把 price merge 到 meta
    for t, p in prices.items():
        if t in meta:
            meta[t]["price"] = p
    print(f"[meta+price] {sum(1 for m in meta.values() if m.get('price', 0) > 0)} tickers have price (using {price_date})", file=sys.stderr)
    all_rows = fetch_institutional_10d()
    per_ticker = build_per_ticker_calendar(all_rows)
    features = compute_features(per_ticker, meta)
    sorted_dates = sorted({r["date"] for r in all_rows}, reverse=True)[:10]
    data = write_json(features, sorted_dates)
    data["price_date"] = price_date
    render_html(data, PUBLIC_DIR / "chips.html")
    print(f"[done] {time.time()-t0:.1f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
