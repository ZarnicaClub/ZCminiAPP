# Этап 0 — Заморозка и страховка

**Цель:** зафиксировать рабочее состояние так, чтобы любой следующий шаг был откатываемым.
**Статус:** ✅ PASS (24.08.2026)

## Шаги
- [x] `git init` в `implementation/`, монолит скопирован в `legacy/`, тег `v11.11-clean` (commit `87b2058`).
- [x] Бэкап production: выгрузки заказчика `data/default_db.sql` (DDL) + `data/orders.csv` + `data/calls.csv` (данные). S3 не трогаем (MP3 не перезаливаются) — инвентаризация S3 не требуется.
- [x] Точный DDL `orders`/`order_items`/`calls` — `data/default_db.sql` (PostgreSQL 17.10).
- [x] Контракты заморожены: `contracts/samples/tilda_payload.json` (реальный Tilda JSON) + тема письма звонка в `contracts/samples/README.md`.
- [x] Документ отката: `docs/rollback.md`.
- [x] Переменные окружения 3 сервисов: `.env.example`.
- [x] Инвентаризация данных: `docs/data-inventory.md` (30 заказов, 223 звонка → 213 после дедупа, 136 клиентов).

## Критерии PASS
- [x] Есть git-тег, откат задокументирован.
- [x] Реальный DDL получен.
- [x] Есть реальный образец Tilda-пайлоада и темы письма.

## Выход
`legacy/`, `contracts/samples/`, `docs/rollback.md`, `docs/data-inventory.md`, `.env.example`, `.gitignore`, теги `v11.11-clean` + `etap-0-pass`.
