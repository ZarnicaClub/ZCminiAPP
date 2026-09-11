# newCRM — ЗарницаКлаб CRM

Production-версия CRM: **3 независимых сервиса** на Timeweb App Platform + общая PostgreSQL + S3.

**Статус:** ✅ работает в production (переключено 24.08.2026, старый монолит удалён).

## Архитектура

```text
Tilda → orders-webhook ─┐
                        ├─ PostgreSQL (clients, orders, calls)
Mail → calls-worker ────┘          │
                        S3 (MP3)  ←┘
Telegram → crm (Mini App) → API → orders/calls → presigned S3 URL
```

| Сервис | Ответственность |
|---|---|
| `orders-webhook` | приём заказов Tilda, нормализация, upsert `orders` + `clients` |
| `calls-worker` | IMAP (UID) → парсинг → матчинг → S3 → `calls` |
| `crm` | API + Telegram Mini App (заказы, клиенты, звонки, MP3) |

## Стек

Python 3.12 · FastAPI · Uvicorn · psycopg3 + psycopg-pool · boto3 (S3 Signature v4) · mutagen · Alembic · Vanilla JS.

## Структура

```text
implementation/
├── shared/            # общее ядро: phone, date, subject, s3, db, health, serialize, tilda, contracts, logging
├── orders_webhook/    # сервис 1
├── calls_worker/      # сервис 2
├── crm/               # сервис 3 (+ встроенный фронтенд в webassets.py)
├── migrations/        # Alembic (0001..0005)
├── docker/            # Dockerfile.webhook / .worker / .crm
├── scripts/           # операционные: migrate_data, run_migration, db_backup, db_status, gen_webassets, create_roles
├── tests/             # unit-тесты + smoke-тест
├── docs/              # документация: stages/ (этапы), rollback, cutover, deploy, data-inventory
├── contracts/samples/ # контракты (Tilda payload)
└── .github/workflows/ # CI
```

## Деплой

1. Собрать образы: `docker build -f docker/Dockerfile.<svc> -t <hub>/<svc>:latest .` (+ push).
2. 3 сервиса на App Platform, env-переменные из `.env.example`.
3. Подробно: `docs/deploy-app-platform.md`, порядок переключения — `docs/cutover.md`.

> ВАЖНО: `DATABASE_URL` должен быть со `?sslmode=require` (не `verify-full` — сертификата в контейнере нет).

## Проверка работоспособности

- `GET /healthz` на каждом сервисе → `{"status":"ok","database":"ok","s3":"ok"}`.
- `calls-worker`: `GET :8081/status` → счётчики циклов.
- Новый заказ из Tilda → `orders` + `clients` (с `client_id`); новое письмо → `calls` + MP3 в S3.

## Данные и миграция

- Схема: `clients`, `orders`, `calls` (таблица `order_items` удалена).
- Итог миграции: `clients=136`, `orders=30`, `calls=213` (10 дублей удалено по `mp3_hash`).
- Production-выгрузки (`orders.csv`, `calls.csv`, `default_db.sql`) и бэкап до миграции вынесены в `../_архив_данных/` (ПДн, вне git).
- Повторная миграция: вернуть `data/` в корень и выполнить `scripts/run_migration.py` (нужен `pip install -r requirements-dev.txt`).

## Ключевые решения

- `clients` — идентификация по **нормализованному телефону** (`7XXXXXXXXXX`), `phone UNIQUE`.
- `mp3_hash UNIQUE` + контентно-адресуемый ключ S3 `calls/{sha[:2]}/{sha}.mp3`.
- `email_id` = **IMAP UID** (не sequence number).
- Фронтенд **встроен в код** (`crm/webassets.py`, генерируется `scripts/gen_webassets.py` из `crm/templates|static/`).
- Аутентификация API — Telegram `initData` (HMAC), без токена — dev-режим.
