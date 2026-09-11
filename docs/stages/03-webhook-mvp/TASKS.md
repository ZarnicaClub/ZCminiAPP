# Этап 3 — MVP orders-webhook

**Цель:** перенести приём заказов Tilda в отдельный сервис (без order_items, с clients).
**Статус:** ✅ код готов, парсинг проверен на реальном пайлоаде; живой прогон — после staging-БД.

## Готово
- [x] `POST /webhook/tilda/<secret>`: JSON + form; пустой → 400; нет `order_id` → 400.
- [x] Нормализация телефона/даты через `shared/` (единый код с парсером).
- [x] Upsert `orders` по `order_id` (`ON CONFLICT DO UPDATE`), **без записи в `order_items`**.
- [x] Создание/линковка `clients` по нормализованному телефону (upsert).
- [x] Сохранение `raw_payload` (полная история).
- [x] `/healthz` с проверкой DB + S3.
- [x] Защита: секрет в URL (`WEBHOOK_SECRET`). HMAC-подпись Tilda — TODO (нужны детали подписи); rate-limit — на уровне reverse-proxy/App Platform.

## Проверено локально
- [x] `tests/test_tilda.py`: реальный JSON-пайлоад, form-пайлоад, нет order_id → None.
- [x] Все тесты ядра OK; синтаксис сервиса OK.

## Ожидает (живая БД)
- [ ] E2E: заказ из Tilda → `orders`+`clients`; повторная доставка не дублирует; ответ < 300 мс.

## Выход
`orders_webhook/app.py`, `orders_webhook/service.py`, `shared/tilda.py`, `tests/test_tilda.py`.
