#!/usr/bin/env python3
"""Полный прогон миграции prod: stamp baseline -> upgrade 0003 -> данные -> upgrade head."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT))

BASE_URL = os.environ["DATABASE_URL"]

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402


def _cfg():
    return Config(str(ROOT / "alembic.ini"))


def _counts(label):
    import psycopg
    with psycopg.connect(BASE_URL) as conn:
        with conn.cursor() as cur:
            def q(sql):
                cur.execute(sql)
                return cur.fetchone()[0]
            clients = q("SELECT count(*) FROM clients")
            orders = q("SELECT count(*) FROM orders")
            calls = q("SELECT count(*) FROM calls")
            oi = q("SELECT count(*) FROM information_schema.tables WHERE table_name = 'order_items'")
    oi_txt = "есть" if oi else "нет"
    print(f"[{label}] clients={clients} orders={orders} calls={calls} order_items={oi_txt}")


def main():
    print("[1/4] stamp baseline (legacy-таблицы уже существуют)")
    command.stamp(_cfg(), "0001_baseline")

    print("[2/4] upgrade -> 0003_links (clients + колонки)")
    command.upgrade(_cfg(), "0003_links")
    _counts("после 0003")

    print("[3/4] данные (clients + client_id + mp3_hash + дедуп)")
    sys.path.insert(0, str(ROOT / "scripts"))
    import migrate_data as md  # noqa: E402
    orders = md.read_orders(md.DATA_DIR / "orders.csv")
    calls = md.read_calls(md.DATA_DIR / "calls.csv")
    keep, drop = md.dedup_calls(calls)
    clients = md.build_clients(orders, keep)
    print(f"    keep={len(keep)} drop={len(drop)} clients={len(clients)}")
    md.apply_to_db(orders, keep, drop, clients)
    _counts("после данных")

    print("[4/4] upgrade -> head (mp3_hash UNIQUE + drop order_items)")
    command.upgrade(_cfg(), "head")
    _counts("ИТОГ")

    # финальные проверки
    import psycopg
    with psycopg.connect(BASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM calls WHERE mp3_hash IS NULL")
            null_hash = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM (SELECT mp3_hash FROM calls GROUP BY mp3_hash HAVING count(*) > 1) x")
            dup_hash = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM orders WHERE client_id IS NULL")
            null_client_orders = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM calls WHERE client_id IS NULL")
            null_client_calls = cur.fetchone()[0]
    print(f"ПРОВЕРКИ: null mp3_hash={null_hash}, dup mp3_hash={dup_hash}, "
          f"orders без client_id={null_client_orders}, calls без client_id={null_client_calls}")
    print("MIGRATION COMPLETE")


if __name__ == "__main__":
    main()
