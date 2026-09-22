"""orders-webhook — приём заказов Tilda (FastAPI)."""
import logging
import os
import uuid

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request

from orders_webhook.service import upsert_bso, upsert_order
from shared.gsheets import parse_gsheets_bso
from shared.health import check_db, check_s3
from shared.logging_config import set_trace_id, setup_logging
from shared.mailer import log_smtp_config
from shared.tilda import parse_tilda_order

setup_logging()
log = logging.getLogger("orders_webhook.app")

# Разовая диагностика SMTP в логе старта сервиса: видно, куда и по каким адресам
# (IPv4/IPv6) сервис будет подключаться, не заходя внутрь контейнера.
log_smtp_config()

app = FastAPI(title="orders-webhook", version="0.1.0")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")
GSHEETS_SECRET = os.getenv("GSHEETS_SECRET")


@app.get("/healthz")
def healthz():
    return {
        "status": "ok",
        "database": "ok" if check_db() else "error",
        "s3": "ok" if check_s3() else "error",
    }


@app.post("/webhook/tilda/{secret}")
async def tilda_webhook(secret: str, request: Request, background: BackgroundTasks):
    set_trace_id(uuid.uuid4().hex)

    if WEBHOOK_SECRET and secret != WEBHOOK_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")

    content_type = request.headers.get("content-type", "")
    try:
        if "application/json" in content_type:
            data = await request.json() or {}
        else:
            data = dict(await request.form())
    except Exception:
        raise HTTPException(status_code=400, detail="cannot parse body")

    if not data:
        raise HTTPException(status_code=400, detail="empty payload")

    order = parse_tilda_order(data)
    if order is None:
        log.warning("no order_id in payload, skipping")
        return {"status": "skipped", "reason": "missing order_id"}

    try:
        upsert_order(order, background)
    except Exception:
        log.exception("failed to save order")
        raise HTTPException(status_code=500, detail="internal error")

    return {"status": "ok"}


@app.post("/webhook/gsheets")
async def gsheets_webhook(request: Request, x_gsheets_secret: str | None = Header(default=None)):
    """Приём строки БСО из Google Apps Script (авторизация — заголовок X-Gsheets-Secret)."""
    set_trace_id(uuid.uuid4().hex)

    if GSHEETS_SECRET and x_gsheets_secret != GSHEETS_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")

    try:
        data = await request.json() or {}
    except Exception:
        raise HTTPException(status_code=400, detail="cannot parse body")

    if not data:
        raise HTTPException(status_code=400, detail="empty payload")

    bso = parse_gsheets_bso(data)
    if bso is None:
        log.warning("no order_id in payload, skipping")
        return {"status": "skipped", "reason": "missing order_id"}

    try:
        result = upsert_bso(bso)
    except Exception:
        log.exception("failed to save bso")
        raise HTTPException(status_code=500, detail="internal error")

    return result
