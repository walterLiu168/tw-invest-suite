"""
Generate hedge-fund-grade Perplexity Computer research prompts for each pick.

Uses hedge-fund-research-prompts skill templates (Tiger Global growth, Baupost
deep value) and fills them with pick data from MySQL.

Output: a Markdown section ready to paste into Perplexity Computer.
"""
import os
import sys
from typing import List

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import market_screen as ms  # noqa: E402


# --- Tiger Global Growth Equity (template #8) ---

TIGER_GLOBAL_TEMPLATE = """# Tiger Global Growth Equity — Deep Dive

You are a **growth equity analyst at Tiger Global**, modeled after the firm's
publicly documented investment framework. Apply this to:

**Target Company**: {ticker} {name} ({industry})
**Current Price**: NT${price:.2f}
**Market Cap**: NT${market_cap:.0f}M
**52-Week Return**: {ret_60d:+.1%} (60d), {ret_240d:+.1%} (240d)
**Volume (today)**: {volume:,.0f} shares
**Latest News (last 5 days)**:
{news_block}

## Your Task

Produce a **one-page investment memo** with these 10 sections:

1. **Business Quality Assessment** (Score 1-10)
   - What does this company do in 1-2 sentences?
   - What is the durable competitive advantage (moat)?
   - What is the TAM and where in the S-curve is this company?

2. **Rule of 40 Check**
   - Revenue growth rate (YoY) +
   - EBITDA margin (or operating margin if EBITDA unavailable) =
   - Is it > 40%?

3. **Net Revenue Retention**
   - Estimate NRR from any available data (existing customer growth, expansion, churn)
   - Target: > 120% for healthy SaaS-like businesses

4. **Unit Economics**
   - Gross margin trajectory (improving / stable / declining)
   - Operating margin path to profitability
   - Any signs of cost discipline?

5. **Capital Allocation**
   - Where is the company investing? (R&D, M&A, capex)
   - Insider ownership % and recent transactions
   - Any buybacks, dividends, dilution?

6. **Comparable Multiples**
   - Industry peers and their P/E, P/S, EV/EBITDA
   - Where does {ticker} sit relative to peers?
   - Is the premium / discount justified?

7. **Bull Case** (3-5 bullet points, base rates cited)

8. **Bear Case** (3-5 bullet points, specific downside scenarios)

9. **Catalysts** (next 12 months, ranked by impact)
   - Product launches, earnings, regulatory, macro

10. **Investment Decision** (1 paragraph)
    - Position size (small / medium / large)
    - Entry trigger (price level or condition)
    - Stop loss level
    - 12-month price target with reasoning
    - Conviction level (low / medium / high)

## Constraints

- Cite specific numbers, not vague statements
- Reference real comparable companies (e.g., for Taiwan semiconductor, compare to TSMC peers)
- Output should fit on a single printed page
- Use markdown tables for comparable analysis
- **No buy/sell recommendation** without explicit risk framework
"""


# --- Baupost Deep Value (template #9) ---

BAUPOST_TEMPLATE = """# Baupost Group — Deep Value Investigation

You are **Seth Klarman's analytical framework at Baupost Group**, applying
margin-of-safety and value-trap discipline to:

**Target Company**: {ticker} {name} ({industry})
**Current Price**: NT${price:.2f}
**Market Cap**: NT${market_cap:.0f}M
**52-Week Return**: {ret_60d:+.1%} (60d), {ret_240d:+.1%} (240d)
**Volume (today)**: {volume:,.0f} shares
**Latest News (last 5 days)**:
{news_block}

## Your Task

Produce a **margin-of-safety report** with these sections:

1. **Downside Scenario** (must answer: "what is the worst this can be?")
   - Liquidation value (BV - intangibles - liabilities)
   - Going-concern floor (recession earnings × 8x P/E)
   - If both numbers > current price → deep value

2. **Asymmetric Payoff** (must show ≥ 3:1 upside:downside)
   - Bull case target (with reasoning)
   - Bear case target (with reasoning)
   - Probability-weighted expected return
   - Required: positive expected value at conservative probabilities

3. **Catalysts** (must identify ≥ 1)
   - Management change
   - Asset sale / spin-off
   - Activist intervention
   - Industry consolidation
   - Without a catalyst, even cheap stocks can stay cheap

4. **Value-Trap Checklist** (must check all 8)
   - [ ] Secular decline vs cyclical
   - [ ] Accounting red flags (receivables, inventory, off-balance-sheet)
   - [ ] Customer concentration
   - [ ] Capex sustainability
   - [ ] Regulatory tail risk
   - [ ] Insider selling
   - [ ] Short interest rising
   - [ ] Index inclusion / exclusion

5. **Quality of Earnings**
   - Cash flow vs reported earnings
   - One-time items
   - Working capital trends
   - Deferred revenue / customer advances

6. **Margin of Safety Calculation**
   - Graham Number = √(22.5 × EPS × BVPS)
   - Current price vs Graham Number
   - Discount %

7. **Position Sizing** (Kelly Criterion lite)
   - Suggested weight: 1-3% (deep value) or 5-10% (high conviction)
   - Maximum position: 10% of portfolio

8. **Final Verdict** (1 paragraph)
    - Buy / Hold / Pass
    - Required margin of safety: ≥ 30%
    - If less than 30% discount, do not buy

## Constraints

- Bear case must be the FIRST analysis (Klarman's discipline)
- Numbers must be defensible
- Acknowledge what you don't know
- **Never buy on hope or narrative alone** — numbers first
"""


def build_news_block(c: ms.Candidate) -> str:
    """Build the news bullet block for a pick."""
    if not c.news_headlines:
        return "  (no recent news in stock_news table)"
    lines = []
    for h in c.news_headlines[:5]:
        if h:
            lines.append(f"  - {h}")
    return "\n".join(lines) if lines else "  (none)"


def pick_template(c: ms.Candidate) -> str:
    """Choose Baupost (value) or Tiger Global (growth) per horizon + return profile."""
    # Long-term picks → if strong 240d return, use Tiger Global (growth)
    #                  else Baupost (value)
    # Short-term picks → Tiger Global (momentum / growth)
    if c.horizon == "long" and (c.excess_return_240d or 0) > 0.3:
        return TIGER_GLOBAL_TEMPLATE
    if c.horizon == "long" and (c.excess_return_240d or 0) < 0:
        return BAUPOST_TEMPLATE
    # Default: growth lens
    return TIGER_GLOBAL_TEMPLATE


def render_prompt(c: ms.Candidate) -> str:
    """Render the filled-in prompt for one pick."""
    template = pick_template(c)
    market_cap_str = f"{c.market_cap/1e6:.0f}" if c.market_cap else "0"
    return template.format(
        ticker=c.ticker,
        name=c.name,
        industry=c.industry or "—",
        price=c.close,
        market_cap=float(market_cap_str),
        # Pass fractions; template uses :+.1% which auto-multiplies by 100
        ret_60d=(c.excess_return_60d or 0.0),
        ret_240d=(c.excess_return_240d or 0.0),
        volume=c.volume,
        news_block=build_news_block(c),
    )


if __name__ == "__main__":
    result = ms.screen_market()
    out_dir = os.path.expanduser("~/.claude/skills/tw-invest-suite/reports")
    os.makedirs(out_dir, exist_ok=True)
    today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
    out_path = os.path.join(out_dir, f"deep-dive-prompts-{today}.md")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# 🔬 24 檔深度研究 Prompt（hedge-fund-research-prompts）\n\n")
        f.write(f"> 適用：複製每段 prompt 到 Perplexity Computer 跑深度研究\n\n")
        f.write("---\n\n")
        for label, _, _ in ms.PRICE_BUCKETS:
            if label not in result:
                continue
            f.write(f"## {label}\n\n")
            for c in result[label]["long"] + result[label]["short"]:
                f.write(render_prompt(c))
                f.write("\n\n---\n\n")
    print(f"[prompts] saved → {out_path}")
