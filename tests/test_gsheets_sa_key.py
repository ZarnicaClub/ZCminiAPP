"""Тесты разбора ключа сервисного аккаунта (gsheets_pull._parse_sa_text).

Ключ в панели переменных сохраняется длинной строкой и легко портится при копировании:
теряются «=» в конце, добавляются кавычки или переводы строк. Разбор должен это пережить,
иначе забор БСО молча не работает (проверено на проде 28.09.2026).
"""
import base64
import json

from orders_webhook.gsheets_pull import _parse_sa_text

SA = {"type": "service_account", "client_email": "robot@example.iam.gserviceaccount.com",
      "private_key": "-----BEGIN PRIVATE KEY-----\nMIIB\n-----END PRIVATE KEY-----\n",
      "project_id": "balancezc"}


def _b64(raw: dict) -> str:
    return base64.b64encode(json.dumps(raw).encode()).decode()


def test_base64_как_есть():
    assert _parse_sa_text(_b64(SA))["client_email"] == SA["client_email"]


def test_потерянное_выравнивание():
    assert _parse_sa_text(_b64(SA).rstrip("="))["project_id"] == "balancezc"


def test_кавычки_и_пробелы():
    assert _parse_sa_text(f'"{_b64(SA)}"')["project_id"] == "balancezc"
    assert _parse_sa_text("  " + _b64(SA) + "\n")["client_email"] == SA["client_email"]


def test_переносы_строк_внутри():
    b64 = _b64(SA)
    рваной = "\n".join(b64[i:i + 76] for i in range(0, len(b64), 76))
    assert _parse_sa_text(рваной)["type"] == "service_account"


def test_base64url():
    assert _parse_sa_text(base64.urlsafe_b64encode(json.dumps(SA).encode()).decode())["project_id"] == "balancezc"


def test_чистый_json():
    assert _parse_sa_text(json.dumps(SA))["client_email"] == SA["client_email"]


def test_мусор_не_роняет():
    assert _parse_sa_text("") is None
    assert _parse_sa_text("не base64 и не json") is None
    assert _parse_sa_text(None) is None
