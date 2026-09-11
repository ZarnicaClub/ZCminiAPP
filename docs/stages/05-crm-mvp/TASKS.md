# Этап 5 — MVP crm-api + Mini App

**Цель:** читающий интерфейс менеджера в отдельном сервисе.
**Статус:** ✅ код готов и протестирован (auth); живой прогон (БД/S3/браузер) — после staging.

## Готово
- [x] API: `/healthz`, `/api/orders`, `/api/orders/<id>`, `/api/orders/<id>/calls`, `/api/calendar`.
- [x] Сущность клиентов: `/api/clients`, `/api/clients/<id>/calls` (+ счётчики заказов/звонков).
- [x] Несвязанные звонки: `/api/calls/unmatched` (критично — 187 unmatched-звонков).
- [x] Ручное связывание: `POST /api/calls/<id>/match?order_id=...` (MANUAL_MATCH).
- [x] Presigned URL (TTL ≤ 15 мин) через `shared/s3.py`.
- [x] Аутентификация Telegram `initData` (`crm/auth.py`, HMAC-SHA256); без токена — dev-режим.
- [x] Фронтенд: legacy Mini App + заголовок `initData` + вкладка «Клиенты» (список + звонки клиента).
- [x] Ответ заказов в legacy-совместимой структуре (`serialize_order`: customer/event/payment).

## Проверено локально
- [x] `tests/test_auth.py`: валидная подпись, отказ при подмене/отсутствии hash.
- [x] Синтаксис `auth.py`/`repo.py`/`app.py` OK; `node --check app.js` OK.

## Ожидает (живые зависимости)
- [ ] Браузер: карточка заказа/клиента, звонки, MP3; unmatched-звонки видны; ручной match работает.
- [ ] Без валидного initData API отдаёт 401 (при заданном TELEGRAM_BOT_TOKEN).

## Выход
`crm/auth.py`, `crm/repo.py`, `crm/app.py`, `crm/templates/`, `crm/static/`, `tests/test_auth.py`.
