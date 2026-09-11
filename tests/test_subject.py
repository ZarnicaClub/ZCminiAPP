import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.subject import parse_subject


def test_parse_subject():
    r = parse_subject("Запись разговора 11.08.2026 14:48:01 +79851297771 Мария Коробова")
    assert r is not None
    assert r["phone"] == "79851297771"
    assert r["administrator"] == "Мария Коробова"
    assert r["call_datetime"] == "2026-08-11T14:48:01+03:00"


def test_parse_subject_offset():
    r = parse_subject(
        "Запись разговора 11.08.2026 14:48:01 +79851297771 Мария Коробова",
        timezone_offset="+05:00",
    )
    assert r["call_datetime"] == "2026-08-11T14:48:01+05:00"


def test_parse_subject_invalid():
    assert parse_subject("Не запись разговора") is None
    assert parse_subject("") is None


if __name__ == "__main__":
    test_parse_subject()
    test_parse_subject_offset()
    test_parse_subject_invalid()
    print("test_subject: OK")
