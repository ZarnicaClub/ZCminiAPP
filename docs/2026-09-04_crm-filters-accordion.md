# Отчёт об изменении — фильтры по дате (Звонки/Заказы/БСО) + аккордеон БСО

- **Дата:** 04.09.2026
- **Версия:** v12.16
- **Сервис:** `crm` (бэкенд + встроенный фронтенд `crm/webassets.py`)
- **Образ:** `amkorobov/crm:12.16`
- **Статус:** ✅ задеплоено, работает

---

## Цель

1. Раздел **«Звонки»** — добавить фильтр по дате звонков (горизонтальный «ползунок» дат, по умолчанию активна «сегодня»).
2. Раздел **«Заказы»** — заменить фильтр-чипы на: **Ближайшие** (активна по умолчанию) / **Все** / **Выбор даты**.
3. Раздел **«БСО»** — свернуть карточки в аккордеон (в списке виден только `БСО №`, дата и сумма справа; остальное раскрывается по тапу) + добавить фильтр по дате сверху.

---

## Что изменено

### `crm/repo.py`
- Добавлена `_day_bounds(date_str)` — границы суток по часовому поясу `CALL_TIMEZONE_OFFSET`; `None` или невалидная дата → «сегодня».
- `calls_today(limit=200, date_str=None)` — теперь принимает опциональную дату и фильтрует звонки за указанные сутки.

### `crm/app.py`
- `GET /api/calls/today` — добавлен опциональный query-параметр `date` (ISO `YYYY-MM-DD`); без него поведение прежнее (сегодня).

### `crm/templates/index.html`
- Экран «Заказы»: чипы `Ближайшие` (active) / `Все` / `Выбор даты` + контейнер `#ordersDateStrip`.
- Экран «Звонки»: контейнер `#callsDateStrip`.
- Экран «БСО»: контейнер `#bsoDateStrip`.

### `crm/static/app.js`
- `state`: `ordersFilter` по умолчанию `"upcoming"`, добавлены `ordersDate`, `callsDate`, `bsoDate`.
- Новая `renderDayStrip(container, selected, onChange, opts)` — общий горизонтальный «ползунок» дат (−30..+7 дней), с опцией `allowAll` («Все»).
- Звонки: `renderCallsScreen()` / `loadCallsForDate(dateStr)` / `callsDateLabel()`; заголовки списка учитывают выбранную дату.
- Заказы: `renderOrdersDateStrip()` + фильтрация `date` по `event.date`; сводка под фильтром.
- БСО: `bsoCard()` переведён на аккордеон (`bso-toggle` + скрытое `bso-body`), `renderBsoDateStrip()` (фильтр «Все»/дата), `renderBso()` фильтрует по `game_date` и навешивает раскрытие.

### `crm/static/style.css`
- Стили полосы дат: `.day-strip-wrap`, `.day-strip`, `.day-chip`, `.day-chip-dow`, `.day-chip-num`, `.day-chip.all`.
- Стили аккордеона БСО: `.bso-toggle`, `.bso-toggle-main`, `.bso-toggle-title`, `.bso-toggle-date`, `.bso-toggle-total`, `.bso-chevron`, `.bso-body`.

### `crm/webassets.py`
- Перегенерирован скриптом `scripts/gen_webassets.py` (49 227 → 55 077 байт).

---

## Не изменялось

- Схема БД (миграции не добавлялись).
- `orders-webhook`, `calls-worker` — не трогались.
- Эндпоинты `/api/orders`, `/api/bso`, `/api/clients` и логика match-звонков — без изменений.

---

## Бэкап

- Каталог: `newCRM\_архив_данных\_backup_crm_filters_accordion_v12.16_20260904_002526\`
- Файлы (исходные версии до правок): `crm/app.py`, `crm/repo.py`, `crm/webassets.py`, `crm/templates/index.html`, `crm/static/app.js`, `crm/static/style.css`.

---

## Деплой

```cmd
cd /d C:\Users\amkor\OneDrive\Desktop\DSH_amkor\newCRM\implementation
docker build -f docker\Dockerfile.crm -t amkorobov/crm:12.16 .
docker push amkorobov/crm:12.16
```

Затем в Timeweb App Platform передеплоен сервис `crm` на тег `amkorobov/crm:12.16`.

---

## Откат (при необходимости)

1. Восстановить файлы `crm/` из бэкапа `_backup_crm_filters_accordion_v12.16_20260904_002526`.
2. Пересобрать ассеты: `python scripts/gen_webassets.py`.
3. Пересобрать и запушить образ `amkorobov/crm:12.14` (предыдущий) и передеплоить сервис `crm`.
