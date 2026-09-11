import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.date import normalize_order_date


def test_normalize_order_date():
    assert normalize_order_date("16.08.2026") == "2026-08-16"
    assert normalize_order_date("2026-08-16") == "2026-08-16"
    assert normalize_order_date("garbage") == "garbage"
    assert normalize_order_date("") is None
    assert normalize_order_date(None) is None
    assert normalize_order_date("  16.08.2026  ") == "2026-08-16"


if __name__ == "__main__":
    test_normalize_order_date()
    print("test_date: OK")
