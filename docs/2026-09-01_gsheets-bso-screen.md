# Отчёт об изменении — экран «БСО» в CRM

- **Дата:** 01.09.2026
- **Версия:** v12.14
- **Сервис:** `crm` (фронтенд + `repo.py`)
- **Образ:** `amkorobov/crm:12.14`
- **Статус:** ✅ задеплоено

---

## Цель

Добавить в CRM (Telegram Mini App) экран **«БСО»** со списком карточек всех БСО из таблицы `orders_bso`, склеенных с заказом по `order_id`. Навигация: широкая кнопка «БСО» на главном экране + пункт «ЕЩЕ» в нижнем меню.

## Что изменено

### `crm/repo.py`
- `list_bso()`: в SELECT добавлены `o.payment_amount`, `o.order_status`, `o.customer_name AS order_customer_name` (склейка с `orders` по `order_id`).

### `crm/templates/index.html`
- Широкая кнопка **«БСО»** на главном экране (`start-btn-wide`, на всю ширину сетки 2×2).
- Новый экран `screen-bso` (`#bsoList`, `#bsoSummary`).
- Нижнее меню перестроено: `Расписание · Заказы · Звонки · ЕЩЕ`; `ЕЩЕ` открывает меню **Клиенты / БСО** (`#moreMenu`).

### `crm/static/app.js`
- `state.bso`, `loadBsoData()`, `bsoCard()`, `renderBso()`.
- Обработка `view = "bso"` в `show()`, активное состояние кнопки «ЕЩЕ» для `clients`/`bso`.
- Логика меню «ЕЩЕ» (toggle + закрытие по клику вне).

### `crm/static/style.css`
- Стили: `.start-btn-wide`, `.bso-card` (`.bso-client`, `.bso-head`, `.bso-number`, `.bso-date`, `.bso-total`, `.bso-details`, `.bso-row`, `.bso-foot`, `.bso-grand`), `.more-menu`, `.more-item`.

### `crm/webassets.py`
- Перегенерирован скриптом `scripts/gen_webassets.py` (43 022 → 49 227 байт).

---

## Карточка БСО (сверху вниз)

1. **Имя** — активная ссылка → карточка клиента (`openClientCard(client_id)`); если `client_id` нет — обычный текст.
2. **Крупно:** `БСО № <bso_number>`, дата (`game_date`), `total_bso`.
3. **Детали:** № заказа (`order_id`), игроков (факт) `players_fact`, зона отдыха `rest_zone_amount`.
4. **Низ:** Бронь `payment_amount`, Сумма заказа `order_amount`, **Итого** `payment_amount + order_amount = total_bso`.

---

## Не изменялось

- Схема БД (`orders_bso` не менялась — только новые колонки в SELECT).
- `orders-webhook`, `calls-worker`.

## Бэкап

- Каталог: `implementation/_backup_gsheets_bso_frontend_v12.14_20260901_003959/`
- Файлы: `crm/repo.py`, `crm/templates/index.html`, `crm/static/app.js`, `crm/static/style.css`, `crm/webassets.py`.

## Деплой

```cmd
cd /d C:\Users\amkor\OneDrive\Desktop\DSH_amkor\newCRM\implementation
docker build -f docker\Dockerfile.crm -t amkorobov/crm:12.14 .
docker push amkorobov/crm:12.14
```

Затем в App Platform передеплоен сервис `crm` на тег `amkorobov/crm:12.14`.

## Откат

Передеплой предыдущего образа `crm` (тег `amkorobov/crm:12.13` или `12.12`).
