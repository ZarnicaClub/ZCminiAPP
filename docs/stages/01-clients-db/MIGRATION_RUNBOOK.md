# Этап 1 — Runbook миграции БД

## Целевая схема (v2)
`clients` (+136), `orders` (+client_id, +source, без order_items), `calls` (+client_id, +mp3_hash UNIQUE), `order_items` удалена.

## Подготовка
```bash
pip install -r requirements-dev.txt
export DATABASE_URL=postgresql://USER:PASS@HOST:5432/DB
```

## Вариант A — staging / свежая БД (рекомендуется первым)
```bash
# 1. Схема до состояния «данные можно грузить» (mp3_hash ещё nullable)
alembic upgrade 0003_links

# 2. Загрузка и дедупликация данных (30 заказов, 213 звонков, 136 клиентов)
python scripts/migrate_data.py --apply

# 3. Финализация схемы (UNIQUE(mp3_hash), drop order_items)
alembic upgrade head

# 4. Роли
psql "$DATABASE_URL" -f scripts/create_roles.sql
```

## Вариант B — production (legacy-таблицы уже существуют с данными)
```bash
# 0. Бэкап: pg_dump (структура + данные) — ОБЯЗАТЕЛЬНО
# 1. Пометить базлайна (таблицы уже есть — не пересоздаём)
alembic stamp 0001_baseline

# 2. До-дедупное состояние схемы
alembic upgrade 0003_links

# 3. Бэкап данных: создать clients, проставить client_id/mp3_hash, удалить 10 дублей
python scripts/migrate_data.py --apply

# 4. Финализация
alembic upgrade head

# 5. Роли
psql "$DATABASE_URL" -f scripts/create_roles.sql
```

## Проверка (должно совпасть)
```sql
SELECT count(*) FROM clients;  -- 136
SELECT count(*) FROM orders;   -- 30
SELECT count(*) FROM calls;    -- 213
SELECT count(*) FROM calls WHERE mp3_hash IS NULL;  -- 0
-- дублей по sha256 быть не должно:
SELECT mp3_hash, count(*) FROM calls GROUP BY mp3_hash HAVING count(*) > 1;  -- 0 строк
```

## Откат
См. `docs/rollback.md`. До `alembic upgrade head` откат = `alembic downgrade 0002_clients`
(схема) + восстановление данных из бэкапа.
