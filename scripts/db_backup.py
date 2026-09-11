#!/usr/bin/env python3
"""Бэкап таблиц БД в CSV (перед миграцией). Read-only по данным, пишет локально."""
import csv
import json
import os
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

import psycopg

TABLES = ["orders", "order_items", "calls"]


def _ser(v):
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return str(v)
    return v


def main():
    url = os.environ["DATABASE_URL"]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outdir = ROOT / "backup" / ts
    outdir.mkdir(parents=True, exist_ok=True)

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            for table in TABLES:
                cur.execute(f"SELECT * FROM {table}")
                cols = [d[0] for d in cur.description]
                rows = cur.fetchall()
                path = outdir / f"{table}.csv"
                with path.open("w", newline="", encoding="utf-8") as f:
                    w = csv.writer(f, delimiter=";")
                    w.writerow(cols)
                    for row in rows:
                        w.writerow([_ser(v) for v in row])
                print(f"{table}: {len(rows)} rows -> {path}")
    print(f"BACKUP_DIR={outdir}")


if __name__ == "__main__":
    main()
