# Воркер разбора звонков на офисном компьютере

Сценарий: постоянный рабочий ПК в офисе (на нём уже стоит Hermes). Платить за сервер не нужно,
но появляются свои условия — они ниже.

## Что должно быть на ПК

- Постоянное питание; **отключены** сон и гибернация («Электропитание» → «Сон» → «Никогда»).
- Исходящий доступ в интернет по портам **993** (почта Яндекса, IMAP), **443** (S3 + Telegram), **5432** (база).
  Проверено: база Timeweb `201.34.136.152:5432` и S3 доступны из интернета; если база включит
  белый список адресов — нужно добавить IP офиса.
- Python 3.11+ (варианты 1–2, 4) либо Docker Desktop (вариант 3).

## Переменные

Файл `.env.worker` рядом с кодом (по образцу `.env.worker.example`): `DATABASE_URL`,
`S3_BUCKET_NAME`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `MAIL_USERNAME`, `MAIL_PASSWORD`,
`PARSER_LOOKBACK_HOURS=72`. Файл не выкладывать наружу — там пароль ящика и ключи хранилища.

## Вариант 1 (рекомендуемый) — служба Windows через NSSM

Лёгкий: ~150 МБ памяти, без Docker и WSL.

```powershell
# 1) код и виртуальное окружение
git clone https://github.com/ZarnicaClub/ZCminiAPP C:\zcminiapp
cd C:\zcminiapp
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install --no-index --find-links=wheels -r requirements.txt

# 2) проверка вручную (должен отработать цикл и написать итог)
copy .env.worker.example .env.worker    # и заполнить значения
.\.venv\Scripts\python -m calls_worker.main --once

# 3) служба с автозапуском и авто-перезапуском
nssm install ZCWorker "C:\zcminiapp\.venv\Scripts\python.exe" "-m calls_worker.main"
nssm set ZCWorker AppDirectory "C:\zcminiapp"
nssm set ZCWorker AppExit Default Restart
nssm set ZCWorker Start SERVICE_AUTO_START
nssm start ZCWorker
```

## Вариант 2 — Планировщик заданий Windows (без сторонних программ)

Задача: «При запуске компьютера», повтор каждые 5 минут, действие:
`C:\zcminiapp\.venv\Scripts\python.exe -m calls_worker.main --once`, рабочая папка `C:\zcminiapp`.
Во вкладке «Параметры» — галочки «Перезапускать при сбое» и «Выполнять задачу, если компьютер работает от батарей».

## Вариант 3 — Docker Desktop

```powershell
cd C:\zcminiapp
copy .env.worker.example .env.worker
docker compose -f docker-compose.worker.yml up -d --build
```
Обязательно включить в Docker Desktop «Start Docker Desktop when you sign in», иначе после
перезагрузки контейнер не поднимется.

## Вариант 4 — расписание Hermes на офисном ПК

Если не хочется заводить службу: в Hermes на этом ПК создать задачу по расписанию (каждые 5 минут),
команда — `.venv\Scripts\python -m calls_worker.main --once`, рабочая папка — папка проекта.
Плюс: ничего не устанавливать дополнительно. Минус: циклы идут, пока живёт Hermes.

## Проверка

```powershell
curl http://127.0.0.1:8081/status        # варианты 1 и 3: счётчики цикла
Get-Content .\worker.log -Tail 20        # варианты 2 и 4: смотрите вывод задачи
```
Признак успеха: `last_cycle_at` обновляется каждые ~5 минут, `errors` не растёт.

## Нюансы офисного ПК

- **Выключение на выходные**: письма остаются в ящике, воркер разберёт их при следующем запуске
  в пределах окна `PARSER_LOOKBACK_HOURS` (ставим 72–168 ч). Повторов не будет: дубли отсекаются
  по номеру письма и хэшу MP3.
- **Обновления Windows**: перезагрузку лучше планировать на ночь; после неё служба/задача поднимется сама.
- **Резервное копирование пароля ящика и ключей S3**: если ПК переустановят — переменные придётся
  вводить заново, храните копию в защищённом месте.
