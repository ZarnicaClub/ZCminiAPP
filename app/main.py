"""zc-app (13.0) — объединённое приложение: CRM (Mini App + API) и приём данных.

Раньше это были два отдельных сервиса App Platform (`crm` и `orders_webhook`),
которые ходят в одну и ту же БД через общий `shared/`. Логика не меняется:
меняется только то, что теперь это один процесс на одном порту и один инстанс.

Маршруты (пути сохранены как были):
    /                       — Mini App
    /static/app.js, /static/style.css
    /api/*                  — API CRM (авторизация Telegram initData)
    /webhook/tilda/{secret} — приём заказов Tilda
    /webhook/gsheets        — приём строк БСО из Google Apps Script
    /healthz                — проверка БД и S3 (общий для обоих сервисов)
"""
from fastapi import FastAPI

from crm.app import app as crm_app
from orders_webhook.app import app as webhook_app

APP_VERSION = "13.0"

app = FastAPI(title="zc-app", version=APP_VERSION)

# 1) CRM: "/", "/static/*", "/api/*" и /healthz (БД + S3).
app.include_router(crm_app.router)

# 2) Приём данных: "/webhook/tilda/{secret}", "/webhook/gsheets".
#    /healthz у webhook-приложения не дублируем — он идентичен crm-овскому.
for route in webhook_app.router.routes:
    if getattr(route, "path", None) != "/healthz":
        app.router.routes.append(route)
