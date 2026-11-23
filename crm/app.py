"""crm-miniapp — API + Mini App (FastAPI).

Фронтенд встроен в код (crm/webassets.py), поэтому не зависит от наличия
templates/static файлов в контейнере.
"""
import os
import re
from datetime import date

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, Response

from crm import auth, repo
from crm.webassets import APP_JS, INDEX_HTML, STYLE_CSS
from shared.health import check_db, check_s3

app = FastAPI(title="crm-miniapp", version="0.1.0")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def require_auth(x_telegram_init_data: str | None = Header(default=None)):
    if not TELEGRAM_BOT_TOKEN:
        return  # dev-режим: токен не задан, auth выключен
    if not auth.validate_init_data(x_telegram_init_data or "", TELEGRAM_BOT_TOKEN):
        raise HTTPException(status_code=401, detail="unauthorized")


def current_user(x_telegram_init_data: str | None = Header(default=None)) -> dict:
    """Кто пришёл: объект user из подписанного Telegram initData.

    401 — только если подпись неверная (или токен задан, а initData нет).
    В dev-режиме (токен бота не задан) возвращает пометку dev.
    """
    if not TELEGRAM_BOT_TOKEN:
        return {"id": None, "first_name": "dev", "dev": True}
    user = auth.init_data_user(x_telegram_init_data or "", TELEGRAM_BOT_TOKEN)
    if not user:
        raise HTTPException(status_code=401, detail="unauthorized")
    return user


def require_editor(user: dict = Depends(current_user)) -> dict:
    """Право вносить правки: только белый список crm_editors (закрыто по умолчанию)."""
    if user.get("dev"):
        return user
    if not repo.is_editor(user.get("id")):
        raise HTTPException(status_code=403, detail="editing_forbidden")
    return user


@app.get("/api/me")
def api_me(user: dict = Depends(current_user)):
    """Кто я и можно ли мне править — для интерфейса и проверки доступа."""
    row = None
    if not user.get("dev"):
        try:
            row = repo.get_editor(user["id"])
        except Exception:
            row = None  # таблицы ещё нет — прав нет, чтение работает
    name = " ".join(p for p in (user.get("first_name"), user.get("last_name")) if p)
    return {
        "id": user.get("id"),
        "name": name,
        "username": user.get("username"),
        "can_edit": bool(user.get("dev") or row),
        "role": "dev" if user.get("dev") else (row.get("role") if row else None),
    }


@app.patch("/api/orders/{order_id}/date")
def api_edit_order_date(
    order_id: str,
    payload: dict = Body(...),
    user: dict = Depends(require_editor),
):
    """Правка даты игры: только редактор из crm_editors.

    400 — дата не в формате ГГГГ-ММ-ДД; 404 — заказа нет.
    Дата меняется в orders.order_date (вебхук Тильды приходит один раз),
    каждая правка пишется в журнал order_edits.
    """
    raw = payload.get("date") if isinstance(payload, dict) else None
    if not isinstance(raw, str) or not _DATE_RE.match(raw):
        raise HTTPException(status_code=400, detail="invalid_date")
    try:
        new_date = date.fromisoformat(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid_date")
    if not (1990 <= new_date.year <= 2100):
        raise HTTPException(status_code=400, detail="date_out_of_range")
    result = repo.edit_order_date(order_id, new_date, user.get("id"))
    if result is None:
        raise HTTPException(status_code=404, detail="order_not_found")
    return {
        "ok": True,
        "order_id": order_id,
        "old_date": result["old"].isoformat() if result["old"] else None,
        "new_date": raw,
        "changed": result["changed"],
    }


@app.get("/api/dictionaries", dependencies=[Depends(require_auth)])
def api_dictionaries():
    """Значения для выбора: сеансы, тарифы, размещение — из того, что уже есть в заказах."""
    return repo.dictionaries()


@app.get("/api/orders/{order_id}/edits", dependencies=[Depends(require_auth)])
def api_order_edits(order_id: str):
    """История правок заказа — видна всем, кто открывает карточку."""
    return {"order_id": order_id, "edits": repo.order_edits(order_id)}


@app.patch("/api/orders/{order_id}/fields")
def api_edit_order_fields(
    order_id: str,
    payload: dict = Body(...),
    user: dict = Depends(require_editor),
):
    """Правка сеанса, числа игроков, тарифа и размещения — только редактор.

    Сеанс/тариф/размещение принимаются только из существующих значений (словари),
    игроки — целое число 1..500. По каждому изменённому полю — строка в журнале.
    """
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid_payload")
    raw = {k: v for k, v in payload.items() if k in repo.EDIT_FIELDS}
    if not raw:
        raise HTTPException(status_code=400, detail="nothing_to_change")
    dicts = repo.dictionaries()
    changes = {}
    for field, value in raw.items():
        if field == "qty":
            try:
                num = int(str(value).strip())
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="invalid_qty")
            if not (1 <= num <= 500):
                raise HTTPException(status_code=400, detail="invalid_qty")
            changes[field] = str(num)
        else:
            allowed = {d["value"] for d in dicts.get(field, [])}
            if not isinstance(value, str) or value not in allowed:
                raise HTTPException(status_code=400, detail=f"invalid_{field}")
            changes[field] = value
    applied = repo.edit_order_fields(order_id, changes, user.get("id"))
    if applied is None:
        raise HTTPException(status_code=404, detail="order_not_found")
    return {"ok": True, "order_id": order_id, "changes": applied}


@app.get("/healthz")
def healthz():
    return {
        "status": "ok",
        "database": "ok" if check_db() else "error",
        "s3": "ok" if check_s3() else "error",
    }


@app.get("/")
def index():
    return HTMLResponse(INDEX_HTML)


@app.get("/static/app.js")
def app_js():
    return Response(APP_JS, media_type="application/javascript")


@app.get("/static/style.css")
def style_css():
    return Response(STYLE_CSS, media_type="text/css")


@app.get("/api/orders", dependencies=[Depends(require_auth)])
def api_orders(status: str | None = None, date: str | None = None, limit: int = 100):
    limit = min(max(limit, 1), 200)
    orders = repo.list_orders(status=status, event_date=date, limit=limit)
    return {"count": len(orders), "orders": orders}


@app.get("/api/orders/{order_id}", dependencies=[Depends(require_auth)])
def api_order(order_id: str):
    order = repo.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="order_not_found")
    return {"order": order}


@app.get("/api/orders/{order_id}/calls", dependencies=[Depends(require_auth)])
def api_order_calls(order_id: str):
    calls = repo.order_calls(order_id)
    return {"count": len(calls), "calls": calls}


@app.get("/api/orders/{order_id}/bso", dependencies=[Depends(require_auth)])
def api_order_bso(order_id: str):
    return {"bso": repo.get_order_bso(order_id)}


@app.get("/api/clients/{client_id}/bso", dependencies=[Depends(require_auth)])
def api_client_bso(client_id: int):
    bso = repo.client_bso(client_id)
    return {"count": len(bso), "bso": bso}


@app.get("/api/bso", dependencies=[Depends(require_auth)])
def api_bso(limit: int = 200):
    bso = repo.list_bso(limit=min(max(limit, 1), 500))
    return {"count": len(bso), "bso": bso}


@app.get("/api/calendar", dependencies=[Depends(require_auth)])
def api_calendar():
    return {"days": repo.calendar()}


@app.get("/api/clients", dependencies=[Depends(require_auth)])
def api_clients(limit: int = 200):
    clients = repo.list_clients(limit=min(max(limit, 1), 500))
    return {"count": len(clients), "clients": clients}


@app.get("/api/clients/{client_id}/calls", dependencies=[Depends(require_auth)])
def api_client_calls(client_id: int):
    return {"calls": repo.client_calls(client_id)}


@app.get("/api/calls/unmatched", dependencies=[Depends(require_auth)])
def api_unmatched_calls(limit: int = 200):
    return {"calls": repo.unmatched_calls(limit=min(max(limit, 1), 500))}


@app.get("/api/calls/today", dependencies=[Depends(require_auth)])
def api_calls_today(date: str | None = None, limit: int = 200):
    return {"calls": repo.calls_today(limit=min(max(limit, 1), 500), date_str=date)}


@app.get("/api/summary/weekend", dependencies=[Depends(require_auth)])
def api_weekend_summary():
    return {"people": repo.weekend_headcount()}


@app.post("/api/calls/{call_id}/match", dependencies=[Depends(require_auth)])
def api_match_call(call_id: int, order_id: str = Query(...)):
    updated = repo.set_call_order(call_id, order_id)
    if not updated:
        raise HTTPException(status_code=404, detail="call_not_found")
    return {"status": "ok"}
