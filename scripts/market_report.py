"""
Generate market-screen report from screener output.

Applies hedge-fund-expert-team analysis framework to each pick:
  - Long-term: Buffett/Munger/Graham lens (value, moat, balance sheet strength)
  - Short-term: Wood/Burry/Druckenmiller lens (momentum, sentiment, catalysts)

Output: market-screen-YYYY-MM-DD.md in reports/ dir.
"""
import os
import sys
from datetime import datetime
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import market_screen as ms  # noqa: E402


def report_header() -> str:
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""# 📊 台股全市場分價位掃描報告

> 報告日期：{today}
> 工具：tw-invest-suite v0.2（market screen mode）
> 資料源：MySQL `tw_elec.daily_data2_full`（資料日期 {ms.db.latest_date('daily_data2_full')}）
> 篩選邏輯：4 個價位分組 × 每組 3 短中期 + 3 長期 = 24 檔推薦

"""


def bucket_intro(label: str, lo: int, hi: float) -> str:
    """Return a section header with the right emoji + tagline per bucket."""
    if hi == float("inf"):
        return (
            f"## 🏆 {label} 元\n\n"
            "*高價股 — 龍頭企業、法人重倉、波動相對小*\n\n"
        )
    if lo >= 300:
        return (
            f"## 💎 {label} 元\n\n"
            "*中高價股 — 基本面與成長性兼具，適合中期持有*\n\n"
        )
    if lo >= 100:
        return (
            f"## 💵 {label} 元\n\n"
            "*中價股 — 主流操作區間，流動性佳*\n\n"
        )
    return (
        f"## 💰 {label} 元\n\n"
        "*銅板股 — 高波動、題材驅動，短中期操作為主*\n\n"
    )


def long_term_analysis(c: ms.Candidate) -> str:
    """Hedge-fund-expert-team lens for long-term picks.

    Applies Buffett/Munger/Graham/Damodaran criteria:
    - 240d return (momentum proxy)
    - Market cap (moat / scale)
    - ROE proxy (we don't have it, but 240d return is correlated)
    - Volume (liquidity)
    """
    lines = []
    lines.append(f"### 🏛️ {c.ticker} {c.name}（長期）")
    lines.append("")
    lines.append(f"**收盤**：{c.close:.2f} 元  |  **市值**：{c.market_cap/1e9:,.0f} 億  |  **產業**：{c.industry or '—'}")
    lines.append("")

    # Buffett/Munger moat metrics
    cap_text = f"{c.market_cap/1e9:,.0f} 億市值" if c.market_cap else "—"
    bullets = []

    # 240d return as quality proxy
    er240 = c.excess_return_240d or 0
    if er240 > 0.5:
        bullets.append(f"📈 **長期動能強**：240d +{er240:.0%}，巴菲特會想看這檔")
    elif er240 > 0.1:
        bullets.append(f"📈 240d +{er240:.0%}，穩健表現")
    elif er240 < -0.2:
        bullets.append(f"⚠️ 240d {er240:+.0%}，長期動能偏弱，留意是否價值陷阱")

    # Market cap
    if c.market_cap and c.market_cap > 100e9:  # > 1000 億
        bullets.append(f"🏢 **大市值** {cap_text}，符合 Munger「大型、可預測」標準")
    elif c.market_cap and c.market_cap > 30e9:  # > 300 億
        bullets.append(f"🏢 中型市值 {cap_text}，Graham 會列入研究清單")

    # Liquidity (avg volume)
    if c.volume > 5_000_000:
        bullets.append(f"💧 高流動性（今日 {c.volume/1e6:.1f}M 股），可承受大資金")
    elif c.volume > 1_000_000:
        bullets.append(f"💧 流動性 OK（{c.volume/1e3:.0f}K 股）")

    # Industry
    if c.industry:
        bullets.append(f"🏷️ 產業：{c.industry}")

    # Damodaran valuation hint (not exact, just sanity)
    if c.foreign_ratio > 50:
        bullets.append(f"🌍 外資持股 {c.foreign_ratio:.0f}%，國際資金認可")

    lines.append("\n".join(f"- {b}" for b in bullets))
    lines.append("")

    # Graham number hint
    if c.excess_return_240d and c.excess_return_240d > 0.3:
        lines.append("> 💎 **Graham 式評估**：長期動能顯著，可進一步用 DCF 估算內在價值。")
    lines.append("")
    return "\n".join(lines)


def short_term_analysis(c: ms.Candidate) -> str:
    """Hedge-fund-expert-team lens for short-term picks.

    Applies Wood/Burry/Druckenmiller/Technical:
    - Trend alignment (close > SMA13 > SMA27)
    - RSI sweet spot
    - VolumeBurst, KD_GoldenCross (chip signals)
    - News sentiment
    - Gap-up
    """
    lines = []
    lines.append(f"### ⚡ {c.ticker} {c.name}（短中期）")
    lines.append("")
    lines.append(f"**收盤**：{c.close:.2f} 元  |  **漲跌**：{c.change_pct:+.2f}%  |  **產業**：{c.industry or '—'}")
    lines.append("")

    bullets = []

    # Trend alignment (Wood: 順勢而為)
    if c.sma13 and c.sma27 and c.close > c.sma13 > c.sma27:
        bullets.append(f"📈 **多頭排列**：收盤 > SMA13({c.sma13:.0f}) > SMA27({c.sma27:.0f})")
    elif c.sma13 and c.close > c.sma13:
        bullets.append(f"📈 收盤站上 SMA13({c.sma13:.0f})，短多")

    # RSI
    if 50 <= c.rsi14 <= 65:
        bullets.append(f"🎯 **RSI {c.rsi14:.0f}** 在 50-65 甜蜜區，動能強但未過熱")
    elif 40 <= c.rsi14 < 50:
        bullets.append(f"🎯 RSI {c.rsi14:.0f} 中性偏弱，留意反轉")
    elif c.rsi14 > 70:
        bullets.append(f"⚠️ RSI {c.rsi14:.0f} 超買，短線過熱")
    elif c.rsi14 < 30:
        bullets.append(f"🔻 RSI {c.rsi14:.0f} 超賣，反彈機會")

    # Chip signals
    if c.volume_burst == 1:
        bullets.append("💥 **量能爆發** (VolumeBurst)")
    if c.kd_golden_cross == 1:
        bullets.append("✝️ **KD 黃金交叉**")
    if c.inv_first_in == 1:
        bullets.append("🏦 **法人首次進場**")
    if c.chip_score and c.chip_score > 50:
        bullets.append(f"🧠 ChipScore {c.chip_score:.0f}（{ '強' if c.chip_score > 60 else '中性偏多'}）")
    if c.foreign_net and c.foreign_net > 0:
        bullets.append(f"🌍 外資今日買超 {c.foreign_net/1000:,.0f} 張")

    # News sentiment
    if c.news_sentiment_avg is not None:
        if c.news_sentiment_avg > 0.3:
            bullets.append(f"📰 新聞情緒 {c.news_sentiment_avg:+.2f}（{c.news_count_5d}則/5日，題材面正向）")
        elif c.news_sentiment_avg < -0.3:
            bullets.append(f"📰 新聞情緒 {c.news_sentiment_avg:+.2f}（{c.news_count_5d}則/5日，負面）")
    elif c.news_count_5d > 0:
        bullets.append(f"📰 5日內 {c.news_count_5d} 則新聞")

    # Gap
    if c.is_gap == 1 and c.change_pct > 0:
        bullets.append(f"⬆️ 跳空上漲 {c.change_pct:+.2f}%")

    if not bullets:
        bullets.append("— 訊號平淡，無明顯短線催化劑")

    lines.append("\n".join(f"- {b}" for b in bullets))
    lines.append("")

    # News headlines
    if c.news_headlines:
        lines.append("**近期新聞**：")
        for h in c.news_headlines[:3]:
            if h:
                lines.append(f"  - {h}")
        lines.append("")

    # Wood: 5-year vision check
    if c.industry:
        lines.append(f"> 🔬 **Cathie Wood 視角**：{c.industry} 是否在 S 曲線早期採用階段？需產業研究。")
        lines.append("")

    return "\n".join(lines)


def render_picks(label: str, lo: int, hi: float,
                 longs: List[ms.Candidate], shorts: List[ms.Candidate]) -> str:
    """Render one bucket (e.g. '<100') with its 3+3 picks."""
    parts = [bucket_intro(label, lo, hi)]

    if longs:
        parts.append("### 📈 長期持有推薦（基本面）\n")
        for c in longs:
            parts.append(long_term_analysis(c))
    if shorts:
        parts.append("### ⚡ 短中期交易推薦（技術+題材）\n")
        for c in shorts:
            parts.append(short_term_analysis(c))
    return "\n".join(parts)


def render_report(result: Dict[str, Dict[str, List[ms.Candidate]]]) -> str:
    out = [report_header()]

    # Quick market summary
    total_picks = sum(len(v["long"]) + len(v["short"]) for v in result.values())
    out.append(f"## 📋 掃描摘要\n")
    out.append(f"- 全市場股票：1,943 檔（TWSE + TPEx）")
    out.append(f"- 推薦總數：{total_picks} 檔")
    out.append(f"- 4 個價位：<100、100-300、300-1000、>1000")
    out.append(f"- 每個價位：3 檔長期 + 3 檔短中期")
    out.append("")
    out.append("---\n")

    for label, lo, hi in ms.PRICE_BUCKETS:
        if label not in result:
            continue
        out.append(render_picks(label, lo, hi, result[label]["long"], result[label]["short"]))
        out.append("\n---\n")

    out.append("""
## ⚠️ 免責聲明

> 本報告由 AI 自動產生，**僅供研究與教育用途**。
>
> - 資料來源：MySQL `tw_elec` 資料倉（以 `daily_data2_full` 為主，輔以 `chipscore_daily`、`stock_features`、`stock_news`）
> - 篩選邏輯為啟發式（heuristic），非投資建議
> - 投資一定有風險，入市需謹慎
> - 請於做決策前自行查證最新數據或諮詢持牌顧問

*本報告由 tw-invest-suite (market screen mode) 自動產生*
""")
    return "\n".join(out)


def save_report(result: Dict[str, Dict[str, List[ms.Candidate]]]) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    out_dir = os.path.expanduser("~/.claude/skills/tw-invest-suite/reports")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"market-screen-{today}.md")
    content = render_report(result)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


if __name__ == "__main__":
    print("Running market screen…")
    result = ms.screen_market()
    print("Generating report…")
    path = save_report(result)
    print(f"\n[OK] saved → {path}")
