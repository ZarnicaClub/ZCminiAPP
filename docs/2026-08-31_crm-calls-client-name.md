# Отчёт об изменении — раздел «Звонки»: имя клиента + карточка клиента

- **Дата:** 31.08.2026
- **Версия CRM:** v12.12
- **Сервис:** `crm` (фронтенд, встроенный в `crm/webassets.py`)
- **Образ:** `amkorobov/crm:12.12`
- **Статус:** ✅ задеплоено, работает

---

## Цель

В разделе «Звонки» (`screen-calls`):

1. Звонки, привязанные к заказам, отмечать именем клиента.
2. При нажатии на такой звонок открывать карточку клиента.

Без изменений БД и схемы — резолв имени и `client_id` выполняется на фронтенде по уже загруженным данным.

---

## Что изменено

### 1. `crm/static/app.js`

Добавлены помощники (секция «звонки»):

- `findClientByPhone(phone)` — поиск клиента в `state.clients` по нормализованному телефону;
- `orderForCall(call)` — поиск заказа в `state.orders` по `call.order_id`;
- `callClientInfo(call)` — возвращает `{ order, client, name }`:
  - заказ — по `call.order_id`;
  - клиент — по телефону заказа, затем по телефону звонка;
  - имя — `order.customer.name` → `client.name`.

Изменён `callCard(call, options)`:

- принимает опции `{ showClient, index }`;
- для звонков с `order_id` (привязанных к заказу) выводит строку `👤 Имя клиента`;
- добавляет класс `call-card-linked` и атрибут `data-call-index` для обработчика клика.

Изменён `renderCallsToday()`:

- рендерит карточки с опциями `{ showClient: true, index: i }`;
- навешивает обработчик клика: привязанный звонок → `openClientCard(client_id)`, при отсутствии клиента — фолбэк на карточку заказа `openDetail(order)`.

### 2. `crm/static/style.css`

Добавлены стили:

```css
.call-client{font-weight:650;color:var(--green-dark);margin-top:6px}
.call-card-linked{cursor:pointer}
.call-card-linked:active{transform:scale(.99)}
```

### 3. `crm/webassets.py`

Перегенерирован скриптом `scripts/gen_webassets.py` (размер изменился 41 350 → 43 022 байт).

---

## Не изменялось

- База данных (схема, данные, запросы) — не трогались.
- `crm/repo.py` — не изменялся.
- Другие сервисы (`orders-webhook`, `calls-worker`) — не изменялись.

---

## Бэкап

- Каталог: `implementation/_backup_crm_calls_client_name_v12.10_20260831_205747/`
- Файлы: `app.js`, `style.css`, `webassets.py` (исходные версии до правок).

---

## Поведение

- **До:** все карточки звонков одинаковые (дата/время, длительность, администратор, телефон, аудио); клик не предусмотрен.
- **После:** у звонков, привязанных к заказу, отображается строка «👤 Имя клиента», карточка становится кликабельной (курсор + эффект нажатия); клик открывает карточку клиента. Непривязанные звонки остаются без имени и некликабельными.

---

## Деплой

```cmd
cd /d C:\Users\amkor\OneDrive\Desktop\DSH_amkor\newCRM\implementation
docker build -f docker\Dockerfile.crm -t amkorobov/crm:12.12 .
docker push amkorobov/crm:12.12
```

---

## Откат (при необходимости)

1. Восстановить `app.js`, `style.css`, `webassets.py` из бэкапа.
2. Пересобрать ассеты: `python scripts/gen_webassets.py`.
3. Пересобрать и запушить образ `amkorobov/crm:12.12` и передеплоить сервис `crm`.
