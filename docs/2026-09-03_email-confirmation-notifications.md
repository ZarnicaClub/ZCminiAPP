# Отчёт об изменении — email-уведомление о подтверждении брони

- **Дата:** 03.09.2026
- **Версия:** v12.15
- **Сервисы:** `orders-webhook` (отправка)
- **Образ:** `amkorobov/orders-webhook:latest`
- **Бэкап:** `implementation/_backup_email_notifications_v12.15_20260903_191515` (git HEAD `1c014bb`)
- **Статус:** ✅ задеплоено, подтверждение брони уходит клиенту по SMTP

---

## Цель

Автоматически отправлять клиенту письмо-подтверждение бронирования сразу после
приёма **оплаченного** заказа из Tilda. Дизайн письма, HTML-шаблон и inline-картинка
взяты из пакета `ZarnicaClub_email_package`.

## Схема

```text
Tilda (форма заказа, оплата)
      ↓  HTTPS POST /webhook/tilda/{secret}
      ↓  orders-webhook → upsert_order()  (заказ сохранён, транзакция закрыта)
      ↓  _maybe_send_confirmation(): заказ paid + есть customer_email + SMTP настроен
      ↓  shared/mailer.py → рендер email.html + SMTP (smtplib, STARTTLS)
```

---

## Что изменено

### Новые файлы
- `shared/mailer.py` — рендер шаблона, маппинг полей заказа → переменные шаблона,
  отправка через SMTP. Только stdlib (`smtplib`, `email.mime`, `ssl`) — новых зависимостей нет.
- `shared/email/email.html` и `shared/email/hero.png` — шаблон и hero-картинка
  (скопированы из `ZarnicaClub_email_package`; картинка идёт inline c `Content-ID: zarnica-hero`).

### Изменённые файлы
- `orders_webhook/service.py` — импорт `shared.mailer`; после `upsert_order()` вызывается
  `_maybe_send_confirmation(order)` (проверка paid + customer_email + SMTP).
- `.env.example`, `docker-compose.yml` — добавлена секция SMTP.

### Константы письма и клуба
Зашиты **в коде** (`shared/mailer.py`, блок констант вверху файла), НЕ в окружении:

| Константа | Значение | Примечание |
|---|---|---|
| `FROM_NAME` | `ЗарницаКлаб` | |
| `FROM_EMAIL` | `""` | пусто = отправитель равен `SMTP_USER` (почтовый ящик) |
| `EMAIL_SUBJECT` | `ЗарницаКлаб — бронирование подтверждено` | |
| `EMAIL_FORMAT` | `Пейнтбол` | |
| `CLUB_MAP_URL` | `https://yandex.ru/maps/` | |
| `CLUB_PHONE` | `""` | ⚠️ TODO: вписать реальный телефон |
| `CLUB_MESSENGER` | `Telegram / WhatsApp` | ⚠️ TODO: уточнить ник/ссылку |
| `CLUB_SITE` | `зарницаклаб.рф` | |
| `CLUB_ADDRESS` | `""` | ⚠️ TODO: вписать реальный адрес |

### Маппинг полей заказа → переменные шаблона
- `name`/`email` ← `customer_name`/`customer_email`;
- `day`/`month`/`year` ← `order_date` (месяц → родительный падеж, напр. «АВГУСТА»);
- `qty`, `session`, `game`, `tent` ← одноимённые поля заказа;
- `payment_amount`, `order_id`, `payment_id` ← `payment_amount`, `order_id`, `payment_transaction_id`;
- `order_item_qty`/`order_item_price` ← первая позиция `raw_payload.payment.products[0]`
  (таблица `order_items` удалена); фолбэк `1 × payment_amount`;
- `map_url`, `club_*`, `format` ← константы клуба выше.

---

## Безопасность

1. **Порядок**: письмо отправляется только **после** `conn.commit()` — сбой SMTP не откатывает заказ.
2. **Не роняет webhook**: вызов обёрнут в `try/except`, любая ошибка логируется, Tilda получает `200 OK`.
3. **Feature-флаг**: если `SMTP_HOST` не задан — код ничего не делает (ни БД, ни SMTP). Это состояние по умолчанию до настройки SMTP.
4. **Email из заказа**: адрес берётся из уже сохранённого поля `orders.customer_email`
   (отдельная таблица-лог не используется).
5. **Оплаченные заказы**: отправка только при `order_status == 'paid'` (конвенция CRM).

---

## Переменные окружения (orders-webhook)

Добавлены **только** секреты SMTP:

```
SMTP_HOST
SMTP_PORT       (по умолчанию 587)
SMTP_USER
SMTP_PASSWORD
```

Остальные параметры письма — константы в `shared/mailer.py`.

---

## Деплой

```cmd
cd newCRM\implementation
docker build -f docker/Dockerfile.webhook -t amkorobov/orders-webhook:latest .
docker push amkorobov/orders-webhook:latest
```

На App Platform: передеплоить `orders-webhook`, добавить env `SMTP_HOST/PORT/USER/PASSWORD`.

## Проверка

- Новый оплаченный заказ из Tilda → в логах webhook `confirmation email sent: order=... to=...`.

## Откат / отключение

- **Отключить без пересборки**: удалить `SMTP_HOST` из env сервиса → отправка выключена.
- **Откат кода**: восстановить файлы из бэкапа
  `_backup_email_notifications_v12.15_20260903_191515` (или `git checkout` изменённых файлов).
