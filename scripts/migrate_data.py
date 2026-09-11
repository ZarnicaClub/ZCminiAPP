#!/usr/bin/env python3
"""Миграция данных legacy -> newCRM v2.

Читает production-выгрузки data/orders.csv и data/calls.csv, строит
clients/orders/calls целевой схемы и (в режиме --apply) пишет в PostgreSQL.

Порядок в общем runbook:
  1. alembic upgrade 0003        (схема: clients + колонки, mp3_hash ещё nullable)
  2. python scripts/migrate_data.py --apply   (данные + дедуп)
  3. alembic upgrade head        (0004 UNIQUE(mp3_hash), 0005 drop order_items)

Режимы:
  --dry-run : только парсинг/подсчёт/валидация, без БД.
  --apply   : upsert в PostgreSQL (DATABASE_URL). Идемпотентно.
"""
import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared.phone import normalize_phone  # noqa: E402

DATA_DIR = ROOT / "data"

ORDERS_COLS = [
    "id", "order_id", "order_status", "payment_amount", "payment_currency",
    "payment_system", "payment_transaction_id", "order_date", "customer_name",
    "customer_email", "customer_phone", "game", "tent", "session_time", "qty",
    "extra_fields", "raw_payload", "received_at",
]


def read_orders(path: Path):
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        for rec in csv.DictReader(f, fieldnames=ORDERS_COLS, delimiter=";"):
            if not rec.get("order_id"):
                continue
            rows.append(rec)
    return rows


def read_calls(path: Path):
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as f:
        for rec in csv.DictReader(f, delimiter=";"):
            md = {}
            try:
                md = json.loads(rec.get("metadata") or "{}")
            except (json.JSONDecodeError, TypeError):
                pass
            rec["sha256"] = md.get("sha256")
            rows.append(rec)
    return rows


def dedup_calls(calls):
    """1 звонок на уникальный sha256 (оставляем минимальный id)."""
    groups = defaultdict(list)
    for c in calls:
        key = c.get("sha256") or ("email:" + str(c.get("email_id")))
        groups[key].append(c)
    keep, drop = [], []
    for key, items in groups.items():
        items = sorted(items, key=lambda x: int(x.get("id") or 0))
        keep.append(items[0])
        drop.extend(items[1:])
    return keep, drop


def build_clients(orders, calls):
    clients = {}  # phone -> dict
    for o in orders:
        p = normalize_phone(o.get("customer_phone"))
        if not p:
            continue
        c = clients.setdefault(p, {"phone": p, "name": None, "email": None})
        c["name"] = c["name"] or (o.get("customer_name") or None)
        c["email"] = c["email"] or (o.get("customer_email") or None)
    for call in calls:
        p = normalize_phone(call.get("phone"))
        if not p:
            continue
        clients.setdefault(p, {"phone": p, "name": None, "email": None})
    return list(clients.values())


def _jsonb(v):
    v = (v or "").strip()
    return v if v else "{}"


def apply_to_db(orders, calls_keep, calls_drop, clients):
    import psycopg

    db = os.environ.get("DATABASE_URL")
    if not db:
        raise SystemExit("DATABASE_URL не задан")

    with psycopg.connect(db) as conn:
        with conn.cursor() as cur:
            for c in clients:
                cur.execute(
                    """
                    INSERT INTO clients (phone, name, email) VALUES (%s, %s, %s)
                    ON CONFLICT (phone) DO UPDATE SET
                        name = COALESCE(clients.name, EXCLUDED.name),
                        email = COALESCE(clients.email, EXCLUDED.email)
                    """,
                    (c["phone"], c["name"], c["email"]),
                )

            for o in orders:
                phone = normalize_phone(o.get("customer_phone"))
                cur.execute(
                    """
                    INSERT INTO orders (
                        order_id, order_status, payment_amount, payment_currency,
                        payment_system, payment_transaction_id, order_date,
                        customer_name, customer_email, customer_phone,
                        game, tent, session_time, qty, extra_fields, raw_payload,
                        received_at, source, client_id
                    ) VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,
                        %s,'tilda',(SELECT client_id FROM clients WHERE phone=%s)
                    )
                    ON CONFLICT (order_id) DO UPDATE SET
                        client_id = (SELECT client_id FROM clients WHERE phone=%s)
                    """,
                    (
                        o.get("order_id"), o.get("order_status"), o.get("payment_amount"),
                        o.get("payment_currency"), o.get("payment_system"),
                        o.get("payment_transaction_id"), o.get("order_date"),
                        o.get("customer_name"), o.get("customer_email"),
                        o.get("customer_phone"), o.get("game"), o.get("tent"),
                        o.get("session_time"), o.get("qty"),
                        _jsonb(o.get("extra_fields")), _jsonb(o.get("raw_payload")),
                        o.get("received_at"), phone, phone,
                    ),
                )

            for c in calls_keep:
                phone = normalize_phone(c.get("phone"))
                dur = c.get("duration_seconds")
                cur.execute(
                    """
                    INSERT INTO calls (
                        email_id, order_id, phone, call_datetime, administrator,
                        mp3_filename, s3_key, duration_seconds, status, metadata,
                        client_id, mp3_hash
                    ) VALUES (
                        %s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,
                        (SELECT client_id FROM clients WHERE phone=%s), %s
                    )
                    ON CONFLICT (email_id) DO UPDATE SET
                        client_id = (SELECT client_id FROM clients WHERE phone=%s),
                        mp3_hash = EXCLUDED.mp3_hash
                    """,
                    (
                        c.get("email_id"), (c.get("order_id") or None), phone,
                        c.get("call_datetime"), c.get("administrator"),
                        c.get("mp3_filename"), c.get("s3_key"),
                        (int(dur) if dur not in (None, "") else None),
                        c.get("status"), c.get("metadata"), phone, c.get("sha256"),
                        phone,
                    ),
                )

            for c in calls_drop:
                cur.execute("DELETE FROM calls WHERE id = %s", (c.get("id"),))

        conn.commit()
    print("APPLY: done")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="писать в PostgreSQL")
    ap.add_argument("--dry-run", action="store_true", help="только подсчёт")
    a = ap.parse_args()

    orders = read_orders(DATA_DIR / "orders.csv")
    calls = read_calls(DATA_DIR / "calls.csv")
    calls_keep, calls_drop = dedup_calls(calls)
    clients = build_clients(orders, calls_keep)

    print(f"orders:            {len(orders)}")
    print(f"calls total:       {len(calls)}")
    print(f"calls keep:        {len(calls_keep)}")
    print(f"calls drop (dupes):{len(calls_drop)}")
    print(f"clients:           {len(clients)}")

    bad_o = [o for o in orders if not normalize_phone(o.get("customer_phone"))]
    bad_c = [c for c in calls_keep if not normalize_phone(c.get("phone"))]
    print(f"orders, bad phone: {len(bad_o)}")
    print(f"calls,  bad phone: {len(bad_c)}")

    if a.apply:
        apply_to_db(orders, calls_keep, calls_drop, clients)
    else:
        print("(dry-run: запись в БД не выполнялась)")


if __name__ == "__main__":
    main()
