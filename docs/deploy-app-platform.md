# Деплой 3 сервисов на Timeweb App Platform

## Сборка образов (Docker Hub)
```bash
docker build -f docker/Dockerfile.webhook -t amkorobov/orders-webhook:latest .
docker build -f docker/Dockerfile.worker  -t amkorobov/calls-worker:latest  .
docker build -f docker/Dockerfile.crm     -t amkorobov/crm:latest          .
docker push amkorobov/orders-webhook:latest
docker push amkorobov/calls-worker:latest
docker push amkorobov/crm:latest
```

## Три сервиса на App Platform

| Сервис | Образ / Dockerfile | Порт | Env (кроме общих) |
|---|---|---|---|
| `orders-webhook` | `docker/Dockerfile.webhook` | 8080 | `WEBHOOK_SECRET`, `GSHEETS_SECRET` |
| `calls-worker` | `docker/Dockerfile.worker` | 8081 (health) | `MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_IMAP_*`, `MAIL_FOLDER` |
| `crm` | `docker/Dockerfile.crm` | 8080 | `TELEGRAM_BOT_TOKEN` |

Общие для всех: `DATABASE_URL`, `S3_ENDPOINT_URL`, `S3_BUCKET_NAME`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_REGION`, `CALL_TIMEZONE_OFFSET`.

> App Platform инжектит `PORT`; webhook и crm слушают `${PORT:-8080}`.
> Worker healthcheck: `GET :8081/status` или `:8081/healthz`.

## Порядок развёртывания
1. Мигрировать БД (runbook `01-clients-db/MIGRATION_RUNBOOK.md`): staging → prod.
2. Применить роли `scripts/create_roles.sql`.
3. Задеплоить 3 сервиса рядом со старым монолитом (parallel-run).
4. Прогнать E2E по `docs/cutover.md`, затем переключить URL Tilda и остановить старый монолит.

## Проверка
- webhook/crm: `GET /healthz` → `{"status":"ok","database":"ok","s3":"ok"}`.
- worker: `GET :8081/status` → счётчики цикла.
