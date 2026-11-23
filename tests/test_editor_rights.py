"""Права на правки: белый список Telegram-ID (crm_editors).

Проверяем цепочку: подписанный initData -> user.id -> таблица -> can_edit/403.
База не нужна: repo.get_editor/is_editor подменяются.
"""
import hashlib
import hmac
import json
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from crm import app as crm_app
from crm.app import app
from crm.auth import init_data_user

TOKEN = "12345:TEST_BOT_TOKEN"
OWNER_ID = 828432096


def _sign(params, token=TOKEN):
    data_check = "\n".join(f"{k}={params[k]}" for k in sorted(params))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    return hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()


def _init_data(user_id, token=TOKEN):
    params = {
        "user": json.dumps({"id": user_id, "first_name": "Тест"}, ensure_ascii=False),
        "auth_date": "1720000000",
        "query_id": "q1",
    }
    return "&".join(f"{k}={quote(v, safe='')}" for k, v in params.items()) + f"&hash={_sign(params, token)}"


def test_init_data_user_returns_id():
    user = init_data_user(_init_data(OWNER_ID), TOKEN)
    assert user is not None and user["id"] == OWNER_ID


def test_init_data_user_rejects_tamper():
    assert init_data_user(_init_data(OWNER_ID).replace(str(OWNER_ID), "1"), TOKEN) is None
    assert init_data_user(_init_data(1, "other:token"), TOKEN) is None
    assert init_data_user("", TOKEN) is None


def test_api_me_allows_listed(monkeypatch):
    monkeypatch.setattr(crm_app, "TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setattr(
        crm_app.repo, "get_editor", lambda tid: {"role": "admin"} if tid == OWNER_ID else None
    )
    r = TestClient(app).get("/api/me", headers={"X-Telegram-Init-Data": _init_data(OWNER_ID)})
    assert r.status_code == 200
    assert r.json()["can_edit"] is True
    assert r.json()["role"] == "admin"


def test_api_me_denies_unknown(monkeypatch):
    monkeypatch.setattr(crm_app, "TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setattr(crm_app.repo, "get_editor", lambda tid: None)
    r = TestClient(app).get("/api/me", headers={"X-Telegram-Init-Data": _init_data(555)})
    assert r.status_code == 200
    assert r.json()["can_edit"] is False
    assert r.json()["role"] is None


def test_api_me_requires_signature(monkeypatch):
    monkeypatch.setattr(crm_app, "TELEGRAM_BOT_TOKEN", TOKEN)
    assert TestClient(app).get("/api/me").status_code == 401
    bad = TestClient(app).get(
        "/api/me", headers={"X-Telegram-Init-Data": "user=%7B%22id%22%3A1%7D&hash=deadbeef"}
    )
    assert bad.status_code == 401


def test_require_editor_closed_by_default(monkeypatch):
    monkeypatch.setattr(crm_app, "TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setattr(crm_app.repo, "is_editor", lambda tid: False)
    with pytest.raises(HTTPException) as err:
        crm_app.require_editor(user={"id": 555})
    assert err.value.status_code == 403


def test_require_editor_allows_listed(monkeypatch):
    monkeypatch.setattr(crm_app, "TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setattr(crm_app.repo, "is_editor", lambda tid: tid == OWNER_ID)
    assert crm_app.require_editor(user={"id": OWNER_ID})["id"] == OWNER_ID
