"""Тест логики миграции данных (dedup, clients) на синтетических данных."""
import csv
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import migrate_data as md

CALLS_HEADER = ["id", "email_id", "order_id", "phone", "call_datetime", "administrator",
                "mp3_filename", "s3_key", "duration_seconds", "status", "created_at", "metadata"]


def _write_orders(path):
    rows = [
        ["1", "o1", "paid", "5000", "RUB", "tinkoff", "t1", "2026-08-16", "А", "a@x.ru",
         "79001112233", "g", "t", "s", "2", "{}", "{}", "2026-08-16 10:00:00+00"],
        ["2", "o2", "paid", "5000", "RUB", "tinkoff", "t2", "2026-08-17", "Б", "b@x.ru",
         "79004445566", "g", "t", "s", "2", "{}", "{}", "2026-08-17 10:00:00+00"],
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        csv.writer(f, delimiter=";").writerows(rows)


def _write_calls(path):
    rows = [
        ["1", "e1", "o1", "79001112233", "2026-08-16 12:00:00+00", "adm", "a.mp3", "k1",
         "60", "matched", "2026-08-16 12:00:00+00", '{"sha256":"aaa"}'],
        ["2", "e2", "o1", "79001112233", "2026-08-16 12:00:00+00", "adm", "a.mp3", "k2",
         "60", "matched", "2026-08-16 12:00:00+00", '{"sha256":"aaa"}'],  # дубль sha256
        ["3", "e3", "", "79009998877", "2026-08-16 13:00:00+00", "adm", "b.mp3", "k3",
         "30", "unmatched", "2026-08-16 13:00:00+00", '{"sha256":"bbb"}'],
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(CALLS_HEADER)
        w.writerows(rows)


def test_migration_logic():
    td = ROOT / "tests" / "_fixtures_tmp"
    td.mkdir(exist_ok=True)
    try:
        _write_orders(td / "orders.csv")
        _write_calls(td / "calls.csv")
        orders = md.read_orders(td / "orders.csv")
        calls = md.read_calls(td / "calls.csv")
        keep, drop = md.dedup_calls(calls)
        clients = md.build_clients(orders, keep)

        assert len(orders) == 2
        assert len(calls) == 3
        assert len(keep) == 2          # дубль sha256 убран
        assert len(drop) == 1
        assert len(clients) == 3       # 2 из заказов + 1 из unmatched-звонка
        by_phone = {c["phone"]: c for c in clients}
        assert by_phone["79001112233"]["name"] == "А"
        assert by_phone["79009998877"]["name"] is None
    finally:
        shutil.rmtree(td, ignore_errors=True)


if __name__ == "__main__":
    test_migration_logic()
    print("test_migrate_data: OK")
