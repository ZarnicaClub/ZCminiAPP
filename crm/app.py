"""crm-miniapp — API + Mini App (FastAPI).

Фронтенд встроен в код (crm/webassets.py), поэтому не зависит от наличия
templates/static файлов в контейнере.
"""
import os

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, Response

from crm import auth, repo
from crm.webassets import APP_JS, INDEX_HTML, STYLE_CSS
from shared.health import check_db, check_s3

app = FastAPI(title="crm-miniapp", version="0.1.0")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")


def require_auth(x_telegram_init_data: str | None = Header(default=None)):
    if not TELEGRAM_BOT_TOKEN:
        return  # dev-режим: токен не задан, auth выключен
    if not auth.validate_init_data(x_telegram_init_data or "", TELEGRAM_BOT_TOKEN):
        raise HTTPException(status_code=401, detail="unauthorized")


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
