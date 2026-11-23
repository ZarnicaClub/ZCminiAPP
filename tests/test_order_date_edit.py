"""Правка даты игры: только редактор, валидация, 404 и журнал.

База не нужна: crm.repo.edit_order_date подменяется.
"""
import hashlib
import hmac
import json
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient

from crm import app as crm_app
from crm.app import app

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


def _patch(client, order_id, body, user_id=OWNER_ID):
    return client.patch(
        f"/api/orders/{order_id}/date",
        headers={"X-Telegram-Init-Data": _init_data(user_id)},
        json=body,
    )


def _allow_editor(monkeypatch, allowed=True):
    monkeypatch.setattr(crm_app, "TELEGRAM_BOT_TOKEN", TOKEN)
    monkeypatch.setattr(crm_app.repo, "is_editor", lambda tid: allowed and tid == OWNER_ID)


def test_editor_changes_date(monkeypatch):
    _allow_editor(monkeypatch)
    calls = {}

    def fake(order_id, new_date, edited_by):
        calls.update(order_id=order_id, new=new_date, by=edited_by)
        return {"old": date(2012, 12, 7), "new": new_date, "changed": True}

    monkeypatch.setattr(crm_app.repo, "edit_order_date", fake)
    r = _patch(TestClient(app), "1444418991", {"date": "2026-12-07"})
    assert r.status_code == 200
    assert r.json() == {
        "ok": True,
        "order_id": "1444418991",
        "old_date": "2012-12-07",
        "new_date": "2026-12-07",
        "changed": True,
    }
    assert calls == {"order_id": "1444418991", "new": date(2026, 12, 7), "by": OWNER_ID}


def test_stranger_gets_403(monkeypatch):
    _allow_editor(monkeypatch)
    r = _patch(TestClient(app), "1444418991", {"date": "2026-12-07"}, user_id=555)
    assert r.status_code == 403


def test_same_date_is_noop(monkeypatch):
    _allow_editor(monkeypatch)
    monkeypatch.setattr(
        crm_app.repo,
        "edit_order_date",
        lambda oid, nd, by: {"old": date(2026, 12, 7), "new": nd, "changed": False},
    )
    r = _patch(TestClient(app), "1444418991", {"date": "2026-12-07"})
    assert r.status_code == 200 and r.json()["changed"] is False


@pytest.mark.parametrize("bad", ["07.12.2026", "2026-13-01", "2026-02-30", "", None, 20261207])
def test_bad_date_is_400(monkeypatch, bad):
    _allow_editor(monkeypatch)
    r = _patch(TestClient(app), "1444418991", {"date": bad})
    assert r.status_code == 400


def test_unknown_order_is_404(monkeypatch):
    _allow_editor(monkeypatch)
    monkeypatch.setattr(crm_app.repo, "edit_order_date", lambda oid, nd, by: None)
    r = _patch(TestClient(app), "нет-такого", {"date": "2026-12-07"})
    assert r.status_code == 404


def test_without_init_data_is_401(monkeypatch):
    monkeypatch.setattr(crm_app, "TELEGRAM_BOT_TOKEN", TOKEN)
    r = TestClient(app).patch("/api/orders/1444418991/date", json={"date": "2026-12-07"})
    assert r.status_code == 401
