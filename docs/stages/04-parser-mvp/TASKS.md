# Этап 4 — MVP calls-worker (MP3 parser)

**Цель:** парсинг почты в отдельном сервисе с исправлением двух критичных дефектов.
**Статус:** ✅ код готов, чистая логика протестирована; живой прогон (IMAP/S3/PG) — после staging.

## Готово
- [x] IMAP через **UID** (`imap.uid('search'/'fetch')`) — фикс #2 (`email_id` = UID).
- [x] Парсинг темы через `shared/subject.py`; 1 письмо = 1 звонок = 1 MP3.
- [x] Матчинг по телефону через `orders.customer_phone` (0→unmatched, 1→matched, >1→ambiguous).
- [x] S3-ключ **по sha256** `calls/{sha256[:2]}/{sha256}.mp3` — фикс #1 (нет перезаписи, нет дублей контента).
- [x] `mp3_hash UNIQUE` + `ON CONFLICT DO NOTHING` — защита от дублей по email_id И по содержимому.
- [x] Пре-проверка существующих `email_id`/`mp3_hash` до загрузки (нет лишних upload'ов).
- [x] Advisory lock против пересечения циклов; graceful цикл (ошибка письма не валит worker).
- [x] Health/status: `/status` отдаёт `last_cycle_at`, `processed`, `matched/unmatched/ambiguous`, `errors`.

## Проверено локально
- [x] `tests/test_parser.py`: матчинг, извлечение MP3-вложения, парсинг темы из реального письма.
- [x] Синтаксис `parser.py`/`imap.py`/`service.py`/`main.py` OK.

## Упрощение MVP (сознательное)
- Очередь/DLQ `call_processing_jobs` **отложена**: retry = следующий цикл + `email_id`/`mp3_hash` UNIQUE + advisory lock. Достаточно для текущей нагрузки (1 worker); добавляется при необходимости.

## Ожидает (живые зависимости)
- [ ] IMAP + S3 + PG: 3 рестарта без потери писем; один MP3 из разных писем → один объект S3.

## Выход
`calls_worker/parser.py`, `imap.py`, `service.py`, `main.py`, `tests/test_parser.py`.
