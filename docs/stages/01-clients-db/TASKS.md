# Этап 1 — Таблица Clients, удаление order_items, загрузка клиентов

**Цель:** привести схему БД к целевой модели v2 и наполнить `clients`.
**Статус:** код готов и проверен локально; **запуск миграции на живой PostgreSQL — ожидает staging-БД**.

## Целевая модель (v2)
```text
clients: client_id PK, phone UNIQUE, name, email, created_at
orders:  legacy + client_id FK + source (order_items УДАЛЯЕТСЯ)
calls:   legacy + client_id FK + mp3_hash UNIQUE
```

## Готово (код)
- [x] Alembic (5 миграций: `0001_baseline` → `0005_drop_order_items`), `alembic.ini`, `env.py`.
- [x] `shared/phone.py` — единая нормализация телефона.
- [x] `scripts/migrate_data.py` — загрузка/дедуп (clients/orders/calls), идемпотентный.
- [x] `scripts/create_roles.sql` — webhook_user / worker_user / crm_user.
- [x] `01-clients-db/MIGRATION_RUNBOOK.md` — staging → prod.
- [x] `docs/data-inventory.md` — инвентаризация данных.

## Проверено локально (без БД)
- [x] Синтаксис всех модулей (py_compile exit 0).
- [x] Логика миграции на реальных CSV: 30 заказов, 223→213 звонков (10 дублей), 136 клиентов, 0 невалидных телефонов.
- [x] Регрессионные тесты `tests/test_phone.py`, `tests/test_migrate_data.py` — OK.

## Ожидает (нужна живая PostgreSQL)
- [ ] `alembic upgrade 0003_links` → `migrate_data.py --apply` → `alembic upgrade head` на staging.
- [ ] Проверка счётчиков: clients=136, orders=30, calls=213, mp3_hash без NULL и без дублей.
- [ ] Применить `create_roles.sql`.
- [ ] Затем тот же прогон на production (по runbook, после бэкапа).

## Выход
`migrations/`, `shared/phone.py`, `scripts/migrate_data.py`, `scripts/create_roles.sql`, `MIGRATION_RUNBOOK.md`, тесты.

## Блокер
Нет доступа к живой PostgreSQL (в этой песочнице Docker-демон не запущен, сети для установки alembic нет). Нужен `DATABASE_URL` staging-БД от заказчика или прогон runbook на TimeWeb.
