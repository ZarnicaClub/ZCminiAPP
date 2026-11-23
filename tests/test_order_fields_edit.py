"""Правка полей заказа (сеанс, игроки, тариф, размещение) и история.

База не нужна: repo.dictionaries / edit_order_fields / order_edits подменяются.
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
from crm.app import app

TOKEN = "12345:TEST_BOT_TOKEN"
OWNER_ID = 828432096

DICTS = {
    "session_time": [{"value": "- Утренний с 9:00 до 14:45;", "count": 47},
                     {"value": "- День с 09:00 до 17:00", "count": 5}],
    "game": [{"value": "Пейнтбол Стандарт Плюс", "count": 46},
             {"value": "Лазертаг", "count": 8}],
    "tent": [{"value": "Без размещения в платной зоне", "count": 40},
             {"value": "Беседка до 20 человек", "count": 18}],
    "qty": [{"value": "10", "count": 25}],
}


def _sign(params, token=TOKEN):
    data_check = "\n".join(f"{k}={params[k]}" for k in sorted(params))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    return hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()


def _init_data(user_id, token=TOKEN):
    params = {"user": json.dumps({"id": user_id, "first_name": "Тест"}, ensure_ascii=False),
              "auth_date": "1720000000", "query_id": "q1"}
    return "&".join(f"{k}={quote(v, safe='')}" for k, v in params.items()) + f"&hash={_sign(params, token)}"


def _headers(user_id=OWNER_ID):
    return {"X-Telegram-Init-Data": _init_data(user_id)}


def _allow(monkeypatch, allowed=True):
    monkeypatch.setattr(crm_app, "TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setattr(crm_app.repo, "is_editor", lambda tid: allowed and tid == OWNER_ID)
    monkeypatch.setattr(crm_app.repo, "dictionaries", lambda: DICTS)


def test_edit_fields_ok(monkeypatch):
    _allow(monkeypatch)
    seen = {}

    def fake(order_id, changes, edited_by):
        seen.update(order_id=order_id, changes=changes, by=edited_by)
        return [{"field": f, "old": "старое", "new": v} for f, v in changes.items()]

    monkeypatch.setattr(crm_app.repo, "edit_order_fields", fake)
    r = TestClient(app).patch("/api/orders/1444418991/fields", headers=_headers(),
                              json={"qty": 10, "game": "Лазертаг"})
    assert r.status_code == 200
    assert seen["changes"] == {"qty": "10", "game": "Лазертаг"}
    assert seen["by"] == OWNER_ID
    assert len(r.json()["changes"]) == 2


def test_edit_fields_403_for_stranger(monkeypatch):
    _allow(monkeypatch)
    r = TestClient(app).patch("/api/orders/1/fields", headers=_headers(555), json={"qty": 10})
    assert r.status_code == 403


@pytest.mark.parametrize("payload", [{"qty": 0}, {"qty": 501}, {"qty": "abc"}, {"qty": ""},
                                     {"game": "Несуществующий тариф"},
                                     {"tent": "Трон"}, {"session_time": "Ночь"},
                                     {"unknown": "x"}, {}])
def test_edit_fields_400(monkeypatch, payload):
    _allow(monkeypatch)
    monkeypatch.setattr(crm_app.repo, "edit_order_fields", lambda *a: [])
    r = TestClient(app).patch("/api/orders/1/fields", headers=_headers(), json=payload)
    assert r.status_code == 400


def test_edit_fields_404(monkeypatch):
    _allow(monkeypatch)
    monkeypatch.setattr(crm_app.repo, "edit_order_fields", lambda *a: None)
    r = TestClient(app).patch("/api/orders/нет/fields", headers=_headers(), json={"qty": 10})
    assert r.status_code == 404


def test_edit_fields_requires_auth(monkeypatch):
    monkeypatch.setattr(crm_app, "TELEGRAM_BOT_TOKEN", TOKEN)
    r = TestClient(app).patch("/api/orders/1/fields", json={"qty": 10})
    assert r.status_code == 401


def test_history_visible_to_any_authorized(monkeypatch):
    monkeypatch.setattr(crm_app, "TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setattr(crm_app.repo, "order_edits", lambda oid, limit=200: [
        {"id": 1, "field": "order_date", "old_value": "2012-12-07", "new_value": "2026-12-07",
         "edited_by": OWNER_ID, "edited_at": "2026-11-23T09:46:43+00:00", "editor_name": "Артём"}
    ])
    r = TestClient(app).get("/api/orders/1444418991/edits", headers=_headers(999))
    assert r.status_code == 200 and len(r.json()["edits"]) == 1
    assert TestClient(app).get("/api/orders/1444418991/edits").status_code == 401


def test_dictionaries_requires_auth(monkeypatch):
    monkeypatch.setattr(crm_app, "TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setattr(crm_app.repo, "dictionaries", lambda: DICTS)
    assert TestClient(app).get("/api/dictionaries", headers=_headers()).status_code == 200
    assert TestClient(app).get("/api/dictionaries").status_code == 401
