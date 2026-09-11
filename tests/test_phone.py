"""Регрессионные тесты нормализации телефона (единое ядро)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from shared.phone import normalize_phone


def test_normalize_phone():
    cases = [
        ("89037335471", "79037335471"),      # 8-префикс
        ("+79175307576", "79175307576"),     # +7
        ("+7 (909) 777-00-05", "79097770005"),
        ("8-916-759-00-05", "79167590005"),
        ("9257720257", "79257720257"),       # 10 цифр с 9
        ("79775767828", "79775767828"),      # уже канонический
        ("74951397975", "74951397975"),      # городской +7 495
        ("", None),
        ("abc", None),
        (None, None),
    ]
    for raw, expected in cases:
        got = normalize_phone(raw)
        assert got == expected, f"{raw!r} -> {got!r} != {expected!r}"


if __name__ == "__main__":
    test_normalize_phone()
    print("test_phone: OK")
