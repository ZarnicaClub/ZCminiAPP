"""Забор строк БСО из Google Sheets (сервисный аккаунт) — замена Apps Script-отправителю.

Раньше скрипт в таблице раз в 5 минут отправлял строки листа «БАЛАНС» POST-ом на
`/webhook/gsheets`. После переезда на объединённое приложение адрес скрипта перестал
существовать (старый сервис удалён), поэтому поток развёрнут: CRM сама читает таблицу.

Правила отбора — те же, что были в скрипте (`gsheets_webhook/apps_script.gs`):
лист «БАЛАНС», статья «Касса», дата >= `GSHEETS_DATE_FROM`, заполнен `order_id`.
Маппинг полей — как в `docs/2026-08-31_orders-bso-gsheets.md`.

Доступ: сервисный аккаунт Google. Ключ берём либо из `GSHEETS_SA_B64` (base64 от JSON,
так удобнее хранить в переменных приложения), либо из файла `GSHEETS_SA_FILE`.
Таблица должна быть расшарена роботу на чтение.

Ничего не пишем напрямую в БД — отдаём разобранные строки в существующий
`orders_webhook.service.upsert_bso` (он идемпотентный: повтор обновляет, не дублирует).
"""
import base64
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterator, Optional

from shared.gsheets import parse_gsheets_bso

log = logging.getLogger("orders_webhook.gsheets_pull")

SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPE_SHEETS = "https://www.googleapis.com/auth/spreadsheets.readonly"
SCOPE_DRIVE = "https://www.googleapis.com/auth/drive.metadata.readonly"

DEFAULT_SHEET = "БАЛАНС"
DEFAULT_DATE_FROM = "2026-08-13"
DEFAULT_ARTICLE = "Касса"
# Запасной источник ключа робота: объект в закрытом хранилище S3 (переменная не нужна).
DEFAULT_SA_S3_KEY = "system/gsheets-sa.json"

# Откуда взяли ключ (для лога старта: видно, что именно сработало).
_sa_source = "не найден"

# Заголовки колонок в листе «БАЛАНС» -> имена полей payload (как в старом Apps Script).
COLUMNS = {
    "article": "Статья",
    "date": "Дата",
    "income": "Приход",
    "docNumber": "№ документа",
    "playersFact": "игроков (факт)",
    "customer": "Заказчик",
    "restZone": "Зона отдыха",
    "orderId": "order_id",
}


# ---------------------------------------------------------------------
# Доступ к Google
# ---------------------------------------------------------------------
def _parse_sa_text(text: str) -> Optional[dict]:
    """Разбирает ключ из строки: чистый JSON, base64 или base64url.

    Терпим к тому, что переменная при копировании через панель портится: лишние кавычки,
    переводы строк, потерянные символы «=» в конце (base64 требует выравнивания длины).
    """
    text = (text or "").strip().strip('"').strip("'").strip()
    if not text:
        return None
    if text.lstrip().startswith("{"):
        return json.loads(text)
    compact = re.sub(r"\s+", "", text)
    compact += "=" * (-len(compact) % 4)  # дописываем выравнивание, если панель его съела
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            return json.loads(decoder(compact).decode("utf-8"))
        except Exception:  # noqa: BLE001 — пробуем следующий вариант
            continue
    return None


def _sa_from_s3() -> Optional[dict]:
    """Запасной путь: ключ лежит в закрытом хранилище S3 (объект GSHEETS_SA_S3_KEY).

    Так надёжнее переменной: длинную строку в панели легко сохранить битой, а объект в S3
    не зависит от ограничений поля ввода.
    """
    key = os.getenv("GSHEETS_SA_S3_KEY", DEFAULT_SA_S3_KEY)
    if not key:
        return None
    try:
        from shared.s3 import s3_client

        client, bucket = s3_client()
        body = client.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")
        return json.loads(body)
    except Exception:  # noqa: BLE001 — S3 опционален, не валим старт приложения
        log.warning("ключ робота из S3 (%s) не прочитан", key)
        return None


def _sa_info() -> Optional[dict]:
    """Ключ сервисного аккаунта: переменная (base64/JSON) → файл → S3.

    Что было: ключ лежал только в переменной, и при потере символов при копировании
    забор молча не работал. Теперь источников три, а причина отказа попадает в лог.
    """
    global _sa_source
    raw = os.getenv("GSHEETS_SA_B64")
    if raw:
        info = _parse_sa_text(raw)
        if info:
            _sa_source = f"переменная GSHEETS_SA_B64 ({len(raw)} символов)"
            return info
        log.error("GSHEETS_SA_B64 не разобран как base64(JSON): длина %d символов, "
                  "похоже строка сохранена в панели не целиком", len(raw))
    path = os.getenv("GSHEETS_SA_FILE")
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                _sa_source = f"файл {path}"
                return json.load(f)
        except Exception:  # noqa: BLE001
            log.exception("не удалось прочитать файл ключа %s", path)
    info = _sa_from_s3()
    if info:
        _sa_source = f"S3 объект {os.getenv('GSHEETS_SA_S3_KEY', DEFAULT_SA_S3_KEY)}"
        return info
    return None


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def access_token(scope: str = SCOPE_SHEETS) -> str:
    """Меняет ключ сервисного аккаунта на access-токен Google (JWT-подпись RS256).

    Например: Google удаляет старые ключи и отзывает OAuth-доступы живых пользователей,
    а сервисный аккаунт работает, пока его не удалили и пока таблица расшарена ему.
    """
    info = _sa_info()
    if not info:
        raise RuntimeError("ключ сервисного аккаунта не задан (GSHEETS_SA_B64 / GSHEETS_SA_FILE)")

    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding, rsa

    now = int(time.time())
    header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claims = _b64url(json.dumps({
        "iss": info["client_email"],
        "scope": scope,
        "aud": info.get("token_uri", TOKEN_URI),
        "iat": now,
        "exp": now + 3600,
    }).encode())
    signing_input = f"{header}.{claims}"
    key = serialization.load_pem_private_key(info["private_key"].encode(), password=None)
    assert isinstance(key, rsa.RSAPrivateKey), "ключ сервисного аккаунта должен быть RSA"
    signature = key.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    assertion = f"{signing_input}.{_b64url(signature)}"

    data = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": assertion,
    }).encode()
    with urllib.request.urlopen(urllib.request.Request(
            info.get("token_uri", TOKEN_URI), data=data), timeout=30) as resp:
        return json.load(resp)["access_token"]


def _get_json(url: str, token: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def find_spreadsheet(token: str) -> Optional[str]:
    """Ищет таблицу, расшаренную роботу (если id не задан переменной окружения)."""
    query = urllib.parse.quote("mimeType='application/vnd.google-apps.spreadsheet' and trashed=false")
    url = (f"https://www.googleapis.com/drive/v3/files?q={query}&pageSize=10"
           f"&fields=files(id,name)&orderBy=modifiedTime desc")
    data = _get_json(url, token)
    files = data.get("files", [])
    if not files:
        log.warning("роботу не расшарена ни одна таблица Google")
        return None
    if len(files) > 1:
        log.warning("роботу доступно несколько таблиц, беру самую свежую: %s",
                    ", ".join(f"{f['name']} ({f['id']})" for f in files))
    return files[0]["id"]


def spreadsheet_id(token: str) -> Optional[str]:
    return os.getenv("GSHEETS_SPREADSHEET_ID") or find_spreadsheet(token)


# ---------------------------------------------------------------------
# Разбор листа
# ---------------------------------------------------------------------
def _norm(value: Any) -> str:
    """Нормализация заголовка: без переносов/лишних пробелов, нижний регистр."""
    return " ".join(str(value or "").replace("\n", " ").split()).strip().lower()


def header_index(headers: list[Any]) -> dict:
    """Карта «поле -> индекс колонки» по фактическим заголовкам листа."""
    by_name = {_norm(h): i for i, h in enumerate(headers) if _norm(h)}
    idx, missing = {}, []
    for key, title in COLUMNS.items():
        pos = by_name.get(_norm(title))
        if pos is None:
            missing.append(title)
        else:
            idx[key] = pos
    if missing:
        raise RuntimeError("в листе не найдены колонки: " + ", ".join(missing))
    return idx


def iso_date(text: Any) -> Optional[str]:
    """Строка даты из таблицы -> ISO (поддерживаем 13.08.2026, 13.08.26, 2026-08-13)."""
    raw = str(text or "").strip()
    if not raw:
        return None
    for sep in (".", "/"):
        if sep in raw:
            parts = [p.strip() for p in raw.split(sep)]
            if len(parts) == 3 and all(p.isdigit() for p in parts):
                day, month, year = (int(p) for p in parts)
                if year < 100:
                    year += 2000
                if 1 <= day <= 31 and 1 <= month <= 12:
                    return f"{year:04d}-{month:02d}-{day:02d}"
    if "-" in raw:
        parts = raw.split("-")
        if len(parts) == 3 and all(p.isdigit() for p in parts):
            year, month, day = (int(p) for p in parts)
            return f"{year:04d}-{month:02d}-{day:02d}"
    return None


def _clean_number(value: Any) -> Any:
    """Убирает «₽» и неразрывные пробелы, чтобы числовой парсер их понял."""
    if isinstance(value, str):
        return value.replace("₽", "").replace("\u00a0", " ").strip()
    return value


def iter_payloads(values: list[list[Any]], date_from: str = DEFAULT_DATE_FROM,
                  article: str = DEFAULT_ARTICLE) -> Iterator[dict]:
    """Проходит строки листа и отдаёт payload'ы для CRM (как это делал Apps Script)."""
    if not values:
        return
    idx = header_index(values[0])
    for line_no, row in enumerate(values[1:], start=2):
        def cell(key: str) -> Any:
            pos = idx[key]
            return row[pos] if pos < len(row) else None

        row_article = str(cell("article") or "").strip()
        if row_article.lower() != article.lower():
            continue
        game_date = iso_date(cell("date"))
        if not game_date or game_date < date_from:
            continue
        order_id_raw = str(cell("orderId") or "").strip()
        order_id = "".join(ch for ch in order_id_raw if ch.isdigit())
        if not order_id:
            continue
        if not game_date:
            continue
        yield {
            "_row": line_no,
            "order_id": order_id,
            "game_date": game_date,
            "order_amount": _clean_number(cell("income")),
            "bso_number": str(cell("docNumber") or "").strip(),
            "players_fact": cell("playersFact"),
            "customer_name": str(cell("customer") or "").strip(),
            "rest_zone_amount": _clean_number(cell("restZone")),
        }


def fetch_values(sheet_id: str, token: str, sheet_name: str = DEFAULT_SHEET) -> list[list[Any]]:
    """Читает весь лист одним запросом (значения как их видит человек в таблице)."""
    rng = urllib.parse.quote(f"'{sheet_name}'!A1:BZ", safe="")
    url = f"{SHEETS_API}/{sheet_id}/values/{rng}?valueRenderOption=FORMATTED_VALUE"
    data = _get_json(url, token)
    return data.get("values", [])


# ---------------------------------------------------------------------
# Прогон
# ---------------------------------------------------------------------
def pull_once(sheet_id: Optional[str] = None) -> dict:
    """Один прогон: читает лист и дописывает БСО в CRM. Возвращает счётчики."""
    from orders_webhook.service import upsert_bso  # локальный импорт: без циклов

    token = access_token(SCOPE_SHEETS)
    sid = sheet_id or spreadsheet_id(token)
    if not sid:
        return {"status": "no_spreadsheet", "seen": 0, "saved": 0, "skipped": 0, "errors": 0}

    sheet_name = os.getenv("GSHEETS_SHEET_NAME", DEFAULT_SHEET)
    date_from = os.getenv("GSHEETS_DATE_FROM", DEFAULT_DATE_FROM)
    values = fetch_values(sid, token, sheet_name)

    seen = saved = skipped = errors = 0
    for payload in iter_payloads(values, date_from=date_from):
        seen += 1
        row_no = payload.pop("_row")
        try:
            bso = parse_gsheets_bso(payload)
            if bso is None:
                log.warning("строка %s: не разобрался order_id, пропуск", row_no)
                skipped += 1
                continue
            result = upsert_bso(bso)
            if result.get("status") == "ok":
                saved += 1
            else:
                skipped += 1
                log.info("строка %s: %s", row_no, result.get("reason", result.get("status")))
        except Exception:  # noqa: BLE001 — одна плохая строка не должна ронять прогон
            errors += 1
            log.exception("строка %s: ошибка обработки", row_no)

    log.info("БСО из таблицы: строк в отборе %s, записано %s, пропущено %s, ошибок %s",
             seen, saved, skipped, errors)
    return {"status": "ok", "sheet_id": sid, "sheet": sheet_name,
            "seen": seen, "saved": saved, "skipped": skipped, "errors": errors}


def enabled() -> bool:
    """Автоматический забор включён? (флаг в окружении + есть ключ)"""
    flag = str(os.getenv("GSHEETS_PULL_ENABLED", "")).strip().lower()
    return flag in ("1", "true", "yes", "on") and _sa_info() is not None


def log_config() -> None:
    """Диагностика в логе старта: включён ли забор, откуда ключ и куда ходим."""
    info = _sa_info()
    log.info("БСО из Google Sheets: %s | робот=%s (ключ: %s) | лист=%s | отбор: статья «%s», дата с %s",
             "включён" if enabled() else "выключен",
             (info or {}).get("client_email", "—"),
             _sa_source,
             os.getenv("GSHEETS_SHEET_NAME", DEFAULT_SHEET),
             os.getenv("GSHEETS_ARTICLE", DEFAULT_ARTICLE),
             os.getenv("GSHEETS_DATE_FROM", DEFAULT_DATE_FROM))


async def loop_forever() -> None:
    """Фоновый цикл в приложении: раз в N секунд забирает БСО из таблицы."""
    import asyncio

    interval = int(os.getenv("GSHEETS_PULL_INTERVAL_SECONDS", "300") or 300)
    log.info("забор БСО запущен, интервал %s с", interval)
    while True:
        try:
            await asyncio.to_thread(pull_once)
        except Exception:  # noqa: BLE001 — цикл не должен умирать
            log.exception("прогон забора БСО упал")
        await asyncio.sleep(interval)
