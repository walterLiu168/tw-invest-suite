"""chip_advanced.py — 籌碼進階指標 (P2)
抓 20 日 OHLCV + 20 日法人，產出：
  - 法人 20 日均價 (VWAP on days with positive net institutional)
  - 當前價位 vs 法人 20 日均價 (% above/below)
  - 力道標 (今日 / 5 日平均 ratio)
  - 外資停留天數 (從最近方向改變算到今天)
"""
import json
import statistics
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
SKILL_DIR = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite")
SCRIPTS_DIR = SKILL_DIR / "scripts"
CACHE_DIR = SCRIPTS_DIR / "_cache"
sys.path.insert(0, str(SCRIPTS_DIR))

import finmind_client as fm  # noqa: E402
from industry_zh import zh_industry, resolve  # noqa: E402

PUBLIC_DIR = ROOT / "public"
DATA_DIR = PUBLIC_DIR / "data"


def fetch_ohlcv_20d():
    """抓近 30 個日曆日 (cover 20 trading days) 全市場 OHLCV"""
    by = {}  # date -> {ticker: close}
    today = datetime.now()
    for offset in range(0, 32):
        d = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        try:
            rows = fm.stock_price(stock_id="", start_date=d, end_date=d)
        except Exception as e:
            print(f"[price] {d} ERR {e}", file=sys.stderr)
            continue
        if rows:
            day = {}
            for r in rows:
                t = str(r.get("stock_id", "")).strip()
                c = r.get("close")
                if t and c is not None:
                    try:
                        day[t] = float(c)
                    except (TypeError, ValueError):
                        pass
            by[d] = day
            print(f"[price] {d} {len(day)} tickers", file=sys.stderr)
        time.sleep(0.5)
        if len(by) >= 22:  # 取夠了
            break
    return by


def fetch_institutional_20d():
    """抓 30 個日曆日 FinMind institutional"""
    all_rows = []
    today = datetime.now()
    for offset in range(0, 32):
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


def build_features(ohlcv, inst_rows, meta):
    """組合 OHLCV + institutional → 每檔 feature"""
    # 整理 inst → {ticker: {date: {f, t, d}}}
    by = {}
    for r in inst_rows:
        t = str(r.get("stock_id", "")).strip()
        d = r.get("date", "")
        cat = r.get("name", "")
        if not t or not d or cat not in ("Foreign_Investor", "Investment_Trust", "Dealer_self", "Dealer_Hedging"):
            continue
        b = r.get("buy") or 0
        s = r.get("sell") or 0
        try:
            net = float(b) - float(s)
        except (TypeError, ValueError):
            continue
        slot = by.setdefault(t, {}).setdefault(d, {"f": 0.0, "t": 0.0, "d": 0.0})
        if cat == "Foreign_Investor":
            slot["f"] = net
        elif cat == "Investment_Trust":
            slot["t"] = net
        elif cat in ("Dealer_self", "Dealer_Hedging"):
            slot["d"] += net
    # 取交集日期
    all_dates = sorted(ohlcv.keys(), reverse=True)
    inst_dates = sorted({d for by_td in by.values() for d in by_td.keys()}, reverse=True)
    common_dates = sorted(set(all_dates) & set(inst_dates), reverse=True)
    use_dates = common_dates[:20]  # 最多 20 個交易日
    print(f"[merge] ohlcv dates={len(all_dates)}, inst dates={len(inst_dates)}, common={len(common_dates)}, using {len(use_dates)}", file=sys.stderr)
    out = []
    for t, m in meta.items():
        if t not in by:
            continue
        # 取這檔在 use_dates 內的資料
        per_day = []
        for d in use_dates:
            od = ohlcv.get(d, {}).get(t)
            id_ = by[t].get(d)
            if od is None or id_ is None:
                continue
            three_net = id_["f"] + id_["t"] + id_["d"]
            per_day.append({
                "date": d,
                "close": od,
                "f": id_["f"],
                "t": id_["t"],
                "d": id_["d"],
                "three": three_net,
            })
        if not per_day:
            continue
        # per_day[0] = 最新, per_day[-1] = 最舊
        # 我們要按時間正序算 20 日均
        per_day_asc = list(reversed(per_day))
        # 法人 20 日均價 (VWAP on days with positive net)
        buy_days = [d for d in per_day_asc if d["three"] > 0]
        if buy_days:
            sum_amount = sum(d["three"] * d["close"] for d in buy_days)
            sum_shares = sum(d["three"] for d in buy_days)
            vwap_buy = sum_amount / sum_shares if sum_shares > 0 else None
        else:
            vwap_buy = None
        # 法人 20 日均價 (所有天 — 包含負值) → 用 close 為權重
        sum_amount_all = sum(d["three"] * d["close"] for d in per_day_asc)
        sum_shares_all = sum(d["three"] for d in per_day_asc)
        vwap_all = sum_amount_all / sum_shares_all if sum_shares_all > 0 else None
        # 當前收盤 (今日)
        cur_close = per_day_asc[-1]["close"] if per_day_asc else 0
        # 當前 vs 法人 20 日均價
        if vwap_buy and vwap_buy > 0 and cur_close > 0:
            pct = (cur_close - vwap_buy) / vwap_buy * 100
        else:
            pct = None
        # 20 日累計 3 法人淨買超
        cum_20d = sum(d["three"] for d in per_day_asc)
        cum_20d_f = sum(d["f"] for d in per_day_asc)
        cum_20d_t = sum(d["t"] for d in per_day_asc)
        # 5 日累計
        cum_5d = sum(d["three"] for d in per_day_asc[-5:])
        # 力道標 = 今日 / 5 日均日
        today_three = per_day_asc[-1]["three"] if per_day_asc else 0
        avg_5d_daily = cum_5d / 5 if len(per_day_asc) >= 5 else (cum_5d / max(1, len(per_day_asc)))
        if avg_5d_daily > 0:
            force = today_three / avg_5d_daily
        elif avg_5d_daily < 0 and today_three < 0:
            force = abs(today_three / avg_5d_daily)
        else:
            force = None
        # 外資停留天數 (從最近方向改變算到今天)
        f_stay = 0
        f_stay_dir = 0
        for d in reversed(per_day_asc):  # 從最舊到最新
            if d["f"] > 0:
                if f_stay_dir in (0, 1):
                    f_stay += 1; f_stay_dir = 1
                else:
                    break
            elif d["f"] < 0:
                if f_stay_dir in (0, -1):
                    f_stay += 1; f_stay_dir = -1
                else:
                    break
            else:
                break
        # 20 日內有幾天 外資買超 / 賣超
        f_buy_days = sum(1 for d in per_day_asc if d["f"] > 0)
        f_sell_days = sum(1 for d in per_day_asc if d["f"] < 0)
        out.append({
            "ticker": t,
            "name": m.get("name", t),
            "industry": m.get("industry", ""),
            "industry_zh": resolve(t, m.get("industry", ""), m.get("sector", "")),
            "price": cur_close,
            "vwap_buy_20d": round(vwap_buy, 2) if vwap_buy else None,
            "vwap_all_20d": round(vwap_all, 2) if vwap_all else None,
            "vs_vwap_pct": round(pct, 2) if pct is not None else None,
            "cum_20d_shares": cum_20d,
            "cum_20d_f_shares": cum_20d_f,
            "cum_20d_t_shares": cum_20d_t,
            "cum_5d_shares": cum_5d,
            "force_ratio": round(force, 2) if force is not None else None,
            "f_stay_days": f_stay,
            "f_stay_dir": f_stay_dir,
            "f_buy_days_20d": f_buy_days,
            "f_sell_days_20d": f_sell_days,
        })
    return out, use_dates


def load_meta():
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
            "industry": yf.get("industry") or "",
            "sector": yf.get("sector") or "",
        }
    return meta


def write_json(features, dates):
    # 多條件雷達 (P2.4 雛形)：
    # 「力道強」= force >= 2.0 且 5d 法人淨買超 (買盤) / 「法人加碼」= vs_vwap_pct <= -3
    radar = {
        "force_strong_buy": [f for f in features if (f.get("force_ratio") or 0) >= 2.0 and f.get("cum_5d_shares", 0) > 0],
        "force_strong_sell": [f for f in features if (f.get("force_ratio") or 0) >= 2.0 and f.get("cum_5d_shares", 0) < 0],
        "below_inst_cost": [f for f in features if (f.get("vs_vwap_pct") or 0) <= -3.0],
        "above_inst_cost": [f for f in features if (f.get("vs_vwap_pct") or 0) >= 3.0],
    }
    for k in radar:
        radar[k].sort(key=lambda x: abs(x.get("force_ratio") or x.get("vs_vwap_pct") or 0), reverse=True)
    out = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "trading_dates_20d": dates,
        "ticker_count": len(features),
        "features": features,
        "radar": radar,
    }
    p = DATA_DIR / "chips-advanced.json"
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[json] {p}  count={len(features)}  force_buy={len(radar['force_strong_buy'])} force_sell={len(radar['force_strong_sell'])} below={len(radar['below_inst_cost'])} above={len(radar['above_inst_cost'])}", file=sys.stderr)
    return out


def main():
    t0 = time.time()
    print(f"[start] {datetime.now():%Y-%m-%d %H:%M:%S}", file=sys.stderr)
    meta = load_meta()
    print(f"[meta] {len(meta)} tickers", file=sys.stderr)
    ohlcv = fetch_ohlcv_20d()
    inst = fetch_institutional_20d()
    features, dates = build_features(ohlcv, inst, meta)
    write_json(features, dates)
    print(f"[done] {time.time()-t0:.1f}s", file=sys.stderr)


if __name__ == "__main__":
    main()
