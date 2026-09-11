"""Парсинг payload Tilda -> нормализованный OrderIn."""
import json
from typing import Any, Optional

from .contracts import OrderIn
from .date import normalize_order_date
from .phone import normalize_phone

ORDER_KNOWN_KEYS = {
    "payment", "orderid", "order_id", "name", "email", "phone", "date",
    "payment_status", "status", "amount", "systempayment", "paymentid",
    "payment_id", "game", "tent", "выберите_сеанс", "qty",
}
DROPPED_KEY_PREFIXES = ("checkbox",)


def get_ci(d: Any, *keys, default=None):
    """Регистронезависимое чтение ключа."""
    if not isinstance(d, dict):
        return default
    lower = {str(k).lower(): v for k, v in d.items()}
    for key in keys:
        if str(key).lower() in lower:
            return lower[str(key).lower()]
    return default


def parse_payment(data: dict) -> dict:
    raw = get_ci(data, "payment")
    if raw:
        try:
            p = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(p, dict):
                return p
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


def _is_dropped_key(key) -> bool:
    return str(key).lower().startswith(DROPPED_KEY_PREFIXES)


def _to_float(v) -> Optional[float]:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_tilda_order(data: dict) -> Optional[OrderIn]:
    """Принимает JSON- или form-пайлоад; возвращает OrderIn или None (нет order_id)."""
    if not isinstance(data, dict):
        return None
    payment = parse_payment(data)
    order_id = get_ci(payment, "orderid") or get_ci(data, "orderid", "order_id")
    if not order_id:
        return None

    amount = get_ci(payment, "amount") or get_ci(data, "amount")
    status = get_ci(data, "payment_status", "status") or get_ci(payment, "status")
    if not status and amount:
        status = "paid"

    extra = {
        k: v for k, v in data.items()
        if str(k).lower() not in ORDER_KNOWN_KEYS and not _is_dropped_key(k)
    }

    return OrderIn(
        order_id=str(order_id),
        order_status=status,
        payment_amount=_to_float(amount),
        payment_currency=get_ci(payment, "currency") or "RUB",
        payment_system=(
            get_ci(payment, "sys", "systempayment", "system")
            or get_ci(data, "systempayment")
        ),
        payment_transaction_id=get_ci(payment, "systranid"),
        order_date=normalize_order_date(get_ci(data, "date")),
        customer_name=get_ci(data, "name"),
        customer_email=get_ci(data, "email"),
        customer_phone=normalize_phone(get_ci(data, "phone")),
        game=get_ci(data, "game"),
        tent=get_ci(data, "tent"),
        session_time=get_ci(data, "Выберите_сеанс"),
        qty=get_ci(data, "qty"),
        extra_fields=extra,
        raw_payload=data,
    )
