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
    /healthz                — мгновенный ответ для проверки состояния платформой
    /healthz/deep           — глубокая проверка (БД + S3) для внешнего мониторинга
"""
from fastapi import FastAPI

from crm.app import app as crm_app
from orders_webhook.app import app as webhook_app
from shared.health import check_db, check_s3

APP_VERSION = "13.0"

app = FastAPI(title="zc-app", version=APP_VERSION)


# ВАЖНО: /healthz регистрируем ПЕРВЫМ — платформа опрашивает его каждые 30 секунд
# как путь проверки состояния. Он обязан отвечать мгновенно и не зависеть от внешних
# сервисов (требование App Platform). Раньше здесь были походы в БД и S3: если S3
# отвечал медленно, приложение переставая принимать свежие запросы (наблюдали потерю
# ~10-20% запросов). Глубокая проверка переехала в /healthz/deep.
@app.get("/healthz", include_in_schema=False)
def healthz_probe():
    return {"status": "ok"}


@app.get("/healthz/deep", include_in_schema=False)
def healthz_deep():
    return {
        "status": "ok",
        "database": "ok" if check_db() else "error",
        "s3": "ok" if check_s3() else "error",
    }


# CRM: "/", "/static/*", "/api/*" (свой /healthz из crm перекрыт нашим — он выше).
app.include_router(crm_app.router)

# Приём данных: "/webhook/tilda/{secret}", "/webhook/gsheets".
for route in webhook_app.router.routes:
    if getattr(route, "path", None) != "/healthz":
        app.router.routes.append(route)
