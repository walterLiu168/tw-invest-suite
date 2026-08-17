#!/usr/bin/env python3
"""
FinMind TaiwanStockMarginMaintenance fetcher.

下載全市場個股融資維持率，存到 `finmind_taiwan_margin_maintenance` 表。
取代 120d avg close 的估算（更精準）。

API: https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockMarginMaintenance
頻率: 每日 22:25 跑（run_daily.ps1 stage 9）
Rate: 6000/hr sponsor；1 call 拿全市場（~2000 stocks），3 天範圍
"""
import os
import sys
import time
import json
import requests
import pymysql
from pathlib import Path
from datetime import datetime, date, timedelta

# === Config ===
TOKEN_PATH = Path.home() / ".finmind_token"
API_URL = "https://api.finmindtrade.com/api/v4/data"
DATASET = "TaiwanStockMarginMaintenance"
TARGET_TABLE = "finmind_taiwan_margin_maintenance"

DB_HOST = "localhost"
DB_USER = "root"
DB_PASS = "1234"
DB_NAME = "tw_elec"


def get_token() -> str:
    if not TOKEN_PATH.exists():
        raise SystemExit(f"FATAL: no token at {TOKEN_PATH}")
    return TOKEN_PATH.read_text().strip()


def get_conn():
    return pymysql.connect(host=DB_HOST, user=DB_USER, password=DB_PASS,
                            database=DB_NAME, connect_timeout=10)


def ensure_table():
    """Create target table if not exists."""
    sql = f"""
    CREATE TABLE IF NOT EXISTS {TARGET_TABLE} (
        id BIGINT AUTO_INCREMENT PRIMARY KEY,
        trade_date DATE NOT NULL,
        ticker VARCHAR(16) NOT NULL,
        margin_balance BIGINT,
        margin_cost BIGINT,
        margin_ratio DECIMAL(10,4),
        margin_maintenance DECIMAL(10,4),
        fetched_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uk_date_ticker (trade_date, ticker),
        INDEX idx_ticker (ticker),
        INDEX idx_date (trade_date),
        INDEX idx_maint (margin_maintenance)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql)
        conn.commit()


def ensure_registry(token: str):
    """Add this dataset to finmind_source_registry if not present."""
    sql = """
    INSERT IGNORE INTO finmind_source_registry
        (dataset_key, api_family, finmind_endpoint, source_system, source_tz,
         refresh_cadence, api_rate_class, target_table, default_batch_size,
         owner_module, notes, last_verified_at, created_at, updated_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), NOW())
    """
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, (
            DATASET, "finmind", DATASET, "FinMind", "Asia/Taipei",
            "daily", "finmind", TARGET_TABLE, 1,
            "margin_rebound/finmind_maint.py",
            "Per-stock margin maintenance ratio (real, not 120d-avg estimate)"
        ))
        conn.commit()


def fetch_latest(days_back: int = 7) -> list:
    """Fetch last N days from FinMind.

    NOTE: FinMind API returns the data for the start_date only when given a range.
    So we need to call multiple times (one per date) to get a range.
    For simplicity, we just fetch the latest trading day.
    """
    # Find latest trading day from DB
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("SELECT MAX(Date) FROM daily_data2_full")
        latest = cur.fetchone()[0]
    if not latest:
        print("  WARN: no data in daily_data2_full", flush=True)
        return []
    if isinstance(latest, str):
        latest_date = date.fromisoformat(latest)
    else:
        latest_date = latest

    # Fetch the latest day's data (FinMind returns all stocks for this date)
    end = latest_date
    start = end - timedelta(days=days_back)
    all_rows = []
    for offset in range(days_back + 1):
        target = start + timedelta(days=offset)
        params = {
            "dataset": DATASET,
            "start_date": target.isoformat(),
            "end_date": target.isoformat(),
            "token": get_token(),
        }
        try:
            r = requests.get(API_URL, params=params, timeout=60)
            r.raise_for_status()
            data = r.json()
            if data.get("data"):
                all_rows.extend(data["data"])
                print(f"  + {target}: {len(data['data'])} rows", flush=True)
            else:
                # Empty (weekend/holiday) — skip silently
                pass
        except Exception as e:
            print(f"  WARN: {target} failed: {e}", flush=True)
            continue
        # Rate limit: 1.05s/call (safe, 57/min < 120 anti-abuse)
        time.sleep(1.1)
    return all_rows


def upsert_rows(rows: list):
    """Insert/replace into target table."""
    if not rows:
        return 0
    sql = f"""
    INSERT INTO {TARGET_TABLE}
        (trade_date, ticker, margin_balance, margin_cost, margin_ratio, margin_maintenance)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        margin_balance = VALUES(margin_balance),
        margin_cost = VALUES(margin_cost),
        margin_ratio = VALUES(margin_ratio),
        margin_maintenance = VALUES(margin_maintenance),
        fetched_at = NOW()
    """
    with get_conn() as conn:
        cur = conn.cursor()
        n = 0
        for r in rows:
            try:
                cur.execute(sql, (
                    r["date"],
                    r["stock_id"],
                    int(r.get("margin_balance") or 0),
                    int(r.get("margin_cost") or 0),
                    float(r.get("margin_ratio") or 0),
                    float(r.get("margin_maintenance") or 0),
                ))
                n += 1
            except (KeyError, ValueError, TypeError) as e:
                # skip malformed row
                continue
        conn.commit()
        return n


def main():
    days_back = int(os.environ.get("MAINT_DAYS_BACK", "7"))
    print(f"[{datetime.now():%H:%M:%S}] FinMind {DATASET} fetcher starting (days_back={days_back})", flush=True)
    print("  Ensuring table + registry...", flush=True)
    ensure_table()
    ensure_registry(get_token())

    print("  Fetching from FinMind...", flush=True)
    rows = fetch_latest(days_back=days_back)
    print(f"  Got {len(rows)} rows", flush=True)

    print("  Upserting to DB...", flush=True)
    n = upsert_rows(rows)
    print(f"  Upserted {n} rows", flush=True)
    print(f"[{datetime.now():%H:%M:%S}] Done.", flush=True)


if __name__ == "__main__":
    main()
