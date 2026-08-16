"""Daily LLM commentary for watchlist 24 picks.

Reads watchlist + cross-source data, builds prompt, calls LLM, writes
markdown report to outputs/commentary/<date>.md.

Config (env vars, with defaults):
    LLM_BASE_URL  — OpenAI-compatible endpoint (default: Mavis internal)
    LLM_API_KEY   — API key (Mavis uses internal auth)
    LLM_MODEL     — model id (default: MiniMax-M3)
    WATCHLIST_RUN — specific market_screen_runs.id (default: latest)

Usage:
    python daily_commentary.py                # uses latest run
    python daily_commentary.py --run-id 7     # specific run
    python daily_commentary.py --out custom.md  # custom output path
"""
import os
import sys
import json
import argparse
import requests
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Optional

# Add project root to path so we can import project modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "scripts"))

try:
    import pymysql
    HAS_DB = True
except ImportError:
    HAS_DB = False

# ============== Config ==============
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://agent.minimax.io/mavis/api/v1/llm/v1")
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MODEL", "MiniMax-M3")

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "outputs" / "commentary"


# ============== DB Queries ==============

def get_conn():
    if not HAS_DB:
        raise RuntimeError("pymysql not installed")
    return pymysql.connect(host='localhost', user='root', password='1234',
                            database='tw_elec', connect_timeout=10)


def fetch_watchlist(run_id: Optional[int] = None) -> List[Dict]:
    """Fetch 24 watchlist picks + key metrics."""
    with get_conn() as conn:
        cur = conn.cursor(pymysql.cursors.DictCursor)
        if run_id is None:
            cur.execute("SELECT MAX(id) AS max_id FROM market_screen_runs")
            run_id = cur.fetchone()["max_id"]
        cur.execute("""
            SELECT
                p.ticker,
                p.name,
                p.horizon       AS direction,
                p.bucket        AS price_bucket,
                p.score,
                p.rationale     AS reasoning,
                p.industry,
                p.close_at_pick AS close_pick,
                p.change_pct,
                p.volume,
                p.market_cap,
                d.Close         AS close,
                d.rsi_14        AS rsi,
                d.ForeignNet    AS foreign_net,
                d.ThreeNet      AS three_net
            FROM market_screen_picks p
            LEFT JOIN daily_data2_full d ON p.ticker = d.Ticker
                AND d.Date = (SELECT MAX(Date) FROM daily_data2_full WHERE Ticker = p.ticker)
            WHERE p.run_id = %s
              AND p.status = 'active'
            ORDER BY
                FIELD(p.bucket, 'mega', 'large', 'mid', 'small'),
                p.horizon DESC, p.score DESC
        """, (run_id,))
        picks = cur.fetchall()
        # 24h news (top 2) — related_tickers is a JSON array
        for p in picks:
            cur.execute("""
                SELECT title, source, sentiment_label, published_at
                FROM stock_news
                WHERE related_tickers LIKE %s
                ORDER BY published_at DESC
                LIMIT 2
            """, (f'%"{p["ticker"]}"%',))
            p["news"] = [f"{n['title'][:60]}... ({n['source']})" for n in cur.fetchall()]
    return picks


def fetch_market_overview() -> Dict:
    """Get broad market context: TAIEX close, volume, breadth."""
    with get_conn() as conn:
        cur = conn.cursor(pymysql.cursors.DictCursor)
        cur.execute("""
            SELECT Date, Close, Volume
            FROM tw_index
            ORDER BY Date DESC
            LIMIT 5
        """)
        idx = cur.fetchall()
        # Foreign net across market (last day) + breadth
        cur.execute("""
            SELECT
                SUM(d.ForeignNet)    AS total_foreign,
                SUM(d.ThreeNet)      AS total_three,
                SUM(CASE WHEN d.Close > d2.Close THEN 1 ELSE 0 END) AS stocks_up,
                SUM(CASE WHEN d.Close < d2.Close THEN 1 ELSE 0 END) AS stocks_dn,
                COUNT(*)             AS total
            FROM daily_data2_full d
            JOIN daily_data2_full d2
              ON d.Ticker = d2.Ticker
             AND d2.Date = (SELECT MAX(Date2.Date) FROM daily_data2_full Date2
                            WHERE Date2.Ticker = d.Ticker AND Date2.Date < d.Date)
            WHERE d.Date = (SELECT MAX(Date) FROM daily_data2_full)
        """)
        breadth = cur.fetchone()
    return {"index_5d": idx, "breadth": breadth}


# ============== Prompt Builder ==============

PROMPT_TEMPLATE = """你是台股資深分析師，正在為客戶撰寫「每日台股精選早報」。
今天是 $today（$weekday）。

【大盤氛圍】
$market_overview

【24 檔精選】（已依價位 × 多空分組）

$stocks

---

請用繁體中文撰寫完整早報，格式如下：

## 1. 大盤速覽（2-3 段）
- 今日指數 / 量能 / 法人動向
- 整體市場情緒（貪婪/恐懼/中性）
- 影響今日走勢的關鍵事件

## 2. 24 檔精選速評
針對每檔用以下格式（**精簡、訊號明確**）：

### [TICKER] NAME — LONG_SHORT — BUCKET
- **判斷**：1 句多空結論
- **理由**：3 個 bullet（資料驅動，含具體數字）
- **進場 / 停損 / 目標**：具體價位
- **風險**：1-2 個關鍵風險

## 3. 跨檔觀察（2 段）
- 共同主題（哪幾檔同類股一起動、法人一致方向等）
- 反向觀察（哪些 ticker 的訊號矛盾）

## 4. 給客戶的行動建議（3-5 點）
- 今天該關注什麼、該避開什麼

---
語氣：直接、像 senior 分析師對客戶講話，不囉嗦。"""


def build_prompt(picks: List[Dict], market: Dict) -> str:
    today = date.today()
    weekday_cn = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"][today.weekday()]

    # Market overview text
    idx_5d = market.get("index_5d", [])
    if idx_5d:
        latest = idx_5d[0]
        prev = idx_5d[1] if len(idx_5d) > 1 else latest
        chg = ((latest["Close"] - prev["Close"]) / prev["Close"] * 100) if prev["Close"] else 0
        closes_str = ", ".join(f"{x['Close']:,.0f}" for x in idx_5d[::-1])
        mkt_txt = (
            f"加權指數：{latest['Close']:,.2f}（{chg:+.2f}%），"
            f"近 5 日：{closes_str}"
        )
    else:
        mkt_txt = "（無指數資料）"
    breadth = market.get("breadth") or {}
    if breadth.get("total_foreign") is not None:
        f_net = float(breadth["total_foreign"] or 0) / 1e6
        t_net = float(breadth["total_three"] or 0) / 1e6
        up = int(breadth.get("stocks_up") or 0)
        dn = int(breadth.get("stocks_dn") or 0)
        total = int(breadth.get("total") or 0)
        mkt_txt += (
            f"\n全市場外資買賣超：{f_net:+,.1f} 億股"
            f"\n三大法人合計：{t_net:+,.1f} 億股"
            f"\n上漲家數 {up} / 下跌 {dn} / 共 {total}"
        )

    # Stocks list text
    stocks_txt_parts = []
    for p in picks:
        direction_cn = "多" if p["direction"] == "long" else "空"
        bucket_cn = p.get("price_bucket") or "—"
        score = float(p.get("score") or 0)
        close = float(p.get("close") or p.get("close_pick") or 0)
        rsi = float(p.get("rsi") or 0)
        fn = float(p.get("foreign_net") or 0) / 1000
        tn = float(p.get("three_net") or 0) / 1000
        mcap = float(p.get("market_cap") or 0) / 1e8
        news_str = " | ".join(p.get("news") or []) or "（無近期新聞）"
        reasoning = (p.get("reasoning") or "")[:200].replace("\n", " ")
        name = p.get("name") or p["ticker"]
        line = (
            f"**{p['ticker']} {name}** ({p.get('industry', '—')}) · {direction_cn} · 價位 {bucket_cn} · 評分 {score:.1f}\n"
            f"  - 收盤 {close:,.2f} · RSI {rsi:.0f} · 外資 {fn:+,.0f} 張 · 三大 {tn:+,.0f} 張 · 市值 {mcap:,.1f} 億\n"
            f"  - 新聞：{news_str}\n"
            f"  - 選股理由：{reasoning}"
        )
        stocks_txt_parts.append(line)
    stocks_txt = "\n\n".join(stocks_txt_parts)

    from string import Template
    tpl = Template(PROMPT_TEMPLATE)
    return tpl.substitute(
        today=today.isoformat(),
        weekday=weekday_cn,
        market_overview=mkt_txt,
        stocks=stocks_txt,
    )


# ============== LLM Call ==============

def call_llm(prompt: str, max_tokens: int = 4096, temperature: float = 0.7) -> str:
    """Call OpenAI-compatible chat completion API."""
    url = f"{LLM_BASE_URL.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
    }
    if LLM_API_KEY:
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "你是台股資深分析師，擅長用數據說話、訊號明確、不囉嗦。"},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    print(f"  Calling LLM: {LLM_MODEL} @ {LLM_BASE_URL}", file=sys.stderr)
    resp = requests.post(url, json=payload, headers=headers, timeout=180)
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


# ============== Main ==============

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", type=int, help="market_screen_runs.id (default: latest)")
    parser.add_argument("--out", type=Path, help="Output markdown path")
    parser.add_argument("--dry-run", action="store_true", help="Print prompt only, no LLM call")
    parser.add_argument("--max-tokens", type=int, default=4096)
    args = parser.parse_args()

    print(f"[{datetime.now():%H:%M:%S}] Daily commentary starting...", file=sys.stderr)

    # 1. Fetch data
    print("  Fetching watchlist...", file=sys.stderr)
    picks = fetch_watchlist(run_id=args.run_id)
    print(f"    Got {len(picks)} picks", file=sys.stderr)
    print("  Fetching market overview...", file=sys.stderr)
    market = fetch_market_overview()

    # 2. Build prompt
    print("  Building prompt...", file=sys.stderr)
    prompt = build_prompt(picks, market)
    print(f"    Prompt: {len(prompt)} chars", file=sys.stderr)

    if args.dry_run:
        print("=" * 80)
        print(prompt)
        print("=" * 80)
        return

    # 3. Call LLM
    commentary = call_llm(prompt, max_tokens=args.max_tokens)
    print(f"    Got {len(commentary)} chars from LLM", file=sys.stderr)

    # 4. Write output
    if args.out:
        out_path = args.out
    else:
        DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = DEFAULT_OUTPUT_DIR / f"{date.today().isoformat()}.md"
    out_path.write_text(commentary, encoding="utf-8")
    print(f"  Written to {out_path}", file=sys.stderr)
    print(f"[{datetime.now():%H:%M:%S}] Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
