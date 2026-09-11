import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared.serialize import json_safe, serialize_order, serialize_row


def test_json_safe():
    assert json_safe(Decimal("5000.00")) == 5000.0
    assert json_safe(date(2026, 8, 16)) == "2026-08-16"
    assert json_safe(datetime(2026, 8, 16, 10, 0)) == "2026-08-16T10:00:00"
    assert json_safe("str") == "str"
    assert json_safe(None) is None


def test_serialize_order_structure():
    row = {
        "id": 1, "order_id": "123", "order_status": "paid",
        "payment_amount": Decimal("5000.00"), "payment_currency": "RUB",
        "payment_system": "tinkoff", "payment_transaction_id": "txn1",
        "order_date": date(2026, 8, 16),
        "customer_name": "Евгения", "customer_email": "e@x.ru",
        "customer_phone": "79037335471",
        "game": "Лазертаг", "tent": "Беседка", "session_time": "Утро",
        "qty": "8", "extra_fields": {}, "received_at": None,
    }
    o = serialize_order(row)
    # legacy-фронтенд ожидает эти вложенные блоки
    assert o["order_id"] == "123"
    assert o["status"] == "paid"
    assert o["payment"]["amount"] == 5000.0
    assert o["payment"]["currency"] == "RUB"
    assert o["payment"]["system"] == "tinkoff"
    assert o["customer"]["name"] == "Евгения"
    assert o["customer"]["phone"] == "79037335471"
    assert o["event"]["date"] == "2026-08-16"
    assert o["event"]["game"] == "Лазертаг"
    assert o["event"]["session"] == "Утро"
    assert o["event"]["qty"] == "8"


def test_serialize_row():
    assert serialize_row({"a": Decimal("1.5"), "b": date(2026, 1, 1)}) == {"a": 1.5, "b": "2026-01-01"}


if __name__ == "__main__":
    test_json_safe()
    test_serialize_order_structure()
    test_serialize_row()
    print("test_serialize: OK")
