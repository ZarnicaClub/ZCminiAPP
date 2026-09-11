# Отчёт об изменении — интеграция БСО из Google Sheets (`orders_bso`)

- **Дата:** 31.08.2026
- **Версия:** v12.13
- **Сервисы:** `orders-webhook` (приём), `crm` (чтение) + миграция БД
- **Образы:** `amkorobov/orders-webhook:12.13`, `amkorobov/crm:12.13`
- **Статус:** ✅ задеплоено, данные из Google Sheets поступают в `orders_bso`

---

## Цель

Принимать БСО (бланк строгой отчётности) из Google Sheets (лист `БАЛАНС`, статья `Касса`) и записывать их в новую таблицу `orders_bso` по ключу `order_id`, связывая с **уже существующим** заказом. Новый заказ из Google Sheets не создаётся.

## Схема

```text
Google Sheets (БАЛАНС, «Касса», дата >= 13.08.2026, order_id заполнен)
      ↓  Google Apps Script (по расписанию, каждые 5 минут)
      ↓  HTTPS POST /webhook/gsheets  (заголовок X-Gsheets-Secret)
      ↓  orders-webhook → upsert_bso()
      ↓  PostgreSQL: orders_bso
      ↓  CRM (read-only API: /api/bso, /api/orders/{order_id}/bso, /api/clients/{client_id}/bso)
```

---

## Что изменено

### БД
- `migrations/versions/0006_orders_bso.py` — таблица `orders_bso` (unique `order_id`, FK → `orders.order_id` ON DELETE CASCADE, индексы `idx_orders_bso_order_id` / `_bso_number` / `_game_date`).
- `scripts/create_roles.sql` — `GRANT` на `orders_bso` (в текущей «одновладельческой» схеме не применялись — роли не используются).

### Приём данных (orders-webhook)
- `shared/contracts.py` — добавлен `BsoIn`.
- `shared/gsheets.py` — парсер `parse_gsheets_bso()` (толерантная нормализация типов).
- `orders_webhook/service.py` — `upsert_bso()`: заказа нет → `skipped`; есть → `INSERT … ON CONFLICT (order_id) DO UPDATE` (идемпотентно).
- `orders_webhook/app.py` — `POST /webhook/gsheets`, авторизация заголовком `X-Gsheets-Secret` (env `GSHEETS_SECRET`).

### CRM (чтение)
- `crm/repo.py` — `get_order_bso()`, `client_bso()`, `list_bso()`.
- `crm/app.py` — `GET /api/orders/{order_id}/bso`, `GET /api/clients/{client_id}/bso`, `GET /api/bso`.

### Конфиг
- `.env.example`, `docker-compose.yml` — добавлен `GSHEETS_SECRET`.
- `docs/deploy-app-platform.md` — env-таблица обновлена.

### Apps Script
- `gsheets_webhook/apps_script.gs` — production-скрипт (обход всех готовых строк, auth, конфиг через Script Properties `GSHEETS_ENDPOINT` / `GSHEETS_SECRET`).

### Тесты
- `tests/test_gsheets.py` — нормализация полей (пройден: `test_gsheets: OK`).

---

## API-контракт приёма

`POST /webhook/gsheets`, заголовок `X-Gsheets-Secret: <секрет>`, body:

```json
{
  "order_id": 1624763921,
  "game_date": "2026-08-13",
  "order_amount": 19000,
  "bso_number": "1449",
  "players_fact": 8,
  "customer_name": "Юля",
  "rest_zone_amount": null
}
```

Ответы:

| Код | Тело | Смысл |
|---|---|---|
| 200 | `{"status":"ok"}` | БСО записан/обновлён |
| 200 | `{"status":"skipped","reason":"order_not_found"}` | заказа с `order_id` нет — пропуск |
| 200 | `{"status":"skipped","reason":"missing order_id"}` | нет `order_id` в payload |
| 400 | `{"detail":"cannot parse body"}` / `empty payload` | неверный запрос |
| 403 | `{"detail":"forbidden"}` | секрет не совпал |

## Соответствие полей

| Google Sheets | `orders_bso` |
|---|---|
| `order_id` | `order_id` (TEXT, FK → `orders.order_id`) |
| `Дата` | `game_date` (DATE) |
| `Приход` | `order_amount` (NUMERIC(12,2)) |
| `№ документа` | `bso_number` (TEXT) |
| `игроков (факт)` | `players_fact` (INTEGER) |
| `Заказчик` | `customer_name` (TEXT) |
| `Зона отдыха` | `rest_zone_amount` (NUMERIC(12,2)) |

---

## Поведение

- **До:** данные БСО из Google Sheets никуда не попадали (только тестовые POST на Webhook.site); БСО в CRM не отображалось.
- **После:** готовая строка `Касса` (дата ≥ 13.08.2026, `order_id` заполнен) автоматически дописывает/обновляет БСО в `orders_bso` для существующего заказа; данные доступны через API CRM (визуализация в карточке — следующий этап, не входил в этот объём «БД и API без фронтенда»).

---

## Бэкап

- Каталог: `implementation/_backup_gsheets_bso_v12.13_20260831_232335/`
- Файлы (исходные версии до правок): `.env.example`, `crm/app.py`, `crm/repo.py`, `docker-compose.yml`, `docs/deploy-app-platform.md`, `orders_webhook/app.py`, `orders_webhook/service.py`, `scripts/create_roles.sql`, `shared/contracts.py`.

---

## Деплой

1. БД: создана таблица `orders_bso` (миграция `0006_orders_bso`); `alembic_version = 0006_orders_bso`. Роли не перевыдавались — сервисы ходят в БД одним владельцем.
2. Образы собраны/запушены:
   ```cmd
   docker build -f docker\Dockerfile.webhook -t amkorobov/orders-webhook:12.13 .
   docker build -f docker\Dockerfile.crm     -t amkorobov/crm:12.13 .
   docker push amkorobov/orders-webhook:12.13
   docker push amkorobov/crm:12.13
   ```
3. В App Platform у `orders-webhook` задан env `GSHEETS_SECRET`.
4. В Apps Script заданы Script Properties `GSHEETS_ENDPOINT` (= `https://<адрес-orders-webhook>/webhook/gsheets`) и `GSHEETS_SECRET` (то же значение, что на сервере), установлен триггер `processSheet` каждые 5 минут.

---

## Откат (при необходимости)

1. **БД:** `alembic downgrade 0005_drop_order_items` (удалит `orders_bso`) или вручную `DROP TABLE orders_bso;`. Если таблица удалялась — сначала выгрузить данные при необходимости (`pg_dump` / `scripts/db_backup.py`).
2. **Образы:** передеплоить предыдущие теги (`orders-webhook`, `crm` — версия до 12.13).
3. **Apps Script:** удалить триггер и/или вернуть `GSHEETS_ENDPOINT` на прежнее значение (Webhook.site).
4. Файлы кода восстановить из каталога бэкапа (см. выше).
