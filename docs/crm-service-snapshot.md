# Снимок сервиса `crm` (API + Telegram Mini App)

> Это снимок-описание текущего состояния сервиса `crm` на момент фиксации.
> Не является отчётом об изменениях — код не менялся, бэкап/деплой не требуются.

- **Дата фиксации:** 04.09.2026
- **Версия:** v12.17
- **Образ:** `amkorobov/crm:12.17`
- **Статус:** ✅ работает в production (Timeweb App Platform)
- **Путь:** `newCRM\implementation\crm\`

---

## 1. Назначение

Сервис `crm` — третий из трёх сервисов newCRM. Это **API + Telegram Mini App** для менеджера клуба «ЗарницаКлаб»:

- отдаёт данные заказов, клиентов, звонков и БСО в read-only режиме;
- единственный сервис, который делает **записи в БД** — ручное связывание звонка с заказом (`POST /api/calls/{id}/match`);
- отдаёт временные presigned-ссылки на MP3-записи звонков из S3;
- фронтенд **встроен в код** (`crm/webassets.py`), поэтому контейнер не зависит от `templates/` и `static/` на диске.

Место в архитектуре:

```text
Tilda → orders-webhook ─┐
                        ├─ PostgreSQL (clients, orders, calls, orders_bso)
Mail → calls-worker ────┘          │
                        S3 (MP3)  ←┘
Telegram → crm (Mini App) → API → orders/calls → presigned S3 URL
```

---

## 2. Стек и зависимости

| Слой | Технология |
|---|---|
| Язык | Python 3.12 |
| Веб-фреймворк | FastAPI 0.115.5 |
| ASGI-сервер | Uvicorn 0.30.6 |
| БД | psycopg 3.2.9 + psycopg-pool 3.2.3 (PostgreSQL) |
| S3 | boto3 1.40.0 (Signature v4) |
| Прочее | pydantic 2.9.2, python-dotenv, python-json-logger, python-multipart |
| Фронтенд | Vanilla JS + CSS (без фреймворков/сборки) |

Полный список — `requirements.txt`.

---

## 3. Структура файлов

```text
crm/
├── __init__.py        # docstring
├── app.py             # FastAPI-приложение, маршруты, аутентификация
├── auth.py            # валидация Telegram initData (HMAC-SHA256)
├── repo.py            # запросы к PostgreSQL + presigned URL
├── webassets.py       # встроенные INDEX_HTML, APP_JS, STYLE_CSS
├── static/
│   ├── app.js         # логика фронтенда (892 строки)
│   └── style.css      # стили (253 строки)
└── templates/
    └── index.html     # разметка экранов (142 строки)
```

`static/` и `templates/` — исходники; они компилируются в `webassets.py` скриптом `scripts/gen_webassets.py`.

---

## 4. Запуск

- **Контейнер:** `docker/Dockerfile.crm` (`python:3.12-slim`, non-root пользователь `appuser`, `EXPOSE 8080`).
- **Команда:**
  ```sh
  uvicorn crm.app:app --host 0.0.0.0 --port ${PORT:-8080}
  ```

### Переменные окружения

| Переменная | Назначение |
|---|---|
| `DATABASE_URL` | PostgreSQL (обязательно `?sslmode=require`) |
| `S3_ENDPOINT_URL` | по умолчанию `https://s3.twcstorage.ru` |
| `S3_BUCKET_NAME` / `S3_ACCESS_KEY` / `S3_SECRET_KEY` | доступ к S3 (обязательны для presigned-ссылок) |
| `S3_REGION` | по умолчанию `us-east-1` |
| `CALL_TIMEZONE_OFFSET` | часовой пояс звонков, по умолчанию `+03:00` |
| `TELEGRAM_BOT_TOKEN` | токен бота; **не задан → auth выключен (dev-режим)** |
| `PORT` | задаётся платформой App Platform |

---

## 5. API-эндпоинты

Аутентификация: все `/api/*` маршруты — через зависимость `require_auth` (кроме `/healthz`, `/` и `/static/*`).

| Метод | Путь | Параметры | Ответ |
|---|---|---|---|
| GET | `/healthz` | — | `{status, database, s3}` |
| GET | `/` | — | HTML (Mini App) |
| GET | `/static/app.js` | — | JavaScript |
| GET | `/static/style.css` | — | CSS |
| GET | `/api/orders` | `status?`, `date?`, `limit` (1–200, def 100) | `{count, orders[]}` |
| GET | `/api/orders/{order_id}` | — | `{order}` или 404 |
| GET | `/api/orders/{order_id}/calls` | — | `{count, calls[]}` |
| GET | `/api/orders/{order_id}/bso` | — | `{bso}` |
| GET | `/api/clients/{client_id}/bso` | `client_id: int` | `{count, bso[]}` |
| GET | `/api/bso` | `limit` (1–500, def 200) | `{count, bso[]}` |
| GET | `/api/calendar` | — | `{days[]}` |
| GET | `/api/clients` | `limit` (1–500, def 200) | `{count, clients[]}` |
| GET | `/api/clients/{client_id}/calls` | `client_id: int` | `{calls[]}` |
| GET | `/api/calls/unmatched` | `limit` (1–500, def 200) | `{calls[]}` |
| GET | `/api/calls/today` | `date?` (ISO), `limit` (1–500, def 200) | `{calls[]}` |
| GET | `/api/summary/weekend` | — | `{people}` |
| POST | `/api/calls/{call_id}/match` | `order_id` (query, обязателен) | `{status:"ok"}` или 404 |

---

## 6. Аутентификация

`crm/auth.py` — валидация Telegram WebApp initData:

1. Параметры initData разбираются по `&` и `=`, значения `unquote`.
2. Извлекается `hash`, остальные пары сортируются по ключу и склеиваются через `\n` (data-check-string).
3. `secret_key = HMAC-SHA256(b"WebAppData", bot_token)`.
4. Сравнение подписи через `hmac.compare_digest`.

**Dev-режим:** если `TELEGRAM_BOT_TOKEN` не задан, `require_auth` пропускает всех (возвращает `None`).

Фронтенд передаёт токен в заголовке `X-Telegram-Init-Data` (значение `window.Telegram.WebApp.initData`).

---

## 7. Доступ к данным (`crm/repo.py`)

Все запросы — read-only (кроме `set_call_order`), через общий пул `shared/db.py`.

| Функция | Что делает | Таблицы |
|---|---|---|
| `list_orders(status, event_date, limit)` | список заказов с фильтрами | `orders` |
| `get_order(order_id)` | один заказ (+ `raw_payload`) | `orders` |
| `order_calls(order_id)` | звонки заказа (+ presigned) | `calls` |
| `get_order_bso(order_id)` | один БСО заказа | `orders_bso` |
| `client_bso(client_id)` | БСО клиента (join orders) | `orders_bso`, `orders` |
| `list_bso(limit)` | все БСО (left join orders) | `orders_bso`, `orders` |
| `calendar()` | заказы по датам с `CURRENT_DATE`, total/paid | `orders` |
| `list_clients(limit)` | клиенты с оплаченными заказами, счётчики | `clients`, `orders`, `calls` |
| `client_calls(client_id)` | звонки клиента (+ presigned) | `calls` |
| `unmatched_calls(limit)` | звонки `status='unmatched'` | `calls` |
| `calls_today(limit, date_str)` | звонки за сутки по TZ | `calls` |
| `weekend_headcount()` | сумма игроков оплаченных заказов до ближайшего понедельника | `orders` |
| `set_call_order(call_id, order_id)` | **запись**: связать звонок с заказом, `status='matched'` | `calls` |

Сериализация заказа (`shared/serialize.py` → `serialize_order`) — вложенная структура, совместимая с фронтендом:

```text
order = {
  id, order_id, status,
  payment:   { amount, currency, system, transaction_id },
  customer:  { name, email, phone },
  event:     { date, game, tent, session, qty },
  extra_fields, received_at
}
```

Presigned-ссылки на MP3 генерируются в `shared/s3.py` (`presigned_url(s3_key, expires=900)` — TTL 15 минут) и подставляются как поле `audio_url` в каждый звонок.

---

## 8. Схема БД (таблицы, используемые сервисом)

Схема формируется миграциями Alembic `0001–0007`.

### `orders`
`id`, `order_id` (unique), `order_status`, `payment_amount` (Numeric), `payment_currency`, `payment_system`, `payment_transaction_id`, `order_date`, `customer_name`, `customer_email`, `customer_phone`, `game`, `tent`, `session_time`, `qty`, `extra_fields` (JSONB), `raw_payload` (JSONB), `received_at`, `client_id` (FK→clients), `source` (def `tilda`).

Индексы: `order_id` (unique), `game`, `order_status`, `client_id`.

### `clients`
`client_id` (PK, BigInteger), `phone` (unique), `name`, `email`, `created_at`.

Идентификация — по **нормализованному телефону** `7XXXXXXXXXX`.

### `calls`
`id`, `email_id` (unique, = IMAP UID), `order_id`, `phone`, `call_datetime`, `administrator`, `mp3_filename`, `s3_key`, `duration_seconds`, `status` (`matched`/`unmatched`/`ambiguous`), `created_at`, `metadata` (JSONB), `client_id` (FK), `mp3_hash` (unique).

### `orders_bso`
`id`, `order_id` (unique, FK→orders CASCADE), `game_date`, `order_amount` (Numeric), `bso_number`, `players_fact`, `customer_name`, `rest_zone_amount` (Numeric), `source` (def `gsheets`), `received_at`, `updated_at`.

Один БСО на один заказ; данные приходят из Google Sheets.

---

## 9. Фронтенд (Telegram Mini App)

Одностраничное приложение без сборки. Разметка — `templates/index.html`, логика — `static/app.js`, стили — `static/style.css`; всё встроено в `webassets.py`.

### Экраны

| Экран | Назначение |
|---|---|
| Старт | главное меню: Расписание / Клиенты / Заказы / Звонки / БСО |
| Расписание | месяц + неделя, бейдж «Ожидаем в выходные», сводка дня, переключатель Утро/Вечер |
| Клиенты | список клиентов с оплаченными заказами, карточка клиента |
| Заказы | фильтр Ближайшие / Все / Выбор даты (+ полоса дат) |
| Звонки | звонки за дату (полоса дат), карточка с плеером MP3 |
| БСО | аккордеон карточек + фильтр Все / Выбор даты |

### Ключевые особенности

- **Telegram WebApp SDK:** `tg.ready()`, `tg.expand()`; заголовок `X-Telegram-Init-Data` из `initData`.
- **Навигация:** нижняя панель (`schedule`/`orders`/`calls`/«ЕЩЕ»), меню «ЕЩЕ» → `clients`/`bso`.
- **Диалог** `<dialog id="orderDialog">` — карточка заказа или клиента с блоками «Звонки»/«Заказы».
- **Данные:** при старте параллельно грузятся `/api/orders`, `/api/clients`, `/api/bso` (кэш в `state`), отдельно — `/api/summary/weekend` и звонки за выбранную дату.
- **Классификация игры** (пейнтбол/лазертаг/кидбол) и **сеанса** (Утро 09:00–14:45 / Вечер 15:15–21:00) — по строке, без БД.
- **Копирование телефона/e-mail** в буфер обмена с фолбэком на `document.execCommand("copy")`.
- **Экранирование** вывода через `esc()` (защита от XSS), пресеты в шаблонных строках.

---

## 10. Общие зависимости (`shared/`)

| Модуль | Что даёт сервису |
|---|---|
| `db.py` | ленивый синглтон `ConnectionPool` (min 1, max 5, max_idle 240) |
| `s3.py` | `s3_client()` (boto3, s3v4), `presigned_url()`, `build_s3_key()` |
| `serialize.py` | `json_safe`, `serialize_row`, `serialize_order` |
| `health.py` | `check_db()` (`SELECT 1`), `check_s3()` (`head_bucket`) |

---

## 11. Ключевые решения

- Фронтенд **встроен в код** (`webassets.py`, генерируется `scripts/gen_webassets.py`) — контейнер автономен.
- Аутентификация API — Telegram `initData` (HMAC); без `TELEGRAM_BOT_TOKEN` — dev-режим.
- Presigned S3-ссылки на MP3 с TTL 15 минут (не отдаём ключи напрямую).
- `clients` идентифицируются по нормализованному телефону (`phone UNIQUE`).
- Сервис почти полностью read-only; единственная запись — ручной match звонка (`set_call_order`).
- Часовой пояс звонков — `CALL_TIMEZONE_OFFSET` (по умолчанию `+03:00`).

---

## 12. История версий `crm` (кратко)

| Версия | Дата | Что изменилось |
|---|---|---|
| v12.6 | 26.08 | вкладка «Звонки», копия телефона, бейдж выходных, `client_id` |
| v12.8 | 28.08 | экран «Расписание» |
| v12.9 | 28.08 | адаптивная вёрстка |
| v12.10 | 28.08 | фикс «не загружаются звонки из карточки» |
| v12.12 | 31.08 | имя клиента в карточках звонков |
| v12.13 | 31.08 | БСО из Google Sheets (БД + API) |
| v12.14 | 01.09 | экран «БСО» во фронтенде |
| v12.16 | 04.09 | фильтры по дате (Звонки/Заказы/БСО) + аккордеон БСО |
| v12.17 | 04.09 | исправление фильтра по дате в «БСО» |

Подробные отчёты — в `docs/2026-*.md`.

---

## 13. Связанная документация

- `README.md` — обзор всей системы и деплой.
- `docs/web-ui-registry.md` — реестр веб-интерфейсов.
- `docs/data-inventory.md` — инвентаризация данных.
- `docs/deploy-app-platform.md`, `docs/cutover.md`, `docs/rollback.md` — деплой и откат.
- `docs/2026-09-04_crm-filters-accordion.md`, `docs/2026-09-04_crm-bso-filter-fix.md` — последние изменения.
