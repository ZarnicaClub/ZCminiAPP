"""Парсинг payload Google Sheets (строка БСО) -> нормализованный BsoIn.

Принимает финальный JSON из Google Apps Script:
{
  "order_id": 1624763921,
  "game_date": "2026-08-13",
  "order_amount": 19000,
  "bso_number": "1449",
  "players_fact": 8,
  "customer_name": "Юля",
  "rest_zone_amount": null
}

Парсер толерантен к строковым/«грязным» значениям (защита от правок в таблице),
но базовый порядок типов задаёт Apps Script.
"""
from typing import Any, Optional

from .contracts import BsoIn
from .date import normalize_order_date


def _to_float(v: Any) -> Optional[float]:
    """Число -> float; '19 000,00' / '19.000,00' -> 19000.0; пусто -> None."""
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    text = str(v).strip().replace("\u00a0", " ").replace(" ", "")
    if not text:
        return None
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _to_int(v: Any) -> Optional[int]:
    """Целое -> int; '8' -> 8; пусто/не-число -> None."""
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _to_str(v: Any) -> Optional[str]:
    if v is None:
        return None
    text = str(v).strip()
    return text or None


def parse_gsheets_bso(data: Any) -> Optional[BsoIn]:
    """Возвращает BsoIn или None, если нет order_id / payload не словарь."""
    if not isinstance(data, dict):
        return None
    order_id = _to_str(data.get("order_id"))
    if not order_id:
        return None
    return BsoIn(
        order_id=order_id,
        game_date=normalize_order_date(data.get("game_date")),
        order_amount=_to_float(data.get("order_amount")),
        bso_number=_to_str(data.get("bso_number")),
        players_fact=_to_int(data.get("players_fact")),
        customer_name=_to_str(data.get("customer_name")),
        rest_zone_amount=_to_float(data.get("rest_zone_amount")),
    )
