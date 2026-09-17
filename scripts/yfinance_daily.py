"""Versioned optional valuation-cache refresh used by the 22:30 Scheduler task."""
import logging
from pathlib import Path
import time

import db_client as db
import yfinance_batch as yfb


def main():
    logs = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_debug")
    logs.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", handlers=[logging.FileHandler(logs / f"yfinance_{time.strftime('%Y%m%d_%H%M%S')}.log", encoding="utf-8"), logging.StreamHandler()])
    with db.get_cursor() as cursor:
        cursor.execute("SELECT ticker FROM industry_type WHERE ticker REGEXP '^[0-9]{4}$|^[0-9]{4}[A-Z]$' ORDER BY ticker")
        tickers = [row["ticker"] for row in cursor.fetchall()]
    if not tickers:
        raise ValueError("Empty valuation-refresh universe")
    yfb.reset()
    logging.info("Valuation refresh: %s tickers, two workers", len(tickers))
    results = yfb.batch_fetch(tickers, workers=2, force=True)
    counts = {kind: sum(item.get("_source") == kind for item in results.values()) for kind in ("yfinance", "fallback", "error")}
    logging.info("Results %s; provider_dead=%s", counts, yfb.is_dead())
    if yfb.is_dead():
        return 2
    return 1 if counts["error"] or counts["fallback"] or len(results) != len(tickers) else 0


if __name__ == "__main__":
    raise SystemExit(main())
