"""orders-webhook — приём заказов Tilda (FastAPI)."""
import logging
import os
import uuid

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from orders_webhook import gsheets_pull
from orders_webhook.service import upsert_bso, upsert_order
from shared.gsheets import parse_gsheets_bso
from shared.health import check_db, check_s3
from shared.logging_config import set_trace_id, setup_logging
from shared.mailer import log_mail_config
from shared.tilda import parse_tilda_order

setup_logging()
log = logging.getLogger("orders_webhook.app")

# Разовая диагностика отправки писем в логе старта сервиса: включена ли отправка,
# с какого адреса и куда шлём (Postbox), на месте ли шаблон и картинка.
log_mail_config()

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
    """Приём строки БСО из Google Apps Script (авторизация — заголовок X-Gsheets-Secret).

    Оставлен для совместимости: штатный путь теперь — забор из таблицы
    (`orders_webhook.gsheets_pull`), скрипт-отправитель не нужен.
    """
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


@app.post("/webhook/gsheets/pull")
async def gsheets_pull_now(x_gsheets_secret: str | None = Header(default=None)):
    """Ручной прогон забора БСО из Google-таблицы (авторизация — тот же секрет).

    Нужен для проверки: приходит то же, что делает фоновый цикл, но сразу и с ответом.
    """
    set_trace_id(uuid.uuid4().hex)

    if GSHEETS_SECRET and x_gsheets_secret != GSHEETS_SECRET:
        raise HTTPException(status_code=403, detail="forbidden")

    try:
        return await run_in_threadpool(gsheets_pull.pull_once)
    except Exception as exc:  # noqa: BLE001
        log.exception("ручной прогон забора БСО упал")
        raise HTTPException(status_code=500, detail=f"pull failed: {type(exc).__name__}")
