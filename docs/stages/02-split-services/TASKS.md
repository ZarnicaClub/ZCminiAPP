# Этап 2 — Разделение монолита на 3 сервиса (скелеты + shared/)

**Цель:** структура репозитория + каркасы трёх сервисов с общим ядром.
**Статус:** ✅ код готов и проверен локально (запуск FastAPI требует установки зависимостей — на сборке Docker).

## Структура (фактическая)
```text
shared/          phone, date, subject, s3, db, health, logging_config, contracts
orders_webhook/  FastAPI: POST /webhook/tilda/<secret>, /healthz
calls_worker/    цикл + health-HTTP (stdlib http.server, порт 8081)
crm/             FastAPI: /, /api/orders, /healthz
docker/          Dockerfile.webhook / .worker / .crm (multi-stage, non-root)
docker-compose.yml
migrations/      (этап 1)
tests/           test_phone, test_date, test_subject, test_s3, test_migrate_data
```

## Готово
- [x] `shared/` чистые функции: `normalize_phone`, `normalize_order_date`, `parse_subject`, `build_s3_key`/`sha256_hex`, пул БД, JSON-логи + `trace_id`, health-проверки DB/S3.
- [x] Pydantic-контракты: `OrderIn`, `CallIn`, `ClientOut`, `TildaProduct`.
- [x] Скелет `orders_webhook` (FastAPI): `/healthz` (DB+S3), заглушка webhook.
- [x] Скелет `calls_worker`: health-HTTP на отдельном порту + пустой цикл.
- [x] Скелет `crm` (FastAPI): `/healthz`, `/`, заглушка `/api/orders`.
- [x] Три Dockerfile (non-root `USER appuser`) + `docker-compose.yml`.

## Проверено локально
- [x] 27 py-файлов компилируются (0 ошибок).
- [x] Тесты ядра: `test_phone`, `test_date`, `test_subject`, `test_s3`, `test_migrate_data` — OK.
- [x] Health-сервер worker отвечает HTTP 200 (`{"status":"ok","service":"calls-worker"}`).

## Ограничение
Запуск FastAPI-приложений и Pydantic-контрактов требует установки зависимостей
(`pip install -r requirements.txt`) — сеть в песочнице не позволяет; сборка/запуск
проверяется на Docker-образе (TimeWeb / локально).

## Выход
`shared/`, три каркаса сервисов, `docker/`, `docker-compose.yml`, тесты.
