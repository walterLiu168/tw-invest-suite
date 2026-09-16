"""D056 one-time official metadata repair. Preserve quarantine rows and audit before writes."""
import argparse
import json
from datetime import datetime
from pathlib import Path

import db_client as db
import pipeline_state as ps

SOURCE = "https://www.twse.com.tw/staticFiles/news/news/tsecnews/8a8216d69dbea9fd019dfc9546a8010d.pdf"
COMPANY = "頌勝科技"
INDUSTRY = "半導體業"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    audit = Path(__file__).parent / "_debug" / "7768-official-resolution"
    with db.get_conn() as conn:
        conn.begin()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT * FROM industry_type WHERE ticker=%s FOR UPDATE", ("7768",))
            existing = cursor.fetchone()
            if existing and (existing["company"] != COMPANY or existing["industry"] != INDUSTRY):
                raise ValueError("Existing metadata conflicts with the reviewed official classification")
            cursor.execute("SELECT * FROM metadata_quarantine WHERE ticker=%s AND resolved_at IS NULL FOR UPDATE", ("7768",))
            rows = cursor.fetchall()
            for row in rows:
                if row["type"] != "twse" or row["stock_name"] != COMPANY or set(json.loads(row["candidate_categories"])) != {INDUSTRY, "電子工業"}:
                    raise ValueError("Unreviewed quarantine event; stop without changing data")
            cursor.execute("SELECT Date,company FROM daily_data2_full WHERE Ticker=%s AND (company IS NULL OR TRIM(company)='') FOR UPDATE", ("7768",))
            company_rows = cursor.fetchall()
            summary = {"ticker": "7768", "source": SOURCE, "official_notice_date": "2026-05-06", "listing_date": "2026-05-07", "industry": INDUSTRY, "open_quarantine": len(rows), "missing_company_rows": len(company_rows), "apply": args.apply}
            if not args.apply:
                conn.rollback()
                print(json.dumps(summary, ensure_ascii=False))
                return 0
            stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
            ps.atomic_json(audit / f"before-{stamp}.json", {**summary, "existing": existing, "quarantine": rows, "company_rows": company_rows})
            if not existing:
                cursor.execute("INSERT INTO industry_type (ticker,company,industry) VALUES (%s,%s,%s)", ("7768", COMPANY, INDUSTRY))
            for row in rows:
                cursor.execute("UPDATE metadata_quarantine SET resolved_at=NOW(),resolved_to_industry=%s WHERE id=%s AND resolved_at IS NULL", (INDUSTRY, row["id"]))
                if cursor.rowcount != 1:
                    raise ValueError("Quarantine changed concurrently")
            cursor.execute("UPDATE daily_data2_full SET company=%s WHERE Ticker=%s AND (company IS NULL OR TRIM(company)='')", (COMPANY, "7768"))
            if cursor.rowcount != len(company_rows):
                raise ValueError("Company repair count changed concurrently")
            conn.commit()
            ps.atomic_json(audit / f"applied-{stamp}.json", {**summary, "status": "committed", "applied_at": datetime.now().isoformat()})
            print(json.dumps({**summary, "status": "committed"}, ensure_ascii=False))
            return 0
        except Exception:
            conn.rollback()
            raise


if __name__ == "__main__":
    raise SystemExit(main())
