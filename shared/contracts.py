"""Контракты (dataclasses — stdlib, единый источник истины)."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class OrderIn:
    """Нормализованный внутренний контракт заказа."""
    order_id: str
    order_status: Optional[str] = None
    payment_amount: Optional[float] = None
    payment_currency: Optional[str] = "RUB"
    payment_system: Optional[str] = None
    payment_transaction_id: Optional[str] = None
    order_date: Optional[str] = None  # ISO YYYY-MM-DD
    customer_name: Optional[str] = None
    customer_email: Optional[str] = None
    customer_phone: Optional[str] = None  # канонический 7XXXXXXXXXX
    game: Optional[str] = None
    tent: Optional[str] = None
    session_time: Optional[str] = None
    qty: Optional[str] = None
    extra_fields: dict[str, Any] = field(default_factory=dict)
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class CallIn:
    """Нормализованный контракт звонка."""
    email_id: str
    phone: str
    call_datetime: datetime
    order_id: Optional[str] = None
    administrator: Optional[str] = None
    mp3_filename: Optional[str] = None
    s3_key: Optional[str] = None
    duration_seconds: Optional[int] = None
    status: str = "unmatched"
    mp3_hash: Optional[str] = None


@dataclass
class BsoIn:
    """Нормализованный контракт строки БСО из Google Sheets."""
    order_id: str
    game_date: Optional[str] = None      # ISO YYYY-MM-DD
    order_amount: Optional[float] = None
    bso_number: Optional[str] = None
    players_fact: Optional[int] = None
    customer_name: Optional[str] = None
    rest_zone_amount: Optional[float] = None


@dataclass
class ClientOut:
    client_id: int
    phone: str
    name: Optional[str] = None
    email: Optional[str] = None
