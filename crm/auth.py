"""Валидация Telegram WebApp initData (HMAC-SHA256)."""
import hashlib
import hmac
import json
from urllib.parse import unquote


def parse_init_data(init_data: str, bot_token: str) -> dict | None:
    """Проверяет подпись Telegram initData и возвращает параметры.

    None — подпись неверная/данных нет. Проверка только HMAC, кто именно
    пришёл, решает вызывающий код (см. ``init_data_user``).
    """
    if not init_data or not bot_token:
        return None
    params = {}
    for pair in init_data.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            params[k] = unquote(v)
    received = params.pop("hash", None)
    if not received:
        return None
    data_check_string = "\n".join(f"{k}={params[k]}" for k in sorted(params))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, received):
        return None
    return params


def validate_init_data(init_data: str, bot_token: str) -> bool:
    """Проверяет подпись Telegram initData."""
    return parse_init_data(init_data, bot_token) is not None


def init_data_user(init_data: str, bot_token: str) -> dict | None:
    """Возвращает объект ``user`` из подписанного initData (id, имя, username).

    id берётся только из подписанных данных — подделать без токена бота нельзя.
    """
    params = parse_init_data(init_data, bot_token)
    if not params:
        return None
    try:
        user = json.loads(params.get("user") or "{}")
    except (TypeError, ValueError):
        return None
    if not isinstance(user, dict) or not isinstance(user.get("id"), int):
        return None
    return user
