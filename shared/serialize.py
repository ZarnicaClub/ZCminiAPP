"""Сериализация в JSON-совместимые значения (общая для сервисов, чистая логика)."""
from datetime import date, datetime
from decimal import Decimal


def json_safe(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def serialize_row(row):
    """Плоский dict -> все значения JSON-safe."""
    return {k: json_safe(v) for k, v in row.items()}


def serialize_order(row):
    """Строка заказа -> legacy-совместимая вложенная структура (для фронтенда)."""
    return {
        "id": row.get("id"),
        "order_id": row.get("order_id"),
        "status": row.get("order_status"),
        "payment": {
            "amount": json_safe(row.get("payment_amount")),
            "currency": row.get("payment_currency"),
            "system": row.get("payment_system"),
            "transaction_id": row.get("payment_transaction_id"),
        },
        "customer": {
            "name": row.get("customer_name"),
            "email": row.get("customer_email"),
            "phone": row.get("customer_phone"),
        },
        "event": {
            "date": json_safe(row.get("order_date")),
            "game": row.get("game"),
            "tent": row.get("tent"),
            "session": row.get("session_time"),
            "qty": row.get("qty"),
        },
        "extra_fields": row.get("extra_fields"),
        "received_at": json_safe(row.get("received_at")),
    }
