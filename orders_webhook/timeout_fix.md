Мы нашли три ключевые проблемы в вашем коде, которые напрямую вызывают ошибки 500 в логах.

---

## 🔴 1. Отсутствует библиотека `python-multipart`

**Где:** в `app.py` при обработке не-JSON запросов:
```python
else:
    data = dict(await request.form())   # ❌ требует python-multipart
```
Tilda часто отправляет данные как `application/x-www-form-urlencoded`, и без этой библиотеки FastAPI/Starlette не может распарсить форму, выбрасывая `AssertionError`.

**Решение:** добавьте `python-multipart` в зависимости:
```bash
pip install python-multipart
```
и пересоберите/перезапустите приложение.

---

## 🔴 2. Соединение с PostgreSQL "умирает" из-за `idle_session_timeout`

**Где:** в `service.py` внутри `upsert_order`:
```python
with pool().connection() as conn:
    with conn.cursor() as cur:
        cur.execute(...)   # ❌ если соединение закрыто — падает с IdleSessionTimeout
```
В логах видно множество записей:
```
psycopg.errors.IdleSessionTimeout: terminating connection due to idle-session timeout
discarding closed connection: <psycopg.Connection [BAD] ...>
```
Это происходит, если между запросами проходит больше времени, чем настроено на сервере БД (`idle_in_transaction_session_timeout`). Пул возвращает "мёртвое" соединение, и попытка выполнить запрос вызывает исключение → 500.

**Решение (выберите одно):**

- **Использовать пул с проверкой (рекомендуется)**  
  Если вы используете `psycopg_pool.ConnectionPool`, включите аргумент `check`:
  ```python
  from psycopg_pool import ConnectionPool
  pool = ConnectionPool(..., check=ConnectionPool.check_connection)
  ```
  Тогда при получении соединения будет выполняться проверка (например, `SELECT 1`), и "битые" коннекты будут заменены.



## 🟡 3. Обработка `order_id` (не ошибка, но улучшение)

В логах есть предупреждения `no order_id in payload, skipping` – это значит, что Tilda иногда присылает заказы без `order_id`. Ваш код возвращает `200` со статусом `skipped`, что корректно. Однако если вы ожидаете, что все заказы имеют `order_id`, то можете оставить как есть.

---

## 🟢 Дополнительные рекомендации

- **Таймаут ответа Tilda** – Tilda ждёт ответ ровно **7 секунд**. Если ваша обработка (включая запись в БД) занимает больше, Tilda тоже выдаст 500. В ваших логах нет явных признаков долгих запросов, но советую замерить время выполнения `upsert_order` и при необходимости вынести тяжёлые операции в фоновые задачи.

- **Логирование ошибок** – у вас уже есть `log.exception("failed to save order")`, этого достаточно для диагностики.

- **Обработка пустого payload** – проверка `if not data` есть, но если Tilda пришлёт пустой `{}`, вы вернёте 400 – это правильно.

---

## 📝 Итоговый план действий

1. **Установите** `python-multipart`.
2. **Перепишите** `upsert_order` с использованием проверки соединения.
3. Перезапустите приложение.

После этих правок ошибки 500 из-за `python-multipart` и `IdleSessionTimeout` должны исчезнуть, и Tilda будет получать стабильные ответы 200.