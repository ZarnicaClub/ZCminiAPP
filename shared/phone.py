"""Единая нормализация телефона для всех сервисов newCRM.

Правила зафиксированы в contracts/samples/README.md:
- 10 цифр, начинается с 9  -> 7 + цифры
- 11 цифр, начинается с 8  -> 7 + последние 10
- 11 цифр, начинается с 7  -> как есть
- иначе                    -> None (невалидный)
"""
import re

_NON_DIGITS = re.compile(r"\D+")


def normalize_phone(value) -> str | None:
    """Приводит номер к каноническому виду 7XXXXXXXXXX."""
    if value is None:
        return None
    digits = _NON_DIGITS.sub("", str(value))
    if len(digits) == 10 and digits.startswith("9"):
        return "7" + digits
    if len(digits) == 11 and digits.startswith("8"):
        return "7" + digits[1:]
    if len(digits) == 11 and digits.startswith("7"):
        return digits
    return None
