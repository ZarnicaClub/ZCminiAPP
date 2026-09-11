# Контракты интеграций (замороженные сэмплы)

## 1. Tilda → Orders Webhook

Endpoint: `POST /webhook/tilda/<secret>`. Content-Type: `application/json`
или form-encoded (flat-поля). Полный пример реального JSON-пайлоада —
`tilda_payload.json`.

Наблюдаемая структура JSON (из production `raw_payload`):

```text
{
  "qty": "8",
  "date": "16.08.2026",           // DD.MM.YYYY
  "game": "Лазертаг Новобранец",
  "name": "Евгения",
  "tent": "Крытая беседка до 20 человек",
  "email": "...",
  "phone": "89037335471",          // исходный формат, нормализуем в 7XXXXXXXXXX
  "formid": "form123064920",
  "formname": "Cart",
  "Выберите_сеанс": "- Утренний с 9:00 до 14:45;",
  "Checkbox": "yes",
  "referer": "https://...",
  "payment": {
    "sys": "tinkoff",
    "amount": "5000",
    "orderid": "2085387211",
    "products": [ {"name": "Игра в клубе ЗарницаКлаб", "price": "5000", "amount": 5000, "quantity": 1} ],
    "systranid": "9037780797"
  }
}
```

Бизнес-ключ идемпотентности: `payment.orderid` → `orders.order_id UNIQUE`.

## 2. Нормализация телефона (единая для webhook и worker)

```text
10 цифр, начинается с 9          → 7 + цифры
11 цифр, начинается с 8          → 7 + остальные 10
11 цифр, начинается с 7          → как есть
иначе                           → невалидный (webhook сохраняет как есть, worker отклоняет)
```
Канонический формат: `7XXXXXXXXXX`.

## 3. Email (Яндекс.Почта) → Calls Worker

Тема письма (реальные примеры):

```text
Запись разговора 29.07.2026 15:09:46 +79775767828 Никитин Александр
Запись разговора 05.08.2026 10:36:53 +79175307576 Никитин Александр
Запись разговора 11.08.2026 14:48:01 +79851297771 Мария Коробова
```

Регулярная структура:

```text
Запись разговора DD.MM.YYYY HH:MM:SS PHONE ADMINISTRATOR
```

Извлекается: `call_datetime` (тема), `phone` (нормализуем), `administrator`
(из темы, кириллицей). Вложение: ровно один MP3 (`audio/mpeg`/`.mp3`).
`duration_seconds` — из MP3 (mutagen). `sha256` — по байтам MP3.

Правило: 1 письмо = 1 звонок = 1 MP3.

## 4. CRM API (чтение)

`GET /api/orders`, `/api/orders/<id>`, `/api/orders/<id>/calls`, `/api/calendar`,
`/healthz`; presigned S3 URL (TTL ≤ 15 мин) для MP3.
