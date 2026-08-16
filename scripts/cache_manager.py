"""
Per-ticker per-data-type cache for the cross-source daily run.

Schema (one JSON file per ticker):
    _cache/<ticker>.json
    {
      "yfinance":  {"fetched_at": "2026-08-13T22:25:00", "data": {...}},
      "finmind_pe":     {"fetched_at": "...", "data": {...}},
      "finmind_div":    {"fetched_at": "...", "data": {...}},
      "finmind_fin":    {"fetched_at": "...", "data": {...}},
      "finmind_month":  {"fetched_at": "...", "data": {...}},
      "finmind_news":   {"fetched_at": "...", "data": [...], "tier": "watchlist|all"},
      "verify_diff":    {"fetched_at": "...", "diffs": [...]}
    }

Cache TTLs (per data type):
    yfinance        1d   (P/E, P/B, dividend, marketCap change daily)
    finmind_pe      1d
    finmind_div     30d
    finmind_fin     30d  (quarterly P&L)
    finmind_month   7d   (monthly revenue, refreshed weekly)
    finmind_news    4h   (watchlist) / 12h (all)

Cross-verify runs on every yfinance fetch (compare PER with FinMind PER).
"""
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

CACHE_DIR = Path(r"C:\Users\icemo\.claude\skills\tw-invest-suite\scripts\_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Cache TTL per data type
TTL = {
    "yfinance":       timedelta(days=1),
    "finmind_pe":     timedelta(days=1),
    "finmind_div":    timedelta(days=30),
    "finmind_fin":    timedelta(days=30),
    "finmind_month":  timedelta(days=7),
    "finmind_news_watchlist": timedelta(hours=4),
    "finmind_news_all":       timedelta(hours=12),
}


def _path(ticker: str) -> Path:
    safe = ticker.replace("/", "_").replace("\\", "_")
    return CACHE_DIR / f"{safe}.json"


def load(ticker: str) -> Dict[str, Any]:
    """Return cached data for ticker (empty dict if no cache)."""
    p = _path(ticker)
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save(ticker: str, cache: Dict[str, Any]) -> None:
    """Persist full cache for one ticker (atomic write)."""
    p = _path(ticker)
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def get_fresh(ticker: str, key: str) -> Optional[Dict[str, Any]]:
    """Return cached entry if fresh, else None. Includes fetched_at + data."""
    cache = load(ticker)
    entry = cache.get(key)
    if not entry:
        return None
    ttl = TTL.get(key)
    if not ttl:
        return entry  # unknown key — treat as fresh
    try:
        fetched = datetime.fromisoformat(entry["fetched_at"])
    except (KeyError, ValueError):
        return None
    if datetime.now() - fetched > ttl:
        return None
    return entry


def put(ticker: str, key: str, data: Any) -> None:
    """Update one key in the ticker's cache and persist."""
    cache = load(ticker)
    cache[key] = {"fetched_at": datetime.now().isoformat(timespec="seconds"), "data": data}
    save(ticker, cache)


def needs_refresh(ticker: str, key: str) -> bool:
    """True if cache miss or stale."""
    return get_fresh(ticker, key) is None


def clear(ticker: str) -> None:
    """Delete cache for one ticker (used for testing)."""
    p = _path(ticker)
    if p.exists():
        p.unlink()


def clear_all() -> int:
    """Delete all cache files. Returns count deleted."""
    n = 0
    for p in CACHE_DIR.glob("*.json"):
        p.unlink()
        n += 1
    return n


def stats() -> Dict[str, int]:
    """Return summary stats for the cache directory."""
    files = list(CACHE_DIR.glob("*.json"))
    return {
        "ticker_count": len(files),
        "size_mb": sum(p.stat().st_size for p in files) / 1024 / 1024,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "clear":
        n = clear_all()
        print(f"Cleared {n} cache files")
    else:
        s = stats()
        print(f"Cache stats: {s['ticker_count']} tickers, {s['size_mb']:.1f} MB")
