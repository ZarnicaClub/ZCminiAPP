"""Валидация Telegram WebApp initData (HMAC-SHA256)."""
import hashlib
import hmac
from urllib.parse import unquote


def validate_init_data(init_data: str, bot_token: str) -> bool:
    """Проверяет подпись Telegram initData."""
    if not init_data or not bot_token:
        return False
    params = {}
    for pair in init_data.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            params[k] = unquote(v)
    received = params.pop("hash", None)
    if not received:
        return False
    data_check_string = "\n".join(f"{k}={params[k]}" for k in sorted(params))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(calc, received)
