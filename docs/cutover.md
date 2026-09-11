# Этап 6 — Runbook теста и переключения production

## 0. Предусловия
- Staging-БД прошла миграцию (runbook этапа 1): `clients=136`, `orders=30`, `calls=213`.
- 3 образа собраны и загружены в Docker Hub (webhook / worker / crm).
- На App Platform созданы 3 сервиса с нужными env-переменными (`.env.example`).

## 1. E2E-чеклист (staging)
### Orders Webhook
- [ ] `POST /webhook/tilda/<secret>` (JSON) → 200, заказ в `orders` + client создан/слинкован.
- [ ] Повторный `POST` того же `order_id` → upsert, без дубля.
- [ ] Пустой пайлоад → 400; нет `order_id` → 400; неверный secret → 403.

### Calls Worker
- [ ] Новое письмо → звонок в `calls` + MP3 в S3 (ключ `calls/{sha}/{sha}.mp3`).
- [ ] Повторный прогон → без дубля (защита по `email_id` И `mp3_hash`).
- [ ] 3 рестарта подряд → без потери писем.
- [ ] `/status` показывает `last_cycle_at`, счётчики, ошибки.

### CRM
- [ ] Карточка заказа открывается; звонки видны; MP3 играет (presigned).
- [ ] Вкладка «Клиенты»: 136 клиентов; звонки клиента видны.
- [ ] `/api/calls/unmatched` показывает несвязанные; ручной match (`/api/calls/<id>/match`) работает.
- [ ] Без валидного initData → 401 (при заданном `TELEGRAM_BOT_TOKEN`).

## 2. Параллельный запуск (parallel-run)
1. Развернуть 3 новых сервиса **рядом** со старым монолитом (не выключая его).
2. Прогнать E2E на staging. Не выключать старый worker до подтверждения.

## 3. Переключение (production)
1. Бэкап prod (pg_dump; CSV/DDL-выгрузки уже есть в `data/`).
2. Миграции на prod (runbook этапа 1, вариант B):
   `alembic stamp 0001_baseline` → `alembic upgrade 0003_links` →
   `python scripts/migrate_data.py --apply` → `alembic upgrade head`.
3. Переключить URL веб-хука Tilda на новый `orders-webhook`.
4. Остановить старый монолит (webhook + parser).
5. Верифицировать: новый заказ → `orders`+`clients`; контрольный звонок → `calls`+S3; MP3 в Mini App.

## 4. Откат
- Вернуть URL Tilda на старый endpoint + передеплой старого образа (архив).
- Схему откатить по `docs/rollback.md` (до `alembic upgrade head` откат простой).
