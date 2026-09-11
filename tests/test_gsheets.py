import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared.gsheets import parse_gsheets_bso


def test_normalized_json():
    b = parse_gsheets_bso({
        "order_id": 1624763921,
        "game_date": "2026-08-13",
        "order_amount": 19000,
        "bso_number": "1449",
        "players_fact": 8,
        "customer_name": "Юля",
        "rest_zone_amount": None,
    })
    assert b is not None
    assert b.order_id == "1624763921"
    assert b.game_date == "2026-08-13"
    assert b.order_amount == 19000.0
    assert b.bso_number == "1449"
    assert b.players_fact == 8
    assert b.customer_name == "Юля"
    assert b.rest_zone_amount is None


def test_dirty_strings():
    b = parse_gsheets_bso({
        "order_id": "1624763921",
        "game_date": "13.08.2026",
        "order_amount": "19 000,00",
        "bso_number": 1449,
        "players_fact": "8",
        "customer_name": " Юля ",
        "rest_zone_amount": " 1 500,50 ",
    })
    assert b is not None
    assert b.game_date == "2026-08-13"
    assert b.order_amount == 19000.0
    assert b.bso_number == "1449"
    assert b.players_fact == 8
    assert b.customer_name == "Юля"
    assert b.rest_zone_amount == 1500.5


def test_missing_order_id():
    assert parse_gsheets_bso({"game_date": "2026-08-13"}) is None
    assert parse_gsheets_bso({}) is None
    assert parse_gsheets_bso(None) is None
    assert parse_gsheets_bso("x") is None
    assert parse_gsheets_bso({"order_id": ""}) is None


if __name__ == "__main__":
    test_normalized_json()
    test_dirty_strings()
    test_missing_order_id()
    print("test_gsheets: OK")
