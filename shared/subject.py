"""Парсинг темы письма со звонком.

Формат: `Запись разговора DD.MM.YYYY HH:MM:SS PHONE ADMINISTRATOR`.
"""
import re
from datetime import datetime, timedelta, timezone

from .phone import normalize_phone

SUBJECT_RE = re.compile(
    r"Запись\s+разговора\s+"
    r"(?P<date>\d{2}\.\d{2}\.\d{4})\s+"
    r"(?P<time>\d{2}:\d{2}:\d{2})\s+"
    r"(?P<phone>\+?\d[\d\s()\-]{9,}\d)\s+"
    r"(?P<administrator>.+?)\s*$",
    re.IGNORECASE,
)


def _parse_offset(offset: str) -> timezone:
    """Разбирает CALL_TIMEZONE_OFFSET вида '+03:00' (или '03:00')."""
    offset = (offset or "+03:00").strip()
    if offset[0] not in "+-":
        offset = "+" + offset
    sign = 1 if offset[0] == "+" else -1
    hh, mm = map(int, offset[1:].split(":"))
    return timezone(sign * timedelta(hours=hh, minutes=mm))


def parse_subject(subject: str, timezone_offset: str = "+03:00"):
    """Возвращает dict(call_datetime, phone, administrator) или None."""
    m = SUBJECT_RE.search(subject or "")
    if not m:
        return None
    phone = normalize_phone(m.group("phone"))
    if not phone:
        return None
    dt = datetime.strptime(
        f'{m.group("date")} {m.group("time")}', "%d.%m.%Y %H:%M:%S"
    )
    dt = dt.replace(tzinfo=_parse_offset(timezone_offset))
    return {
        "call_datetime": dt.isoformat(),
        "phone": phone,
        "administrator": m.group("administrator").strip(),
    }
