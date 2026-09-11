"""Нормализация дат (единое ядро)."""
from datetime import datetime


def normalize_order_date(value):
    """Tilda DD.MM.YYYY -> ISO YYYY-MM-DD; ISO проходит как есть; иначе как есть."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    # Неожиданное значение оставляем видимым, не портим молча.
    return value
