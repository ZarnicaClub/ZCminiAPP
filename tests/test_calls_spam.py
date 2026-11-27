"""Спам-звонки: скрыть из CRM, оставить в базе (решения 1В / 2А / 3Б, 25.11.2026).

База не нужна: `repo._query/_execute` и API-зависимости подменяются.
"""
import hashlib
import hmac
import json
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from crm import app as crm_app
from crm import repo
from crm.app import app

TOKEN = "12345:TEST_BOT_TOKEN"
EDITOR_ID = 828432096
OTHER_ID = 111222333


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


def _headers(user_id):
    return {"X-Telegram-Init-Data": _init_data(user_id)}


@pytest.fixture
def editor_only(monkeypatch):
    monkeypatch.setattr(crm_app, "TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setattr(crm_app.repo, "is_editor", lambda tid: tid == EDITOR_ID)


def test_скрыть_может_только_редактор(editor_only):
    r = TestClient(app).post(f"/api/calls/1/spam", json={"hidden": True}, headers=_headers(OTHER_ID))
    assert r.status_code == 403


def test_редактор_скрывает_звонок(editor_only, monkeypatch):
    calls = []

    def fake_set(call_id, hidden=True, user=None):
        calls.append((call_id, hidden, user.get("id")))
        return {"status": "ok", "hidden": hidden}

    monkeypatch.setattr(crm_app.repo, "set_call_spam", fake_set)
    r = TestClient(app).post("/api/calls/42/spam", json={"hidden": True}, headers=_headers(EDITOR_ID))
    assert r.status_code == 200 and r.json()["hidden"] is True
    assert calls == [(42, True, EDITOR_ID)]


def test_привязанный_к_заказу_не_скрывается(editor_only, monkeypatch):
    monkeypatch.setattr(crm_app.repo, "set_call_spam", lambda *a, **kw: {"status": "linked"})
    r = TestClient(app).post("/api/calls/42/spam", json={"hidden": True}, headers=_headers(EDITOR_ID))
    assert r.status_code == 409
    assert r.json()["detail"] == "call_linked_to_order"


def test_несуществующий_звонок_404(editor_only, monkeypatch):
    monkeypatch.setattr(crm_app.repo, "set_call_spam", lambda *a, **kw: {"status": "not_found"})
    r = TestClient(app).post("/api/calls/999/spam", json={"hidden": True}, headers=_headers(EDITOR_ID))
    assert r.status_code == 404


def test_скрытые_не_отдаются_без_прав(editor_only):
    r = TestClient(app).get("/api/calls/today?include_spam=1", headers=_headers(OTHER_ID))
    assert r.status_code == 403


def test_редактор_видит_скрытые(editor_only, monkeypatch):
    seen = {}

    def fake_calls(limit=200, date_str=None, include_spam=False):
        seen["include_spam"] = include_spam
        return []

    monkeypatch.setattr(crm_app.repo, "calls_today", fake_calls)
    monkeypatch.setattr(crm_app.repo, "spam_count", lambda date_str=None: 2)
    r = TestClient(app).get("/api/calls/today?include_spam=1", headers=_headers(EDITOR_ID))
    assert r.status_code == 200
    assert r.json()["spam_count"] == 2
    assert seen["include_spam"] is True


def test_set_call_spam_не_трогает_привязанный(monkeypatch):
    monkeypatch.setattr(repo, "_query", lambda sql, params=None: [{"order_id": "1714607951"}])
    written = []
    monkeypatch.setattr(repo, "_execute", lambda sql, params=None: written.append(sql) or 1)
    assert repo.set_call_spam(1, hidden=True, user={"id": 1})["status"] == "linked"
    assert written == []


def test_set_call_spam_пишет_метку_и_снимает(monkeypatch):
    monkeypatch.setattr(repo, "_query", lambda sql, params=None: [{"order_id": None}])
    written = []
    monkeypatch.setattr(repo, "_execute", lambda sql, params=None: written.append((sql, params)) or 1)

    assert repo.set_call_spam(7, hidden=True, user={"id": 5, "first_name": "Артём"})["status"] == "ok"
    assert "jsonb_build_object('spam'" in written[0][0]
    assert json.loads(written[0][1][0])["by"] == 5

    assert repo.set_call_spam(7, hidden=False, user={"id": 5})["status"] == "ok"
    assert "- 'spam'" in written[1][0]
