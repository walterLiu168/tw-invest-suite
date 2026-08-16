"""
Master runner: do one full market screen and produce all artifacts.

Run from a chat trigger like '跑市場掃描' or 'today's recommendations'.

Outputs in ~/.claude/skills/tw-invest-suite/reports/:
  - market-screen-YYYY-MM-DD.md    (Markdown report)
  - market-screen-YYYY-MM-DD.html   (HTML report with deep-dive prompts)
  - deep-dive-prompts-YYYY-MM-DD.md (Perplexity prompt pack)
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import market_screen as ms
import market_report as mr
import market_report_html as mrh
import deep_dive_prompts as ddp


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"=== tw-invest-suite · market screen · {today} ===\n")

    print("[1/3] Running screener…")
    result = ms.screen_market()

    print("\n[2/3] Generating Markdown report…")
    md_path = mr.save_report(result)
    print(f"  → {md_path}")

    print("\n[3/3] Generating HTML report + deep-dive prompts…")
    html_path = mrh.save_html(result)
    print(f"  → {html_path}")

    # deep-dive-prompts also produces its own file when run as main;
    # call its main logic explicitly so we get the path back
    out_dir = os.path.expanduser("~/.claude/skills/tw-invest-suite/reports")
    dd_path = os.path.join(out_dir, f"deep-dive-prompts-{today}.md")
    if not os.path.exists(dd_path):
        # Run its main
        with open(dd_path, "w", encoding="utf-8") as f:
            f.write(f"# 🔬 24 檔深度研究 Prompt（hedge-fund-research-prompts）\n\n")
            f.write(f"> 適用：複製每段 prompt 到 Perplexity Computer 跑深度研究\n\n")
            f.write("---\n\n")
            for label, _, _ in ms.PRICE_BUCKETS:
                if label not in result:
                    continue
                f.write(f"## {label}\n\n")
                for c in result[label]["long"] + result[label]["short"]:
                    f.write(ddp.render_prompt(c))
                    f.write("\n\n---\n\n")
    print(f"  → {dd_path}")

    print(f"\n✅ Done. Open the HTML in a browser: file:///{html_path.replace(os.sep, '/')}")


if __name__ == "__main__":
    main()
