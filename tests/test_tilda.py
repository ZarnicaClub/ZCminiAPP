import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared.tilda import parse_tilda_order


def test_json_payload():
    sample = json.loads(
        (ROOT / "contracts" / "samples" / "tilda_payload.json").read_text(encoding="utf-8-sig")
    )
    o = parse_tilda_order(sample)
    assert o is not None
    assert o.order_id == "1221926939"
    assert o.customer_phone == "79027250497"   # из 89027250497
    assert o.order_date == "2026-08-15"        # из 15.08.2026
    assert o.payment_system == "tinkoff"
    assert o.payment_amount == 5000.0
    assert o.customer_name == "Галина"


def test_form_payload():
    o = parse_tilda_order({
        "name": "Тест",
        "phone": "89161234567",
        "date": "20.08.2026",
        "payment": '{"orderid":"12345","amount":"5000","sys":"tinkoff"}',
    })
    assert o is not None
    assert o.order_id == "12345"
    assert o.customer_phone == "79161234567"
    assert o.order_date == "2026-08-20"
    assert o.order_status == "paid"


def test_missing_order_id():
    assert parse_tilda_order({"name": "X"}) is None
    assert parse_tilda_order(None) is None
    assert parse_tilda_order({}) is None


if __name__ == "__main__":
    test_json_payload()
    test_form_payload()
    test_missing_order_id()
    print("test_tilda: OK")
