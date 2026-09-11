#!/usr/bin/env python3
"""Read-only: инвентаризация таблиц БД (проверка состояния перед миграцией)."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))

import psycopg


def main():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL не задан")

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), version()")
            db, ver = cur.fetchone()
            print(f"database: {db}")
            print(f"version:  {ver.split(' on ')[0]}")

            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' ORDER BY table_name"
            )
            tables = [r[0] for r in cur.fetchall()]
            print(f"\ntables ({len(tables)}):")
            for t in tables:
                try:
                    cur.execute(f'SELECT count(*) FROM "{t}"')
                    n = cur.fetchone()[0]
                    print(f"  {t}: {n} rows")
                except Exception as e:  # noqa: BLE001
                    print(f"  {t}: ERROR {e}")


if __name__ == "__main__":
    main()
